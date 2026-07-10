import os
from typing import Dict, Any

class DocuMirrorChatbot:
    """
    DocuMirror Chatbot Agent.
    In a fully configured environment, this would initialize a LangChain
    agent with access to Groq/OpenRouter and RAG tools.
    For this setup, it gracefully falls back to intelligent mock responses.
    """
    def __init__(self):
        self.name = "DocuMirror"
        self.api_key = os.getenv("GROQ_API_KEY", "")

    def invoke(self, message: str) -> str:
        # If no real API key is set, return intelligent mock responses formatted in Markdown
        msg = message.lower()
        
        if "name" in msg or "who are you" in msg or "hi" in msg or "hello" in msg:
            return f"Hey there! 😊 I am **{self.name}**, your friendly AI assistant and buddy by RNS Solutions. I specialize in document extraction, template generation, and JSON schema validation. How can I help you today?"
            
        if "code" in msg or "python" in msg or "example" in msg:
            return f"""Sure, here is an example of some code for you to review.

```python
def extract_document(file_path: str) -> dict:
    \"\"\"
    DocuMirror mock extraction function.
    \"\"\"
    print(f"Extracting data from: {{file_path}}")
    return {{
        "status": "success",
        "confidence": 0.99,
        "doc_type": "commercial_invoice"
    }}
```

You can use the **Copy Code** button on the top right of the code block above to copy it!"""
        
        if "html" in msg or "colspan" in msg or "rowspan" in msg:
            return "Based on the RAG templates, `colspan` and `rowspan` are dynamically assigned based on the `layout_variant` (e.g., sea vs air freight). The JSON Agent ensures the data structure matches these visual merged cells."
            
        if "json" in msg or "schema" in msg:
            return "The current JSON schema enforces the `docs.*` prefix for document-level fields and `item.*` for repeating table rows. You can find the mapping in `RAG/mapping/field_mapping.json`."

        # Default fallback response with MCQ
        return (
            f"Hey my friend! 😊 I received your message: *\"{message}\"*\n\n"
            f"I'm a little bit in doubt about exactly what you need right now. Could you clarify by picking one of the following options?\n\n"
            f"**A.** I need some code examples\n"
            f"**B.** Help with document extraction queries\n"
            f"**C.** JSON schema formatting or templates\n"
            f"**D.** Just wanted to say hi!"
        )

# Singleton instance
chat_agent = DocuMirrorChatbot()

def process_chat(message: str) -> str:
    return chat_agent.invoke(message)
