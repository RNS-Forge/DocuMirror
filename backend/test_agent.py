import os
import sys
from pathlib import Path
from app.agent_orchestrator import run_pipeline

def test_pipeline():
    base_dir = Path("..")
    pdfs = list(base_dir.rglob("*.pdf"))
    if not pdfs:
        print("No PDF found to test with. Creating a dummy file won't work with PyMuPDF directly.")
        return
        
    print(f"Testing with {pdfs[0]}")
    try:
        res = run_pipeline(pdfs[0])
        print("Pipeline finished successfully!")
        print("Doc type:", res.doc_type)
    except Exception as e:
        print("Pipeline failed:", str(e))

if __name__ == "__main__":
    test_pipeline()
