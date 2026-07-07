"""
vision_extraction.py
--------------------
Vision LLM clients with automatic fallback:

    Primary  : Groq  (llama-3.2-90b-vision-preview)
    Fallback : OpenRouter  (google/gemini-2.0-flash-exp:free)

Public API
----------
    extract_document(image_bytes, doc_type_hint, correction_notes) -> DocumentData
    classify_document(image_bytes) -> str   # "commercial_invoice" | "packing_list" | "invoice"
"""

from __future__ import annotations

import base64
import json
import logging
import re
import time
from typing import Optional

import httpx
from groq import Groq, RateLimitError as GroqRateLimitError

from app.config import (
    GROQ_API_KEY,
    GROQ_VISION_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_VISION_MODEL,
    OPENROUTER_VISION_MODEL_2,
)
from app.schemas import (
    CommercialInvoice,
    DocumentData,
    Invoice,
    PackingList,
)

logger = logging.getLogger("documirror.vision_extraction")

# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------
_groq_client = Groq(api_key=GROQ_API_KEY)


def _openrouter_chat(messages: list, model: str = OPENROUTER_VISION_MODEL) -> str:
    """
    Send a chat completion request to OpenRouter and return the assistant message text.
    Uses httpx so we stay dependency-light and can set a generous timeout.
    """
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/documirror",
        "X-Title": "DocuMirror",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 4096,
    }
    logger.debug("OpenRouter request: model=%s", model)
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )
    if resp.status_code != 200:
        logger.error(
            "OpenRouter error %d for model %s: %s",
            resp.status_code, model, resp.text[:300],
        )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

_SCHEMA_HINTS = {
    "commercial_invoice": (
        "exporter, importer, notify_party, invoice_no, invoice_date, iec_no, gst_no, "
        "po_no, lc_no, incoterms, port_of_loading, port_of_discharge, vessel_flight, "
        "country_of_origin, currency, item_table (sr_no, description, hs_code, qty, "
        "unit_price, amount), total_qty, total_value, amount_in_words, freight_charges, "
        "insurance_charges, bank_details (bank_name, account_no, swift_code, iban, branch), "
        "signatory, declaration"
    ),
    "packing_list": (
        "shipper, consignee, notify_party, invoice_ref, bl_no, packing_list_no, date, "
        "port_of_loading, port_of_discharge, vessel_flight, country_of_origin, "
        "package_count, gross_weight, net_weight, dimensions, cbm, marks_and_numbers, "
        "item_breakdown (sr_no, description, hs_code, no_of_packages, package_type, "
        "gross_weight, net_weight, dimensions), signatory, declaration"
    ),
    "invoice": (
        "seller, buyer, ship_to, invoice_no, invoice_date, due_date, po_no, "
        "item_table (sr_no, description, qty, unit_price, amount, tax_rate), "
        "subtotal, discount, tax_label, tax, shipping, total, amount_in_words, "
        "payment_terms, payment_method, "
        "bank_details (bank_name, account_no, swift_code, iban, branch), "
        "notes, signatory"
    ),
}

_LAYOUT_FIELDS = (
    "page_width_px, page_height_px, has_border (bool), header_bg_color (hex or null), "
    "font_family, font_size_body, table_border_style, "
    "column_alignments (list of 'left'|'center'|'right' per item-table column), "
    "bold_labels (bool), two_column_layout (bool)"
)


def _build_extraction_prompt(doc_type: str, correction_notes: str = "") -> str:
    schema_hint = _SCHEMA_HINTS.get(doc_type, _SCHEMA_HINTS["invoice"])
    correction_block = (
        f"\n\nPREVIOUS ITERATION CORRECTIONS REQUIRED:\n{correction_notes}"
        if correction_notes
        else ""
    )
    return (
        f"You are a document data extraction expert. "
        f"The image shows a '{doc_type.replace('_', ' ')}' document.\n\n"
        f"Extract ALL visible field values and return them as a single JSON object "
        f"with two top-level keys:\n"
        f"1. \"fields\" — matching this schema:\n   {schema_hint}\n"
        f"2. \"layout\" — visual/structural metadata:\n   {_LAYOUT_FIELDS}\n\n"
        f"Rules:\n"
        f"- Preserve exact formatting (dates, amounts, codes) as printed.\n"
        f"- For multiline text (addresses, declarations) use '\\n' as line separator.\n"
        f"- If a field is not visible, set it to null.\n"
        f"- item_table / item_breakdown must be a JSON array even if there is only one row.\n"
        f"- Return ONLY the JSON object. No markdown fences, no explanation."
        f"{correction_block}"
    )


def _build_classification_prompt() -> str:
    return (
        "Look at this document image. "
        "Classify it as exactly one of: commercial_invoice, packing_list, invoice.\n"
        "Return a JSON object: {\"doc_type\": \"<one of the three values>\"}. "
        "Return ONLY the JSON. No markdown, no explanation."
    )


# ---------------------------------------------------------------------------
# Core LLM call with Groq → OpenRouter fallback
# ---------------------------------------------------------------------------

