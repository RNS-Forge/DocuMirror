"""
critic.py
---------
LLM-based visual critic that compares the original document page image
against the rendered screenshot and returns a structured list of mismatches.

The critic uses the same Groq → OpenRouter fallback chain as vision_extraction.

Public API
----------
    run_critic(original_image_bytes, rendered_image_bytes) -> CriticResponse
"""

from __future__ import annotations

import base64
import json
import logging
import re
import time

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
from app.schemas import CriticResponse, MismatchItem

logger = logging.getLogger("documirror.critic")

_groq_client = Groq(api_key=GROQ_API_KEY)

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_CRITIC_PROMPT = """You are a document layout quality-control expert.

You are given TWO images:
  Image 1 (left / first):  the ORIGINAL scanned/exported PDF page (ground truth)
  Image 2 (right / second): the RENDERED HTML reproduction

Compare them carefully and list every visual mismatch you can find.

For each mismatch return a JSON object with these fields:
  - "category": one of:
      missing_field | wrong_value | wrong_position | wrong_alignment |
      wrong_table_column | missing_table_row | wrong_font_style |
      wrong_color | other
  - "field_name": the label or field name where the issue occurs (string or null)
  - "expected":   what the original shows (string or null)
  - "actual":     what the rendered version shows (string or null)
  - "suggested_fix": a concrete CSS rule or text change that would fix it (string or null)

Return a JSON object:
{
  "mismatches": [ ...list of mismatch objects... ],
  "overall_assessment": "<one sentence summary>"
}

If there are NO mismatches, return: {"mismatches": [], "overall_assessment": "Perfect match."}

Return ONLY the JSON object. No markdown fences, no explanation."""


# ---------------------------------------------------------------------------
# LLM helpers (duplicated locally to keep this module self-contained)
# ---------------------------------------------------------------------------

def _encode(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode()


def _openrouter_chat(messages: list, model: str = OPENROUTER_VISION_MODEL) -> str:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/documirror",
        "X-Title": "DocuMirror-Critic",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 2048,
    }
    logger.debug("Critic OpenRouter request: model=%s", model)
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )
    if resp.status_code != 200:
        logger.error(
            "Critic OpenRouter error %d for model %s: %s",
            resp.status_code, model, resp.text[:300],
        )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _call_critic_llm(original_bytes: bytes, rendered_bytes: bytes) -> str:
    """
    Send both images to the vision LLM with the critic prompt.
    3-tier fallback: Groq → OpenRouter model 1 → OpenRouter model 2.
    """
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{_encode(original_bytes)}"},
                },
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{_encode(rendered_bytes)}"},
                },
                {"type": "text", "text": _CRITIC_PROMPT},
            ],
        }
    ]

    # ── 1. Groq ──────────────────────────────────────────────────────────
    try:
        logger.info("Critic: calling Groq model %s", GROQ_VISION_MODEL)
        resp = _groq_client.chat.completions.create(
            model=GROQ_VISION_MODEL,
            messages=messages,  # type: ignore[arg-type]
            temperature=0.1,
            max_tokens=2048,
        )
        return resp.choices[0].message.content or ""
    except GroqRateLimitError as exc:
        logger.warning("Critic: Groq rate-limit (%s) — trying OpenRouter fallback 1", exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Critic: Groq failed (%s) — trying OpenRouter fallback 1", exc)

    # ── 2. OpenRouter model 1 ─────────────────────────────────────────────
    time.sleep(1)
    try:
        logger.info("Critic: OpenRouter fallback 1: %s", OPENROUTER_VISION_MODEL)
        return _openrouter_chat(messages, model=OPENROUTER_VISION_MODEL)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Critic: OpenRouter fallback 1 failed (%s) — trying fallback 2: %s",
            exc, OPENROUTER_VISION_MODEL_2,
        )

    # ── 3. OpenRouter model 2 ─────────────────────────────────────────────
    time.sleep(1)
    try:
        logger.info("Critic: OpenRouter fallback 2: %s", OPENROUTER_VISION_MODEL_2)
        return _openrouter_chat(messages, model=OPENROUTER_VISION_MODEL_2)
    except Exception as exc:  # noqa: BLE001
        logger.error("Critic: all LLM providers failed. Last error: %s", exc)
        raise RuntimeError(f"All vision LLM providers failed in critic: {exc}") from exc


def _parse_critic_json(text: str) -> dict:
    """Strip markdown fences and parse JSON from the critic LLM response."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if fence:
        text = fence.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]+\}", text)
        if match:
            return json.loads(match.group())
        raise ValueError(f"No JSON object in critic response:\n{text[:500]}")


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------

def run_critic(
    original_image_bytes: bytes,
    rendered_image_bytes: bytes,
) -> CriticResponse:
    """
    Compare the original PDF page image with the rendered HTML screenshot
    and return a structured list of visual mismatches.

    Parameters
    ----------
    original_image_bytes : bytes
        PNG bytes of the original PDF page.
    rendered_image_bytes : bytes
        PNG bytes of the Playwright screenshot of the rendered template.

    Returns
    -------
    CriticResponse
        Pydantic model with a `mismatches` list and `overall_assessment` string.
    """
    logger.info("Running visual critic comparison")
    raw = _call_critic_llm(original_image_bytes, rendered_image_bytes)

    try:
        data = _parse_critic_json(raw)
    except ValueError as exc:
        logger.error("Critic parse failed: %s", exc)
        # Return an empty critic response rather than crashing the loop
        return CriticResponse(
            mismatches=[],
            overall_assessment="Critic parse error — treating as no mismatches.",
        )

    mismatches_raw = data.get("mismatches", [])
    mismatches: list[MismatchItem] = []

    for item in mismatches_raw:
        try:
            mismatches.append(MismatchItem.model_validate(item))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Skipping invalid mismatch item %s: %s", item, exc)

    assessment: str = data.get("overall_assessment", "")
    logger.info(
        "Critic found %d mismatch(es): %s", len(mismatches), assessment
    )

    return CriticResponse(mismatches=mismatches, overall_assessment=assessment)


def mismatches_to_correction_notes(critic_response: CriticResponse) -> str:
    """
    Convert a CriticResponse into a plain-text correction prompt to be
    appended to the next extraction call.

    Returns a concise bullet-list string the vision LLM can act on.
    """
    if not critic_response.mismatches:
        return ""

    lines = ["Fix the following issues found in the previous render:"]
    for i, m in enumerate(critic_response.mismatches, 1):
        parts = [f"{i}. [{m.category}]"]
        if m.field_name:
            parts.append(f"Field: {m.field_name}.")
        if m.expected:
            parts.append(f"Expected: {m.expected}.")
        if m.actual:
            parts.append(f"Got: {m.actual}.")
        if m.suggested_fix:
            parts.append(f"Fix: {m.suggested_fix}.")
        lines.append(" ".join(parts))

    return "\n".join(lines)
