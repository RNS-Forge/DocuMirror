# DocuMirror

Convert an uploaded PDF (commercial invoice, packing list, or generic invoice) into:

1. **`template.ejs`** — an EJS template that matches the document's visual layout
2. **`data.json`** — extracted field values

Rendering `EJS(data.json)` reproduces the original PDF page as closely as possible.

---

## Architecture

```
Browser / curl
     │
     ▼
FastAPI (Python 8000)          ← orchestrates the whole pipeline
  ├── PyMuPDF                  ← PDF → PNG pages
  ├── Groq API (vision LLM)    ← field + layout extraction  (primary)
  ├── OpenRouter API           ← fallback vision LLM
  ├── Node/Express (4000)      ← EJS render service
  ├── Playwright               ← headless Chromium screenshot
  ├── scikit-image SSIM        ← numeric visual diff
  ├── Groq/OpenRouter critic   ← structured mismatch detection
  └── LangGraph                ← generator → render → critic loop
```

---

## Prerequisites

| Tool | Minimum version |
|------|----------------|
| Python | 3.11 |
| Node.js | 18 |
| npm | 9 |

---

## Setup

### 1. Clone / open the project

```
cd "DocuMirror"
```

### 2. Configure environment variables

The `.env` file is already pre-filled with your API keys at `backend/.env`.
Edit it if you need to change any values:

```
backend/.env
```

Key variables:

| Variable | Description |
|----------|-------------|
| `GROQ_API_KEY` | Groq free-tier API key |
| `GROQ_VISION_MODEL` | `llama-3.2-90b-vision-preview` |
| `OPENROUTER_API_KEY` | OpenRouter free-tier API key |
| `OPENROUTER_VISION_MODEL` | `google/gemini-2.0-flash-exp:free` |
| `SSIM_THRESHOLD` | Stop loop when SSIM ≥ this (default `0.92`) |
| `MAX_CORRECTION_ITERATIONS` | Max correction loops (default `3`) |
| `PDF_RENDER_DPI` | Resolution for PDF → PNG (default `250`) |

### 3. Python backend

```bash
cd backend

# Create and activate a virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright's Chromium browser (one-time)
playwright install chromium
```

### 4. Node render service

```bash
cd render-service
npm install
```

---

## Running

Open **two terminals**.

### Terminal 1 — Node render service

```bash
cd render-service
npm start
# Listening on http://127.0.0.1:4000
```

### Terminal 2 — FastAPI backend

```bash
cd backend
# Activate venv first (see Setup step 3)
python -m app.main
# or:
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Usage

### Extract template + data from a PDF

```bash
curl -X POST http://localhost:8000/extract \
  -F "file=@/path/to/your/invoice.pdf" \
  -o result.json
```

**Response shape:**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "doc_type": "commercial_invoice",
  "template_ejs": "<!DOCTYPE html>...",
  "data_json": {
    "invoice_no": "INV-2024-001",
    "invoice_date": "01-Jan-2024",
    "exporter": "ACME Corp\n123 Export St",
    "item_table": [
      { "description": "Widget A", "qty": "100 PCS", "unit_price": "USD 5.00", "amount": "USD 500.00" }
    ],
    "total_value": "USD 500.00"
  },
  "final_ssim": 0.9341,
  "iterations": [
    { "iteration": 1, "ssim_score": 0.8812, "mismatch_count": 4 },
    { "iteration": 2, "ssim_score": 0.9341, "mismatch_count": 0 }
  ],
  "message": "OK"
}
```

### Preview the rendered screenshot

```bash
curl http://localhost:8000/extract/{job_id}/preview -o preview.png
```

> **Note:** The preview is only available immediately after extraction while the temp directory still exists. It is deleted after the first preview request.

### Health check

```bash
curl http://localhost:8000/health
# {"status":"ok","render_service":"up"}
```

---

## Project structure

```
DocuMirror/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app + endpoints
│   │   ├── schemas.py           # Pydantic models for 3 doc types
│   │   ├── config.py            # .env loader + path constants
│   │   ├── pdf_to_images.py     # PDF → PNG via PyMuPDF
│   │   ├── vision_extraction.py # Groq + OpenRouter vision LLM clients
│   │   ├── template_engine.py   # EJS template selection + CSS injection
│   │   ├── render_client.py     # HTTP client for Node render service
│   │   ├── visual_diff.py       # SSIM + Playwright screenshot
│   │   ├── critic.py            # Mismatch detection LLM call
│   │   └── orchestrator.py      # LangGraph state machine
│   ├── templates/
│   │   ├── commercial_invoice.ejs
│   │   ├── packing_list.ejs
│   │   └── invoice.ejs
│   ├── tmp/
│   │   ├── uploads/             # Temp PDF uploads (auto-deleted)
│   │   └── outputs/             # Temp job outputs (auto-deleted)
│   ├── requirements.txt
│   └── .env
└── render-service/
    ├── server.js                # Express + EJS render endpoint
    └── package.json
```

---

## Design notes

- **No database, no persistent logging.** All job state lives in the LangGraph `PipelineState` TypedDict for the duration of one request and is discarded when the request returns.
- **Free-tier only.** All LLM calls use Groq free tier (primary) and OpenRouter free models (fallback). No paid API calls.
- **Groq rate-limit handling.** `vision_extraction.py` and `critic.py` automatically fall back to OpenRouter on `RateLimitError`.
- **SSIM loop.** The pipeline iterates up to `MAX_CORRECTION_ITERATIONS` times, stopping early when `SSIM >= SSIM_THRESHOLD` or the critic reports zero mismatches.
- **Template strategy.** Base EJS templates use conditionals for optional sections. Only CSS overrides (colours, fonts, alignments) are dynamically injected per document — the full template is never regenerated from scratch.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Node render service not reachable` | Run `cd render-service && npm start` in a separate terminal |
| `playwright install` fails | Run `playwright install-deps chromium` then retry |
| Groq `RateLimitError` at every call | The system automatically falls back to OpenRouter — check your `OPENROUTER_API_KEY` |
| SSIM stays low after 3 iterations | The base template may need manual adjustment for an unusual document layout |
| `fitz` import error | Install with `pip install PyMuPDF` (the package name differs from the import name) |
