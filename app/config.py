import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
def _db_url() -> str:
    url = os.environ.get("DATABASE_URL") or f"sqlite:///{DATA_DIR / 'app.db'}"
    # Render/Heroku hand out postgres:// URLs; SQLAlchemy needs the driver spelled out.
    for old in ("postgres://", "postgresql://"):
        if url.startswith(old):
            return "postgresql+psycopg://" + url[len(old):]
    return url


DB_URL = _db_url()
APP_ENV = os.environ.get("APP_ENV", "development")  # "production" enforces secrets below
# Files at rest are encrypted when set. LOSING THIS KEY MAKES UPLOADED FILES UNRECOVERABLE.
FILE_ENCRYPTION_KEY = os.environ.get("FILE_ENCRYPTION_KEY")
# Registration: "open" (anyone) or "invite" (requires INVITE_CODE).
INVITE_CODE = os.environ.get("INVITE_CODE")
AUTO_MIGRATE = os.environ.get("AUTO_MIGRATE", "1") == "1"
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"  # set to 1 behind HTTPS
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

if APP_ENV == "production":
    missing = [n for n, ok in [("SECRET_KEY", SECRET_KEY != "dev-only-change-me"), ("FILE_ENCRYPTION_KEY", bool(FILE_ENCRYPTION_KEY)),
                               ("INVITE_CODE", bool(INVITE_CODE)), ("COOKIE_SECURE=1", COOKIE_SECURE)] if not ok]
    if missing:
        raise RuntimeError(f"APP_ENV=production but not configured: {', '.join(missing)}")

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
