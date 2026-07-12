"""
main.py
-------
FastAPI application exposing the DocuMirror extraction pipeline.

Endpoints
---------
  POST /extract
      Accepts a PDF upload, runs the full pipeline, and returns:
        - template_ejs (string)
        - data_json (object)
        - final_ssim (float)
        - iterations (array)
      Temp files are cleaned up automatically after the response is sent.

  GET /extract/{job_id}/preview
      Returns the rendered PNG screenshot for visual inspection.
      Only valid while the output directory still exists on disk.

  GET /health
      Basic liveness check.
"""

from __future__ import annotations

import logging
import shutil
import uuid
import time
import psutil
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import BACKEND_PORT, TEMP_UPLOAD_DIR, OUTPUT_DIR
from app.agent_orchestrator import run_pipeline
from app.render_client import check_render_service
from app.schemas import ExtractionResponse, IterationResult
from app.chatbot_agent import process_chat

from pydantic import BaseModel

logger = logging.getLogger("documirror.main")

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    reply: str


_STATIC_DIR = Path(__file__).parent.parent / "static"

app = FastAPI(
    title="DocuMirror",
    description="PDF → EJS template + JSON extraction API",
    version="1.0.0",
)

ACTIVE_JOBS = {}

# Serve the upload UI at the root
if _STATIC_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", include_in_schema=False)
async def root() -> FileResponse:
    """Redirect root to the upload UI."""
    return FileResponse(str(_STATIC_DIR / "index.html"))


@app.get("/upload", include_in_schema=False)
async def upload_page() -> FileResponse:
    """Serve the upload and extraction page."""
    return FileResponse(str(_STATIC_DIR / "upload.html"))


@app.get("/editor", include_in_schema=False)
async def editor_page() -> FileResponse:
    """Serve the code editor page."""
    return FileResponse(str(_STATIC_DIR / "codeeditor.html"))


# ---------------------------------------------------------------------------
# Startup check
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_checks() -> None:
    """Warn if the Node render service is not reachable at startup."""
    if not check_render_service():
        logger.warning(
            "Node render service not reachable at startup. "
            "Start it with: cd render-service && npm start"
        )
    else:
        logger.info("Node render service: OK")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _save_upload(upload: UploadFile, job_id: str) -> Path:
    """Persist the uploaded file to TEMP_UPLOAD_DIR and return its path."""
    suffix = Path(upload.filename or "upload.pdf").suffix or ".pdf"
    dest = TEMP_UPLOAD_DIR / f"{job_id}{suffix}"
    with dest.open("wb") as fh:
        fh.write(upload.file.read())
    logger.info("Saved upload to %s  (%d bytes)", dest, dest.stat().st_size)
    return dest


# ---------------------------------------------------------------------------
# POST /extract
# ---------------------------------------------------------------------------

@app.post("/extract", response_model=ExtractionResponse, summary="Extract template + data from PDF")
async def extract(
    file: UploadFile = File(..., description="PDF file to process"),
) -> JSONResponse:
    """
    Upload a PDF and receive back an EJS template, extracted JSON data,
    the final SSIM score, and a per-iteration summary.

    The pipeline runs synchronously (blocking).  For production use,
    wrap in a background task or run behind a task queue.
    """
    # --- Validate file type ---
    filename = upload_filename = file.filename or "upload.pdf"
    valid_exts = (".pdf", ".png", ".jpg", ".jpeg", ".webp")
    if not filename.lower().endswith(valid_exts):
        raise HTTPException(
            status_code=400,
            detail=f"Only PDF and Image files are accepted. Received: {filename}",
        )

    job_id = str(uuid.uuid4())
    logger.info("New job %s  file=%s", job_id, filename)

    pdf_path: Optional[Path] = None
    output_dir: Optional[Path] = None

    try:
        # 0. Track job
        ACTIVE_JOBS[job_id] = {
            "status": "running",
            "filename": filename,
            "started_at": time.time(),
        }

        # 1. Save upload
        pdf_path = _save_upload(file, job_id)

        # 2. Run pipeline
        result = run_pipeline(pdf_path=pdf_path, job_id=job_id)
        output_dir = result.output_dir

        # 3. Build response payload
        response_payload = ExtractionResponse(
            job_id=job_id,
            doc_type=result.doc_type,
            template_ejs=result.template_ejs,
            data_json=result.data_json,
            final_ssim=round(result.final_ssim, 4),
            iterations=[
                IterationResult(
                    iteration=it.iteration,
                    ssim_score=it.ssim_score,
                    mismatch_count=it.mismatch_count,
                )
                for it in result.iterations
            ],
            message="OK",
        )

        logger.info(
            "Job %s complete  doc_type=%s  ssim=%.4f  iterations=%d",
            job_id,
            result.doc_type,
            result.final_ssim,
            len(result.iterations),
        )
        
        # update job status
        ACTIVE_JOBS[job_id]["status"] = "completed"
        ACTIVE_JOBS[job_id]["completed_at"] = time.time()

        return JSONResponse(content=response_payload.model_dump(mode="json"))

    except Exception as exc:
        logger.exception("Job %s failed: %s", job_id, exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    finally:
        # Always clean up the uploaded PDF
        if pdf_path and pdf_path.exists():
            pdf_path.unlink(missing_ok=True)
            logger.debug("Deleted upload: %s", pdf_path)

        # Output dir is kept briefly for the /preview endpoint;
        # it will be cleaned up either by /preview or on next server restart.
        # For a pure in-memory flow (no preview needed), uncomment:
        # if output_dir and output_dir.exists():
        #     shutil.rmtree(output_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# GET /extract/{job_id}/preview
# ---------------------------------------------------------------------------

@app.get(
    "/extract/{job_id}/preview",
    summary="Return rendered PNG screenshot for visual inspection",
    response_class=FileResponse,
)
async def preview(job_id: str) -> FileResponse:
    """
    Return the Playwright-rendered PNG screenshot for the given job.
    Only valid while the job's output directory still exists on disk.
    The directory is deleted after this endpoint is called.
    """
    # The screenshot is saved by the orchestrator's finish_node alongside
    # template.ejs and data.json.  We look for it here.
    out_dir = OUTPUT_DIR / job_id
    screenshot_path = out_dir / "screenshot.png"

    # Fallback: check if there's any PNG in the output dir
    if not screenshot_path.exists():
        pngs = list(out_dir.glob("*.png")) if out_dir.exists() else []
        if pngs:
            screenshot_path = pngs[0]
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Preview not found for job {job_id}. "
                       "The job may have completed and files were cleaned up.",
            )

    # Stream the file then schedule cleanup
    def cleanup() -> None:
        shutil.rmtree(out_dir, ignore_errors=True)
        logger.debug("Cleaned up output dir after preview: %s", out_dir)

    response = FileResponse(
        path=str(screenshot_path),
        media_type="image/png",
        filename=f"{job_id}_preview.png",
        background=None,
    )
    # Cleanup happens after response is sent via a background task
    from starlette.background import BackgroundTask
    response.background = BackgroundTask(cleanup)
    return response


