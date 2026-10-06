import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
DB_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DATA_DIR / 'app.db'}")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-5-5")
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "25"))
# Configurable retention (GDPR): cases older than this are purged by `python -m app.purge`.
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "365"))

# OCR (Tesseract). Pages with fewer than OCR_MIN_CHARS extracted characters are treated as scans.
OCR_ENABLED = os.environ.get("OCR_ENABLED", "1") != "0"
OCR_LANGS = os.environ.get("OCR_LANGS", "nld+fra+eng")
OCR_DPI = int(os.environ.get("OCR_DPI", "300"))
OCR_MIN_CHARS = int(os.environ.get("OCR_MIN_CHARS", "30"))
OCR_TIMEOUT_S = int(os.environ.get("OCR_TIMEOUT_S", "120"))

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
