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
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import BACKEND_PORT, TEMP_UPLOAD_DIR, OUTPUT_DIR
from app.orchestrator import run_pipeline
from app.render_client import check_render_service
from app.schemas import ExtractionResponse, IterationResult

logger = logging.getLogger("documirror.main")

_STATIC_DIR = Path(__file__).parent.parent / "static"

app = FastAPI(
    title="DocuMirror",
    description="PDF → EJS template + JSON extraction API",
    version="1.0.0",
)

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
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are accepted. Received: " + filename,
        )

    job_id = str(uuid.uuid4())
    logger.info("New job %s  file=%s", job_id, filename)

    pdf_path: Optional[Path] = None
    output_dir: Optional[Path] = None

    try:
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
# Dev entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=BACKEND_PORT, reload=True)
