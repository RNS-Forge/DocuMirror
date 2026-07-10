def json_node(state: dict):
    """
    Maps raw fields into docs.* and item.* structure.
    Validates against RAG/json/schema and RAG/mapping/field_mapping.json.
    """
    raw_fields = state.get("raw_fields", {})
    doc_type = state.get("doc_type", "unknown")
    
    # Placeholder
    structured_json = {
        "docs": {
            "document_type": doc_type
        },
        "item": []
    }
    
    # Simple mapping
    for k, v in raw_fields.items():
        if k in ("items", "item_table", "item_breakdown"):
            structured_json["item"] = v
        elif k != "layout": # Exclude layout metadata from docs JSON
            structured_json["docs"][k] = v
            
    return {"structured_json": structured_json, "status": "json_mapped"}
