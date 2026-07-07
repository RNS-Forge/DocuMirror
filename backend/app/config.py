"""
Configuration loader.
Reads all settings from .env (backend/.env) via python-dotenv.
No secrets are ever hardcoded here.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Load .env from the backend directory (one level up from app/)
# ---------------------------------------------------------------------------
_ENV_PATH = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH, override=False)


# ---------------------------------------------------------------------------
# Logging setup (console only, no file handlers)
# ---------------------------------------------------------------------------
_LOG_LEVEL_STR = os.getenv("LOG_LEVEL", "INFO").upper()
_LOG_LEVEL = getattr(logging, _LOG_LEVEL_STR, logging.INFO)

logging.basicConfig(
    level=_LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)

logger = logging.getLogger("documirror")


# ---------------------------------------------------------------------------
# LLM providers
# ---------------------------------------------------------------------------
GROQ_API_KEY: str = os.environ["GROQ_API_KEY"]
GROQ_VISION_MODEL: str = os.getenv("GROQ_VISION_MODEL", "llama-3.2-90b-vision-preview")

OPENROUTER_API_KEY: str = os.environ["OPENROUTER_API_KEY"]
OPENROUTER_VISION_MODEL: str = os.getenv(
    "OPENROUTER_VISION_MODEL", "nvidia/nemotron-nano-12b-v2-vl:free"
)
OPENROUTER_VISION_MODEL_2: str = os.getenv(
    "OPENROUTER_VISION_MODEL_2", "google/gemma-4-31b-it:free"
)
OPENROUTER_BASE_URL: str = os.getenv(
    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
)


# ---------------------------------------------------------------------------
# Pipeline parameters
# ---------------------------------------------------------------------------
MAX_CORRECTION_ITERATIONS: int = int(os.getenv("MAX_CORRECTION_ITERATIONS", "3"))
SSIM_THRESHOLD: float = float(os.getenv("SSIM_THRESHOLD", "0.92"))
PDF_RENDER_DPI: int = int(os.getenv("PDF_RENDER_DPI", "250"))


# ---------------------------------------------------------------------------
# Service URLs
# ---------------------------------------------------------------------------
RENDER_SERVICE_URL: str = os.getenv("RENDER_SERVICE_URL", "http://localhost:4000/render")
RENDER_SERVICE_PORT: int = int(os.getenv("RENDER_SERVICE_PORT", "4000"))


# ---------------------------------------------------------------------------
# FastAPI server
# ---------------------------------------------------------------------------
BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8000"))


# ---------------------------------------------------------------------------
# File system paths (all temp; nothing persisted after job completes)
# ---------------------------------------------------------------------------
_BASE = Path(__file__).parent.parent          # backend/
TEMP_UPLOAD_DIR: Path = (_BASE / os.getenv("TEMP_UPLOAD_DIR", "./tmp/uploads")).resolve()
OUTPUT_DIR: Path = (_BASE / os.getenv("OUTPUT_DIR", "./tmp/outputs")).resolve()

# Ensure directories exist at startup
TEMP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Base templates directory shipped with the project
TEMPLATES_DIR: Path = (_BASE / "templates").resolve()
