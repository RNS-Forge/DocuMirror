import os
from pathlib import Path
import chromadb
from chromadb.utils import embedding_functions

CHROMA_DB_DIR = Path(__file__).parent.parent / "chroma_db"
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

def build_vector_store():
    """
    Builds the vector store using ChromaDB by indexing EJS templates.
    """
    print("Initializing ChromaDB...")
    client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
    
    # Use default embedding function
    emb_fn = embedding_functions.DefaultEmbeddingFunction()
    
    collection = client.get_or_create_collection(
        name="documirror_templates",
        embedding_function=emb_fn
    )
    
    # Clear old items if re-running
    if collection.count() > 0:
        # Instead of deleting with where={}, which errors in some versions,
        # get all ids and delete them.
        all_items = collection.get()
        if all_items["ids"]:
            collection.delete(ids=all_items["ids"])
    
    docs = []
    metadatas = []
    ids = []
    
    # 1. Index the HTML rules
    rules_file = Path(__file__).parent / "html_rules.md"
    if rules_file.exists():
        rules_content = rules_file.read_text(encoding="utf-8")
        docs.append(rules_content)
        metadatas.append({"doc_type": "global", "chunk_type": "html_rules"})
        ids.append("global_html_rules")
    
    # 2. Index the EJS templates
    for ejs_file in TEMPLATES_DIR.glob("*.ejs"):
        content = ejs_file.read_text(encoding="utf-8")
        
        # Simple chunking: take the <style> block and <table> block
        style_start = content.find("<style>")
        style_end = content.find("</style>")
        if style_start != -1 and style_end != -1:
            style_content = content[style_start:style_end+8]
            docs.append(style_content)
            metadatas.append({"doc_type": ejs_file.stem, "chunk_type": "style"})
            ids.append(f"{ejs_file.stem}_style")
            
        table_start = content.find("<table>")
        table_end = content.find("</table>")
        if table_start != -1 and table_end != -1:
            table_content = content[table_start:table_end+8]
            docs.append(table_content)
            metadatas.append({"doc_type": ejs_file.stem, "chunk_type": "table"})
            ids.append(f"{ejs_file.stem}_table")
            
    if docs:
        print(f"Adding {len(docs)} structural chunks to ChromaDB...")
        collection.add(
            documents=docs,
            metadatas=metadatas,
            ids=ids
        )
        print("Vector store indexing complete. Items in DB:", collection.count())
    else:
        print("No chunks found to index.")

def query_vector_store(query_text: str, n_results: int = 1) -> str:
    """Helper to query the vector store."""
    client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
    emb_fn = embedding_functions.DefaultEmbeddingFunction()
    try:
        collection = client.get_collection(name="documirror_templates", embedding_function=emb_fn)
        results = collection.query(query_texts=[query_text], n_results=n_results)
        if results['documents'] and len(results['documents']) > 0:
            return "\n\n".join(results['documents'][0])
    except Exception as e:
        print(f"ChromaDB query failed: {e}")
    return ""

if __name__ == "__main__":
    build_vector_store()
