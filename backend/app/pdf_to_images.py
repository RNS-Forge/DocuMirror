"""
pdf_to_images.py
----------------
Convert each page of a PDF file into a PNG image using PyMuPDF (fitz).

Returns a list of in-memory PNG bytes objects so the rest of the pipeline
never needs to touch the filesystem for page images.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

import fitz  # PyMuPDF

from app.config import PDF_RENDER_DPI

logger = logging.getLogger("documirror.pdf_to_images")


def pdf_to_images(pdf_path: str | Path, dpi: int = PDF_RENDER_DPI) -> List[bytes]:
    """
    Convert every page of *pdf_path* to a PNG at *dpi* resolution.

    Parameters
    ----------
    pdf_path : str | Path
        Absolute path to the PDF file.
    dpi : int
        Render resolution (dots-per-inch).  Defaults to PDF_RENDER_DPI from config.

    Returns
    -------
    List[bytes]
        One PNG bytes object per page, in page order.

    Raises
    ------
    FileNotFoundError
        If *pdf_path* does not exist.
    fitz.FileDataError
        If the file is not a valid / readable PDF.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    logger.info("Opening PDF: %s  (DPI=%d)", pdf_path.name, dpi)

    # zoom factor: PDF internal unit is 72 dpi
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    images: List[bytes] = []

    with fitz.open(str(pdf_path)) as doc:
        page_count = len(doc)
        logger.info("PDF has %d page(s)", page_count)

        for page_index in range(page_count):
            page = doc.load_page(page_index)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            png_bytes: bytes = pix.tobytes("png")
            images.append(png_bytes)
            logger.debug(
                "Page %d/%d  →  %dx%d px  (%d bytes)",
                page_index + 1,
                page_count,
                pix.width,
                pix.height,
                len(png_bytes),
            )

    logger.info("Converted %d page(s) to PNG", len(images))
    return images


def pdf_page_count(pdf_path: str | Path) -> int:
    """Return the number of pages in a PDF without rendering them."""
    with fitz.open(str(pdf_path)) as doc:
        return len(doc)
