"""
G-lassify Configuration
Loads environment variables and defines project-wide constants.
"""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# ── Paths ──────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS_FILE = PROJECT_ROOT / "credentials.json"
TOKEN_FILE = PROJECT_ROOT / "token.json"
TEMPLATES_DIR = PROJECT_ROOT / "templates"

# ── Load .env ──────────────────────────────────────────────────────────────
load_dotenv(PROJECT_ROOT / ".env")

# ── Required Settings ──────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "").strip()

# ── Optional Settings ─────────────────────────────────────────────────────
EMAIL_BODY_MAX_CHARS = int(os.getenv("EMAIL_BODY_MAX_CHARS", "2000"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# ── Gmail API Scopes ───────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

# ── Logging Setup ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("glassify")


def validate_config():
    """Verify that all required configuration is present."""
    errors = []
    if not GEMINI_API_KEY:
        errors.append("GEMINI_API_KEY is not set in .env")
    if not GMAIL_ADDRESS:
        errors.append("GMAIL_ADDRESS is not set in .env")
    if not CREDENTIALS_FILE.exists():
        errors.append(
            f"credentials.json not found at {CREDENTIALS_FILE}\n"
            "  → Download it from Google Cloud Console > APIs & Services > Credentials"
        )
    if errors:
        for err in errors:
            logger.error(f"Configuration error: {err}")
        sys.exit(1)
    logger.info("Configuration validated successfully")
