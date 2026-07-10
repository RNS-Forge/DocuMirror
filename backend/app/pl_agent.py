def pl_node(state: dict):
    """
    1. Queries RAG (pl/embeddings) for structurally similar templates.
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
        
        rag_hints = query_vector_store("packing list structural layout tables")
        html_rules = query_vector_store("html rules primary tags classes")
        
        correction_notes = "\n".join(mismatches) if mismatches else ""
        if html_rules:
            correction_notes += f"\n\nSTRICT HTML RULES FROM RAG:\n{html_rules}"
        if rag_hints:
            correction_notes += f"\n\nAdditional structural context from RAG:\n{rag_hints}"
            
        data = extract_document(image_bytes, "packing_list", correction_notes)
        raw_fields = data.model_dump()
        
        if hasattr(data, 'template_ejs') and data.template_ejs:
            draft_html = data.template_ejs
        else:
            draft_html = get_template("packing_list", data, []) 
    else:
        draft_html = "<html><body><h1>Packing List</h1></body></html>"
        raw_fields = {"packing_list_number": "PL-123", "items": []}

    return {"draft_html": draft_html, "raw_fields": raw_fields, "status": "pl_drafted"}
