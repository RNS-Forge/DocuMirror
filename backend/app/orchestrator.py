"""
orchestrator.py
---------------
LangGraph state machine that wires together the full extraction pipeline:

    classify → extract → render → screenshot → ssim → (critic → re-extract)*

State is kept entirely in-memory in the LangGraph TypedDict.  Nothing is
written to disk beyond the two final output files (template.ejs, data.json)
which are placed in OUTPUT_DIR/<job_id>/ and deleted after the response is
built.

Graph nodes
-----------
  classify_node   – detect document type
  extract_node    – vision LLM extraction (uses correction_notes if present)
  render_node     – call Node render service → HTML
  screenshot_node – Playwright screenshot → PNG bytes
  ssim_node       – compute SSIM, decide whether to continue or finish
  critic_node     – compare images, build correction_notes
  finish_node     – assemble final result, clean up temp files

Edges
-----
  classify → extract → render → screenshot → ssim
  ssim → critic        (if SSIM < threshold AND iterations < max)
  ssim → finish        (if SSIM >= threshold OR iterations >= max OR 0 mismatches)
  critic → extract     (loop back)
  extract → render → screenshot → ssim (repeat)

Public API
----------
    run_pipeline(pdf_path, job_id) -> PipelineResult
"""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from app.config import (
    MAX_CORRECTION_ITERATIONS,
    OUTPUT_DIR,
    SSIM_THRESHOLD,
)
from app.critic import mismatches_to_correction_notes, run_critic
from app.pdf_to_images import pdf_to_images
from app.render_client import render_template
from app.schemas import CriticResponse, DocumentData, IterationResult
from app.template_engine import get_template
from app.vision_extraction import classify_document, extract_document
from app.visual_diff import compute_ssim, screenshot_html

logger = logging.getLogger("documirror.orchestrator")


# ---------------------------------------------------------------------------
# Pipeline result dataclass
# ---------------------------------------------------------------------------

@dataclass
class PipelineResult:
    """Final result returned by run_pipeline()."""
    job_id: str
    doc_type: str
    template_ejs: str
    data_json: dict
    final_ssim: float
    iterations: List[IterationResult]
    output_dir: Path  # caller should delete after use


# ---------------------------------------------------------------------------
# LangGraph state
# ---------------------------------------------------------------------------

class PipelineState(TypedDict):
    # Inputs
    job_id: str
    page_images: List[bytes]          # PNG bytes per page (usually just page 0)
    output_dir: str                   # str path so TypedDict stays JSON-serialisable

    # Classification
    doc_type: str

    # Extraction
    extracted_data: Optional[dict]    # Pydantic model serialised to dict
    correction_notes: str             # cumulative critic notes for next extraction

    # Render
    template_ejs: str
    rendered_html: str

    # Visual comparison
    screenshot_bytes: Optional[bytes]
    ssim_score: float

    # Critic
    critic_response: Optional[dict]   # CriticResponse serialised to dict

    # Loop control
    iteration: int
    iteration_history: List[dict]     # [{iteration, ssim_score, mismatch_count}]
    done: bool


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------

def _classify_node(state: PipelineState) -> dict:
    """Classify the document type from the first page image."""
    logger.info("[%s] classify_node  (iteration=%d)", state["job_id"], state["iteration"])
    doc_type = classify_document(state["page_images"][0])
    return {"doc_type": doc_type}


def _extract_node(state: PipelineState) -> dict:
    """
    Extract field values and layout metadata.
    On iterations > 0 the correction_notes from the critic are included.
    """
    logger.info(
        "[%s] extract_node  (iteration=%d, doc_type=%s)",
        state["job_id"], state["iteration"], state["doc_type"],
    )
    correction_notes = state.get("correction_notes", "")
    data: DocumentData = extract_document(
        image_bytes=state["page_images"][0],
        doc_type=state["doc_type"],
        correction_notes=correction_notes,
    )
    return {"extracted_data": data.model_dump(mode="json")}


