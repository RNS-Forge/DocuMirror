"""
template_engine.py
------------------
Handles EJS template selection and partial regeneration.

Strategy
--------
1.  We keep three *hand-built* base templates (one per doc type) in /templates/.
2.  The base templates use EJS conditionals (<% if (...) { %>) so optional sections
    (notify_party, freight, bank details, etc.) are automatically shown / hidden
    based on the extracted data — no template regeneration needed for those.
3.  The only thing we might need to regenerate is the CSS overrides section, which
    is a small <style> block injected into the template's <head> to apply
    layout-specific values (colors, borders, fonts) discovered by the vision LLM.
4.  `get_template(doc_type, data, mismatches)` returns a ready-to-render EJS string.

Public API
----------
    get_template(doc_type, data, mismatches) -> str
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from app.config import TEMPLATES_DIR
from app.schemas import DocumentData, LayoutMeta, MismatchItem

logger = logging.getLogger("documirror.template_engine")

# Mapping from doc_type string to base template filename
_TEMPLATE_FILES: dict[str, str] = {
    "commercial_invoice": "commercial_invoice.ejs",
    "packing_list": "packing_list.ejs",
    "invoice": "invoice.ejs",
}

# Default layout to inject when the LLM didn't return one
_DEFAULT_LAYOUT = LayoutMeta()


def _load_base_template(doc_type: str) -> str:
    """Load and return the base EJS template string for *doc_type*."""
    filename = _TEMPLATE_FILES.get(doc_type)
    if not filename:
        logger.warning(
            "Unknown doc_type '%s', falling back to 'invoice' template", doc_type
        )
        filename = _TEMPLATE_FILES["invoice"]

    path = TEMPLATES_DIR / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Base template not found: {path}. "
            "Ensure the /templates directory is present."
        )
    return path.read_text(encoding="utf-8")


def _build_css_overrides(layout: LayoutMeta, mismatches: List[MismatchItem]) -> str:
    """
    Build a small <style> block of CSS overrides derived from *layout* metadata
    and any colour / font / alignment corrections requested by the critic.

    Returns an HTML <style>…</style> string (may be empty if nothing to override).
    """
    rules: list[str] = []

    # Header background colour (e.g. company logo bar)
    if layout.header_bg_color:
        rules.append(
            f".doc-header {{ background-color: {layout.header_bg_color}; "
            f"color: #fff; padding: 12px; }}"
        )

    # Apply critic-requested colour or font corrections
    for m in mismatches:
        if m.category == "wrong_color" and m.suggested_fix:
            rules.append(f"/* critic fix: {m.field_name} */ {m.suggested_fix}")
        elif m.category == "wrong_font_style" and m.suggested_fix:
            rules.append(f"/* critic fix: {m.field_name} */ {m.suggested_fix}")

    if not rules:
        return ""

    lines = "\n  ".join(rules)
    return f"\n<style>\n  /* ---- critic / layout overrides ---- */\n  {lines}\n</style>"


def _inject_css_overrides(template: str, css_block: str) -> str:
    """
    Insert *css_block* just before </head> in *template*.
    If </head> is not found, append at the end of the string.
    """
    if not css_block:
        return template
    marker = "</head>"
    if marker in template:
        return template.replace(marker, css_block + "\n" + marker, 1)
    return template + css_block


def _apply_alignment_overrides(
    template: str,
    layout: LayoutMeta,
    mismatches: List[MismatchItem],
) -> str:
    """
    If the critic flagged wrong_alignment mismatches, inject inline CSS overrides
    into the template string by appending a targeted <style> block.
    """
    alignment_fixes: list[str] = []
    for m in mismatches:
        if m.category == "wrong_alignment" and m.field_name and m.suggested_fix:
            alignment_fixes.append(
                f"/* alignment fix: {m.field_name} */ {m.suggested_fix}"
            )

    # Also honour column_alignments from layout for the item table
    if layout.column_alignments:
        for i, align in enumerate(layout.column_alignments):
            col_n = i + 2  # first col is sr_no (1-indexed in CSS nth-child)
            alignment_fixes.append(
                f"table td:nth-child({col_n}), "
                f"table th:nth-child({col_n}) {{ text-align: {align.value}; }}"
            )

    if not alignment_fixes:
        return template

    lines = "\n  ".join(alignment_fixes)
    css = f"\n<style>\n  /* ---- alignment overrides ---- */\n  {lines}\n</style>"
    return _inject_css_overrides(template, css)


def get_template(
    doc_type: str,
    data: DocumentData,
    mismatches: Optional[List[MismatchItem]] = None,
) -> str:
    """
    Return a ready-to-render EJS template string for *doc_type*.

    The base template already handles optional-section toggling via EJS
    conditionals, so we only need to inject CSS overrides derived from
    the extracted layout metadata and any critic-reported mismatches.

    Parameters
    ----------
    doc_type : str
        One of 'commercial_invoice', 'packing_list', 'invoice'.
    data : DocumentData
        Validated Pydantic model with extracted field values + layout metadata.
    mismatches : list[MismatchItem] | None
        Critic-reported mismatches from the previous iteration (if any).

    Returns
    -------
    str
        EJS template string ready to be sent to the render service.
    """
    mismatches = mismatches or []
    layout: LayoutMeta = getattr(data, "layout", None) or _DEFAULT_LAYOUT

    logger.info(
        "Building template for doc_type='%s'  (mismatches=%d)",
        doc_type,
        len(mismatches),
    )

    template = _load_base_template(doc_type)

    # CSS overrides from layout metadata + critic colour/font fixes
    css_override = _build_css_overrides(layout, mismatches)
    template = _inject_css_overrides(template, css_override)

    # Alignment overrides
    template = _apply_alignment_overrides(template, layout, mismatches)

    return template


def template_path(doc_type: str) -> Path:
    """Return the filesystem path of the base template (for debugging / tests)."""
    filename = _TEMPLATE_FILES.get(doc_type, _TEMPLATE_FILES["invoice"])
    return TEMPLATES_DIR / filename
