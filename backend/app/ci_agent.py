def ci_node(state: dict):
    """
    1. Queries RAG (ci/embeddings) for structurally similar templates.
    2. Extracts raw field values from the image.
    3. Maps extracted values to the template.
    If mismatches > 0, corrects the draft instead of generating a new one.
    """
    mismatches = state.get("mismatches", [])
    image_bytes = state.get("image_bytes")
    
    if image_bytes:
        from app.vision_extraction import extract_document
        from app.template_engine import get_template
        from app.rag_indexer import query_vector_store
        
        # Query RAG for structural hints based on document type
        rag_hints = query_vector_store("commercial invoice structural layout tables")
        
        correction_notes = "\n".join(mismatches) if mismatches else ""
        if rag_hints:
            correction_notes += f"\n\nAdditional structural context from RAG:\n{rag_hints}"
            
        data = extract_document(image_bytes, "commercial_invoice", correction_notes)
        raw_fields = data.model_dump()
        # Mismatches in state are List[str] currently (from mock verifier)
        draft_html = get_template("commercial_invoice", data, []) 
    else:
        draft_html = "<html><body><h1>Commercial Invoice</h1></body></html>"
        raw_fields = {"invoice_number": "INV-123", "items": []}

    return {"draft_html": draft_html, "raw_fields": raw_fields, "status": "ci_drafted"}