def _render_node(state: PipelineState) -> dict:
    """Build the EJS template and render it to HTML via the Node service."""
    logger.info("[%s] render_node  (iteration=%d)", state["job_id"], state["iteration"])

    data_dict: dict = state["extracted_data"]
    doc_type: str = state["doc_type"]

    # Reconstruct Pydantic model to pass typed data to template_engine
    from app.schemas import CommercialInvoice, Invoice, PackingList
    _cls_map = {
        "commercial_invoice": CommercialInvoice,
        "packing_list": PackingList,
        "invoice": Invoice,
    }
    cls = _cls_map.get(doc_type, Invoice)
    typed_data = cls.model_validate(data_dict)

    # Critic mismatches for CSS override injection
    critic_raw = state.get("critic_response") or {}
    critic_mismatches = []
    if critic_raw:
        try:
            cr = CriticResponse.model_validate(critic_raw)
            critic_mismatches = cr.mismatches
        except Exception:  # noqa: BLE001
            pass

    template_ejs = get_template(doc_type, typed_data, critic_mismatches)
    rendered_html = render_template(template_ejs, data_dict)

    return {"template_ejs": template_ejs, "rendered_html": rendered_html}


def _screenshot_node(state: PipelineState) -> dict:
    """Take a Playwright screenshot of the rendered HTML."""
    logger.info("[%s] screenshot_node  (iteration=%d)", state["job_id"], state["iteration"])
    png_bytes = screenshot_html(state["rendered_html"])
    return {"screenshot_bytes": png_bytes}


def _ssim_node(state: PipelineState) -> dict:
    """Compute SSIM and decide whether to continue the correction loop."""
    logger.info("[%s] ssim_node  (iteration=%d)", state["job_id"], state["iteration"])

    score = compute_ssim(state["page_images"][0], state["screenshot_bytes"])

    # Record this iteration
    history: list = list(state.get("iteration_history", []))
    history.append({
        "iteration": state["iteration"],
        "ssim_score": round(score, 4),
        "mismatch_count": -1,   # filled in by critic_node if we go there
    })

    iteration = state["iteration"]
    done = score >= SSIM_THRESHOLD or iteration >= MAX_CORRECTION_ITERATIONS

    logger.info(
        "[%s] SSIM=%.4f  threshold=%.2f  iteration=%d/%d  done=%s",
        state["job_id"], score, SSIM_THRESHOLD, iteration, MAX_CORRECTION_ITERATIONS, done,
    )

    return {
        "ssim_score": score,
        "iteration_history": history,
        "done": done,
    }


def _critic_node(state: PipelineState) -> dict:
    """
    Run the vision critic to compare original vs rendered.
    Build correction_notes for the next extraction call.
    Update the mismatch_count in the last history entry.
    """
    logger.info("[%s] critic_node  (iteration=%d)", state["job_id"], state["iteration"])

    critic_result: CriticResponse = run_critic(
        original_image_bytes=state["page_images"][0],
        rendered_image_bytes=state["screenshot_bytes"],
    )

    # If critic reports zero mismatches, mark done immediately
    mismatch_count = len(critic_result.mismatches)
    done = mismatch_count == 0

    # Patch mismatch_count into the last history entry
    history = list(state.get("iteration_history", []))
    if history:
        history[-1] = dict(history[-1])
        history[-1]["mismatch_count"] = mismatch_count

    correction_notes = mismatches_to_correction_notes(critic_result)

    logger.info(
        "[%s] critic: %d mismatch(es) — done=%s",
        state["job_id"], mismatch_count, done,
    )

    return {
        "critic_response": critic_result.model_dump(mode="json"),
        "correction_notes": correction_notes,
        "iteration_history": history,
        "done": done,
        "iteration": state["iteration"] + 1,
    }


