"""
visual_diff.py
--------------
Compute Structural Similarity Index (SSIM) between two document images.

Workflow
--------
1.  The original page image (PNG bytes from PyMuPDF) is the *reference*.
2.  A Playwright screenshot of the rendered HTML is the *candidate*.
3.  Both are decoded to numpy arrays, converted to greyscale, resized to the
    same dimensions, then passed to skimage.metrics.structural_similarity.

Public API
----------
    compute_ssim(ref_image_bytes, candidate_image_bytes) -> float
    screenshot_html(html)                               -> bytes  (PNG)
"""

from __future__ import annotations

import asyncio
import logging
from io import BytesIO

import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity as sk_ssim

logger = logging.getLogger("documirror.visual_diff")


# ---------------------------------------------------------------------------
# Playwright screenshot
# ---------------------------------------------------------------------------

async def _screenshot_html_async(html: str) -> bytes:
    """
    Render *html* in a headless Chromium browser and return a PNG screenshot.
    The viewport is set to A4 width (794 px) with auto height so the full page
    is captured even when content overflows.
    """
    from playwright.async_api import async_playwright  # lazy import

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 794, "height": 1123},  # A4 at 96 dpi
        )
        page = await context.new_page()
        # Set HTML content directly — no network round-trip needed
        await page.set_content(html, wait_until="networkidle")
        # Full-page screenshot captures overflow content
        png_bytes: bytes = await page.screenshot(full_page=True)
        await browser.close()

    logger.debug("Screenshot captured  (%d bytes)", len(png_bytes))
    return png_bytes


def screenshot_html(html: str) -> bytes:
    """
    Synchronous wrapper around the async Playwright screenshot helper.

    Always runs Playwright in a **brand-new thread** with its own event loop.
    This is safe whether called from a sync context, an async context
    (FastAPI/uvicorn), or a LangGraph node — it never touches the caller's
    event loop, so ``asyncio.run()`` inside the thread never raises
    "cannot be called from a running event loop".

    Parameters
    ----------
    html : str
        Fully rendered HTML string.

    Returns
    -------
    bytes
        PNG screenshot bytes.
    """
    import concurrent.futures

    result_holder: list[bytes] = []
    error_holder:  list[BaseException] = []

    def _run_in_new_loop() -> None:
        """
        Target function for the worker thread — owns its own event loop.

        On Windows the default SelectorEventLoop does not support
        subprocess creation (needed by Playwright to launch Chromium).
        We explicitly use ProactorEventLoop on Windows so that
        asyncio.create_subprocess_exec works correctly.
        """
        import sys
        if sys.platform == "win32":
            loop = asyncio.ProactorEventLoop()
        else:
            loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            png = loop.run_until_complete(_screenshot_html_async(html))
            result_holder.append(png)
        except Exception as exc:  # noqa: BLE001
            error_holder.append(exc)
        finally:
            loop.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(_run_in_new_loop)
        fut.result(timeout=90)          # propagates any thread exception

    if error_holder:
        raise error_holder[0]

    return result_holder[0]


# ---------------------------------------------------------------------------
# SSIM computation
# ---------------------------------------------------------------------------

def _load_greyscale(image_bytes: bytes) -> np.ndarray:
    """Decode PNG bytes to a float32 greyscale numpy array in [0, 1]."""
    img = Image.open(BytesIO(image_bytes)).convert("L")
    return np.array(img, dtype=np.float32) / 255.0


def _resize_to_match(arr_a: np.ndarray, arr_b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Resize *arr_b* to the same shape as *arr_a* using PIL so SSIM is always
    comparing arrays of identical dimensions.
    """
    if arr_a.shape == arr_b.shape:
        return arr_a, arr_b

    h, w = arr_a.shape
    # Reconstruct PIL Image from array, resize, convert back
    img_b = Image.fromarray((arr_b * 255).astype(np.uint8)).resize(
        (w, h), Image.LANCZOS
    )
    resized = np.array(img_b, dtype=np.float32) / 255.0
    logger.debug(
        "Resized candidate from %s to %s for SSIM comparison",
        arr_b.shape,
        resized.shape,
    )
    return arr_a, resized


def compute_ssim(
    ref_image_bytes: bytes,
    candidate_image_bytes: bytes,
) -> float:
    """
    Compute the SSIM score between a reference image and a candidate image.

    Parameters
    ----------
    ref_image_bytes : bytes
        PNG bytes of the original PDF page (ground truth).
    candidate_image_bytes : bytes
        PNG bytes of the Playwright-rendered screenshot.

    Returns
    -------
    float
        SSIM score in [0, 1].  Higher is better; 1.0 = identical.
    """
    ref = _load_greyscale(ref_image_bytes)
    cand = _load_greyscale(candidate_image_bytes)
    ref, cand = _resize_to_match(ref, cand)

    # data_range=1.0 because our arrays are normalised to [0, 1]
    score: float = float(sk_ssim(ref, cand, data_range=1.0))
    logger.info("SSIM score: %.4f", score)
    return score