# ---------------------------------------------------------------------------
# POST /chat
# ---------------------------------------------------------------------------
@app.post("/chat", response_model=ChatResponse, summary="Chat with the Dibella AI Assistant")
async def chat_endpoint(
    message: str = Form(...),
    image: Optional[UploadFile] = File(None)
) -> JSONResponse:
    """
    Chatbot endpoint. Queries the RAG store and returns an answer.
    Currently routed to DocuMirror Chatbot Agent.
    """
    reply = process_chat(message)
    return JSONResponse(content={"reply": reply})

class EditCodeRequest(BaseModel):
    code: str
    prompt: str
    file_type: str

@app.post("/api/edit_code", summary="AI code editing assistant")
async def edit_code_endpoint(req: EditCodeRequest) -> JSONResponse:
    """
    Edit a code snippet or full file based on the prompt using Groq.
    """
    try:
        from app.vision_extraction import _groq_client
        model = "llama-3.3-70b-specdec"
        
        system_instruction = (
            "You are an expert developer. Your task is to modify the provided code according to the instructions. "
            "Return ONLY the modified code. Do not wrap the output in markdown code blocks (e.g. ```html or ```), "
            "do not include explanations, and do not write any greetings or warnings. Return the raw edited code directly."
        )
        
        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": f"CODE:\n{req.code}\n\nINSTRUCTIONS:\n{req.prompt}"}
        ]
        
        resp = _groq_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.1
        )
        edited = resp.choices[0].message.content or ""
        edited = edited.strip()
        
        # Strip accidental code blocks
        if edited.startswith("```"):
            lines = edited.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            edited = "\n".join(lines).strip()
            
        return JSONResponse(content={"edited_code": edited})
    except Exception as e:
        logger.error("AI code edit failed: %s", e)
        # Fallback to config vision model
        try:
            from app.vision_extraction import _groq_client
            from app.config import GROQ_VISION_MODEL
            resp = _groq_client.chat.completions.create(
                model=GROQ_VISION_MODEL,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": f"CODE:\n{req.code}\n\nINSTRUCTIONS:\n{req.prompt}"}
                ],
                temperature=0.1
            )
            edited = resp.choices[0].message.content or ""
            edited = edited.strip()
            if edited.startswith("```"):
                lines = edited.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                edited = "\n".join(lines).strip()
            return JSONResponse(content={"edited_code": edited})
        except Exception as err:
            logger.error("Fallback AI edit failed: %s", err)
            raise HTTPException(status_code=500, detail=str(err)) from err

# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@app.get("/health", summary="Liveness check")
async def health() -> dict:
    render_ok = check_render_service()
    return {
        "status": "ok",
        "render_service": "up" if render_ok else "down",
    }


# ---------------------------------------------------------------------------
# GET /processes
# ---------------------------------------------------------------------------

@app.get("/processes", summary="Get system processes and active jobs")
async def get_processes() -> dict:
    """Return backend server process stats and current pipeline active jobs."""
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        process = psutil.Process()
        app_mem = process.memory_info().rss / (1024 * 1024) # MB
        
        stats = {
            "cpu_percent": cpu_percent,
            "memory_percent": mem.percent,
            "app_memory_mb": round(app_mem, 2),
            "total_memory_mb": round(mem.total / (1024 * 1024), 2),
            "available_memory_mb": round(mem.available / (1024 * 1024), 2)
        }
    except Exception as e:
        stats = {"error": str(e)}

    # cleanup old completed jobs (> 1 hr)
    now = time.time()
    for jid in list(ACTIVE_JOBS.keys()):
        job = ACTIVE_JOBS[jid]
        if job["status"] == "completed" and "completed_at" in job:
            if now - job["completed_at"] > 3600:
                del ACTIVE_JOBS[jid]
                
    return {
        "system_stats": stats,
        "active_jobs": ACTIVE_JOBS
    }


# ---------------------------------------------------------------------------
# Dev entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=BACKEND_PORT, reload=True)
