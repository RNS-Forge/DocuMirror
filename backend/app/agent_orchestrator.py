import asyncio
import uuid
from typing import TypedDict, Annotated, List, Dict, Any
from dataclasses import dataclass
from pathlib import Path

from langgraph.graph import StateGraph, START, END
from app.config import OUTPUT_DIR
from app.schemas import IterationResult

# Define the State
class AgentState(TypedDict):
    file_path: str
    image_bytes: bytes
    doc_type: str
    raw_fields: dict
    draft_html: str
    screenshot_bytes: bytes
    mismatches: List[str]
    iterations: int
    iterations_history: List[dict]
    structured_json: dict
    status: str

# Import node functions
from app.classifier_agent import classifier_node
from app.ci_agent import ci_node
from app.pl_agent import pl_node
from app.verifier_agent import verifier_node
from app.json_agent import json_node

@dataclass
class PipelineResult:
    """Final result returned by run_pipeline()."""
    job_id: str
    doc_type: str
    template_ejs: str
    data_json: dict
    final_ssim: float
    iterations: List[IterationResult]
    output_dir: Path

class AgentOrchestrator:
    def __init__(self):
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("classifier", classifier_node)
        workflow.add_node("ci_generator", ci_node)
        workflow.add_node("pl_generator", pl_node)
        workflow.add_node("verifier", verifier_node)
        workflow.add_node("json_mapper", json_node)

        # Build edges
        workflow.add_edge(START, "classifier")

        # Conditional routing from classifier
        def route_generator(state: AgentState):
            if state.get("doc_type") == "ci":
                return "ci_generator"
            elif state.get("doc_type") == "pl":
                return "pl_generator"
            else:
                return "ci_generator"

        workflow.add_conditional_edges(
            "classifier",
            route_generator,
            {
                "ci_generator": "ci_generator",
                "pl_generator": "pl_generator"
            }
        )

        workflow.add_edge("ci_generator", "verifier")
        workflow.add_edge("pl_generator", "verifier")

        # Conditional routing from verifier
        def route_verification(state: AgentState):
            if len(state.get("mismatches", [])) > 0 and state.get("iterations", 0) < 5:
                # Loop back to generator
                if state.get("doc_type") == "pl":
                    return "pl_generator"
                return "ci_generator"
            else:
                return "json_mapper"

        workflow.add_conditional_edges(
            "verifier",
            route_verification,
            {
                "ci_generator": "ci_generator",
                "pl_generator": "pl_generator",
                "json_mapper": "json_mapper"
            }
        )

        workflow.add_edge("json_mapper", END)

        return workflow.compile()

    def invoke_sync(self, file_path: str):
        from app.pdf_to_images import pdf_to_images
        # Convert first page of PDF to image bytes
        image_bytes = None
        try:
            images = pdf_to_images(file_path)
            if images:
                image_bytes = images[0]
        except Exception as e:
            print(f"Failed to read PDF images: {e}")

        initial_state = {
            "file_path": file_path,
            "image_bytes": image_bytes,
            "doc_type": "unknown",
            "raw_fields": {},
            "draft_html": "",
            "screenshot_bytes": b"",
            "mismatches": [],
            "iterations": 0,
            "iterations_history": [],
            "structured_json": {},
            "status": "started"
        }
        return self.graph.invoke(initial_state)

_orchestrator = AgentOrchestrator()

def run_pipeline(pdf_path: str | Path, job_id: str | None = None) -> PipelineResult:
    """
    Wrapper to match the FastAPI main.py expectations.
    """
    job_id = job_id or str(uuid.uuid4())
    out_dir = OUTPUT_DIR / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    
    final_state = _orchestrator.invoke_sync(str(pdf_path))
    
    # Write screenshot to out_dir
    screenshot_path = out_dir / "screenshot.png"
    screenshot_bytes = final_state.get("screenshot_bytes", b"")
    with open(screenshot_path, "wb") as f:
        f.write(screenshot_bytes)

    template_ejs = final_state.get("draft_html", "")
    data_json = final_state.get("structured_json", {})
    
    iterations_history = final_state.get("iterations_history", [])
    iterations_list = []
    
    for i, hist in enumerate(iterations_history, 1):
        iterations_list.append(IterationResult(
            iteration=i,
            ssim_score=hist.get("ssim_score", 0.0),
            mismatch_count=hist.get("mismatch_count", 0)
        ))
        
    final_ssim = iterations_history[-1].get("ssim_score", 0.0) if iterations_history else 0.0
    
    return PipelineResult(
        job_id=job_id,
        doc_type=final_state.get("doc_type", "unknown"),
        template_ejs=template_ejs,
        data_json=data_json,
        final_ssim=final_ssim,
        iterations=iterations_list,
        output_dir=out_dir
    )
