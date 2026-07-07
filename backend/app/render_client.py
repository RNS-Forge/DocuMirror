"""
render_client.py
----------------
HTTP client that talks to the Node/Express render service.

The render service accepts:
    POST /render   { "template": "<ejs string>", "data": { ... } }
and returns:
    { "html": "<rendered HTML string>" }

Public API
----------
    render_template(template_ejs, data_dict) -> str   (HTML string)
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import RENDER_SERVICE_URL

logger = logging.getLogger("documirror.render_client")

# Generous timeout – large templates with many table rows can take a moment
_TIMEOUT = httpx.Timeout(30.0, connect=5.0)


def render_template(template_ejs: str, data_dict: dict[str, Any]) -> str:
    """
    Send *template_ejs* and *data_dict* to the Node render service and
    return the rendered HTML string.

    Parameters
    ----------
    template_ejs : str
        Full EJS template string.
    data_dict : dict
        Extracted field values (+ layout sub-dict) to fill the template.

    Returns
    -------
    str
        Rendered HTML.

    Raises
    ------
    httpx.HTTPStatusError
        If the render service returns a non-2xx status code.
    RuntimeError
        If the response JSON does not contain an 'html' key.
    """
    payload = {"template": template_ejs, "data": data_dict}

    logger.debug(
        "POST %s  (template=%d chars, data_keys=%d)",
        RENDER_SERVICE_URL,
        len(template_ejs),
        len(data_dict),
    )

    with httpx.Client(timeout=_TIMEOUT) as client:
        response = client.post(RENDER_SERVICE_URL, json=payload)

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        # Surface the render service error message if available
        try:
            detail = exc.response.json().get("error", exc.response.text)
        except Exception:  # noqa: BLE001
            detail = exc.response.text
        logger.error("Render service returned %d: %s", exc.response.status_code, detail)
        raise RuntimeError(f"Render service error {exc.response.status_code}: {detail}") from exc

    body = response.json()
    if "html" not in body:
        raise RuntimeError(f"Render service response missing 'html' key: {body}")

    html: str = body["html"]
    logger.info("Render OK  (%d chars of HTML)", len(html))
    return html


def check_render_service() -> bool:
    """
    Ping the render service health endpoint.
    Returns True if the service is up, False otherwise.
    """
    health_url = RENDER_SERVICE_URL.rstrip("/render").rstrip("/") + "/health"
    try:
        with httpx.Client(timeout=httpx.Timeout(5.0)) as client:
            r = client.get(health_url)
        ok = r.status_code == 200
        if ok:
            logger.debug("Render service health check: OK")
        else:
            logger.warning("Render service health check failed: HTTP %d", r.status_code)
        return ok
    except Exception as exc:  # noqa: BLE001
        logger.warning("Render service unreachable: %s", exc)
        return False