def _call_vision_llm(image_bytes: bytes, prompt: str) -> str:
    """
    Send *image_bytes* (PNG) + *prompt* to:
      1. Groq (meta-llama/llama-4-scout-17b-16e-instruct)  ← primary
      2. OpenRouter model 1 (OPENROUTER_VISION_MODEL)       ← fallback
      3. OpenRouter model 2 (OPENROUTER_VISION_MODEL_2)     ← last resort

    Returns the raw text response from whichever provider succeeds first.
    Raises RuntimeError if all three fail.
    """
    b64 = base64.b64encode(image_bytes).decode()
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"},
                },
                {"type": "text", "text": prompt},
            ],
        }
    ]

    # ── 1. Groq ──────────────────────────────────────────────────────────
    try:
        logger.info("Calling Groq vision model: %s", GROQ_VISION_MODEL)
        resp = _groq_client.chat.completions.create(
            model=GROQ_VISION_MODEL,
            messages=messages,  # type: ignore[arg-type]
            temperature=0.1,
            max_tokens=4096,
        )
        text = resp.choices[0].message.content or ""
        logger.debug("Groq response: %d chars", len(text))
        return text
    except GroqRateLimitError as exc:
        logger.warning("Groq rate-limit (%s) — trying OpenRouter fallback 1", exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Groq failed (%s) — trying OpenRouter fallback 1", exc)

    # ── 2. OpenRouter model 1 ─────────────────────────────────────────────
    time.sleep(1)
    try:
        logger.info("OpenRouter fallback 1: %s", OPENROUTER_VISION_MODEL)
        return _openrouter_chat(messages, model=OPENROUTER_VISION_MODEL)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "OpenRouter fallback 1 failed (%s) — trying fallback 2: %s",
            exc, OPENROUTER_VISION_MODEL_2,
        )

    # ── 3. OpenRouter model 2 ─────────────────────────────────────────────
    time.sleep(1)
    try:
        logger.info("OpenRouter fallback 2: %s", OPENROUTER_VISION_MODEL_2)
        return _openrouter_chat(messages, model=OPENROUTER_VISION_MODEL_2)
    except Exception as exc:  # noqa: BLE001
        logger.error("All LLM providers failed. Last error: %s", exc)
        raise RuntimeError(
            f"All vision LLM providers failed. Last error: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# JSON extraction helpers
# ---------------------------------------------------------------------------

def _parse_json_from_response(text: str) -> dict:
    """
    Extract a JSON object from the LLM response.
    Handles models that wrap JSON in ```json … ``` fences.
    """
    # Strip markdown fences if present
    text = text.strip()
    fence_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if fence_match:
        text = fence_match.group(1)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Last-ditch: find the first { … } block
        match = re.search(r"\{[\s\S]+\}", text)
        if match:
            return json.loads(match.group())
        raise ValueError(f"No JSON object found in LLM response:\n{text[:500]}")


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def classify_document(image_bytes: bytes) -> str:
    """
    Ask the vision LLM to classify the document type.

    Returns one of: 'commercial_invoice', 'packing_list', 'invoice'
    Defaults to 'invoice' if the response is unrecognised.
    """
    prompt = _build_classification_prompt()
    raw = _call_vision_llm(image_bytes, prompt)
    try:
        data = _parse_json_from_response(raw)
        doc_type = data.get("doc_type", "invoice").lower().strip()
        valid = {"commercial_invoice", "packing_list", "invoice"}
        if doc_type not in valid:
            logger.warning("Unknown doc_type '%s' from LLM; defaulting to 'invoice'", doc_type)
            return "invoice"
        logger.info("Document classified as: %s", doc_type)
        return doc_type
    except Exception as exc:  # noqa: BLE001
        logger.error("Classification parse error: %s — defaulting to 'invoice'", exc)
        return "invoice"


def extract_document(
    image_bytes: bytes,
    doc_type: str,
    correction_notes: str = "",
) -> DocumentData:
    """
    Extract field values and layout metadata from a document image.

    Parameters
    ----------
    image_bytes : bytes
        PNG bytes of one document page.
    doc_type : str
        One of 'commercial_invoice', 'packing_list', 'invoice'.
    correction_notes : str
        Optional structured mismatch list from the critic LLM to guide re-extraction.

    Returns
    -------
    DocumentData
        A validated Pydantic model (CommercialInvoice | PackingList | Invoice).
    """
    prompt = _build_extraction_prompt(doc_type, correction_notes)
    raw = _call_vision_llm(image_bytes, prompt)

    try:
        parsed = _parse_json_from_response(raw)
    except ValueError as exc:
        logger.error("Failed to parse extraction JSON: %s", exc)
        raise

    fields: dict = parsed.get("fields", parsed)  # some models skip the wrapper
    layout_raw: dict = parsed.get("layout", {}) or {}

    # Merge layout into fields dict for Pydantic validation
    fields["layout"] = layout_raw

    # Ensure doc_type is set correctly
    fields["doc_type"] = doc_type

    logger.info(
        "Extracted %d top-level fields for doc_type='%s'",
        len(fields),
        doc_type,
    )

    _schema_map = {
        "commercial_invoice": CommercialInvoice,
        "packing_list": PackingList,
        "invoice": Invoice,
    }
    schema_cls = _schema_map.get(doc_type, Invoice)

    # Validate — use model_validate with strict=False so extra fields are ignored
    try:
        return schema_cls.model_validate(fields)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Pydantic validation warning for %s: %s — returning partial model",
            schema_cls.__name__,
            exc,
        )
        # Return whatever passes with lax coercion
        return schema_cls.model_construct(**{
            k: v for k, v in fields.items()
            if k in schema_cls.model_fields
        })
