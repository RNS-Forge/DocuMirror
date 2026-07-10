def classifier_node(state: dict):
    """
    Inspects the image and determines doc_type: 'ci', 'pl', or 'both'.
    Mutates state to set doc_type.
    """
    image_bytes = state.get("image_bytes")
    
    if image_bytes:
        from app.vision_extraction import classify_document
        doc_type_raw = classify_document(image_bytes)
        if doc_type_raw == "packing_list":
            doc_type = "pl"
        else:
            doc_type = "ci"
    else:
        doc_type = 'ci'
    
    return {"doc_type": doc_type, "status": "classified"}