def _finish_node(state: PipelineState) -> dict:
    """
    Write final template.ejs and data.json to the job output directory.
    These files are short-lived — the API handler streams them in the
    response body and then cleans up the directory.
    """
    logger.info("[%s] finish_node — pipeline complete", state["job_id"])

    out = Path(state["output_dir"])
    out.mkdir(parents=True, exist_ok=True)

    template_path = out / "template.ejs"
    data_path = out / "data.json"

    template_path.write_text(state["template_ejs"], encoding="utf-8")
    data_path.write_text(
        json.dumps(state["extracted_data"], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info("[%s] Wrote %s and %s", state["job_id"], template_path, data_path)
    return {}


# ---------------------------------------------------------------------------
# Routing condition
# ---------------------------------------------------------------------------

def _should_continue(state: PipelineState) -> str:
    """Route from ssim_node: go to critic or finish."""
    if state.get("done", False):
        return "finish"
    return "critic"


def _after_critic(state: PipelineState) -> str:
    """Route from critic_node: loop back to extract or finish."""
    if state.get("done", False):
        return "finish"
    return "extract"


# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------

def _build_graph() -> Any:
    """Construct and compile the LangGraph pipeline."""
    builder = StateGraph(PipelineState)

    builder.add_node("classify", _classify_node)
    builder.add_node("extract", _extract_node)
    builder.add_node("render", _render_node)
    builder.add_node("screenshot", _screenshot_node)
    builder.add_node("ssim", _ssim_node)
    builder.add_node("critic", _critic_node)
    builder.add_node("finish", _finish_node)

    builder.set_entry_point("classify")

    builder.add_edge("classify", "extract")
    builder.add_edge("extract", "render")
    builder.add_edge("render", "screenshot")
    builder.add_edge("screenshot", "ssim")

    builder.add_conditional_edges("ssim", _should_continue, {"critic": "critic", "finish": "finish"})
    builder.add_conditional_edges("critic", _after_critic, {"extract": "extract", "finish": "finish"})

    builder.add_edge("finish", END)

    return builder.compile()


_GRAPH = _build_graph()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_pipeline(pdf_path: str | Path, job_id: Optional[str] = None) -> PipelineResult:
    """
    Run the full extraction pipeline for *pdf_path*.

    Parameters
    ----------
    pdf_path : str | Path
        Absolute path to the uploaded PDF file.
    job_id : str | None
        Unique job identifier; auto-generated if not provided.

    Returns
    -------
    PipelineResult
        Contains template_ejs, data_json, final_ssim, and iteration history.
        The caller is responsible for cleaning up PipelineResult.output_dir
        after streaming the response.
    """
    job_id = job_id or str(uuid.uuid4())
    out_dir = OUTPUT_DIR / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Starting pipeline for job %s  pdf=%s", job_id, pdf_path)

    # Convert PDF pages to PNG bytes (use only page 0 for single-page docs)
    page_images: List[bytes] = pdf_to_images(str(pdf_path))
    if not page_images:
        raise ValueError("PDF produced no page images")

    initial_state: PipelineState = {
        "job_id": job_id,
        "page_images": page_images,
        "output_dir": str(out_dir),
        "doc_type": "",
        "extracted_data": None,
        "correction_notes": "",
        "template_ejs": "",
        "rendered_html": "",
        "screenshot_bytes": None,
        "ssim_score": 0.0,
        "critic_response": None,
        "iteration": 1,
        "iteration_history": [],
        "done": False,
    }

    final_state: PipelineState = _GRAPH.invoke(initial_state)

    # Build iteration summary
    iteration_results = [
        IterationResult(
            iteration=h["iteration"],
            ssim_score=h["ssim_score"],
            mismatch_count=h.get("mismatch_count", -1),
        )
        for h in final_state.get("iteration_history", [])
    ]

    return PipelineResult(
        job_id=job_id,
        doc_type=final_state["doc_type"],
        template_ejs=final_state["template_ejs"],
        data_json=final_state["extracted_data"] or {},
        final_ssim=final_state["ssim_score"],
        iterations=iteration_results,
        output_dir=out_dir,
    )
