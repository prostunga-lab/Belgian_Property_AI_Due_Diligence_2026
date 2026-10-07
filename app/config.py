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
def _clean(name: str, default: str = "") -> str:
    """Env value without surrounding whitespace/quotes: values pasted into hosting dashboards often carry an invisible
    trailing space or newline (or quotes), which would silently turn a setting off or make a code never match."""
    return os.environ.get(name, default).strip().strip("\"'").strip()


APP_ENV = _clean("APP_ENV", "development").lower()  # "production" enforces secrets below
# Files at rest are encrypted when set. LOSING THIS KEY MAKES UPLOADED FILES UNRECOVERABLE.
FILE_ENCRYPTION_KEY = os.environ.get("FILE_ENCRYPTION_KEY")
# Registration: "open" (anyone) or "invite" (requires INVITE_CODE).
INVITE_CODE = _clean("INVITE_CODE") or None
AUTO_MIGRATE = os.environ.get("AUTO_MIGRATE", "1") == "1"
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
COOKIE_SECURE = _clean("COOKIE_SECURE", "0") == "1"  # set to 1 behind HTTPS
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-5-5")
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "25"))
# Configurable retention (GDPR): cases older than this are purged by `python -m app.purge`.
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "365"))

# Accounts, credits, billing, e-mail
# Public URL used in e-mailed links and Stripe redirects. Railway/Render expose their public host automatically.
def _base_url() -> str:
    if explicit := os.environ.get("BASE_URL"):
        return explicit.rstrip("/")
    if domain := os.environ.get("RAILWAY_PUBLIC_DOMAIN"):  # host only, no scheme
        return f"https://{domain}"
    return (os.environ.get("RENDER_EXTERNAL_URL") or "http://localhost:8000").rstrip("/")


BASE_URL = _base_url()
FREE_CREDITS = int(os.environ.get("FREE_CREDITS", "6"))  # granted to each new organisation; 1 credit = 1 document
PACK_CREDITS = int(os.environ.get("PACK_CREDITS", "20"))
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
SMTP_HOST = os.environ.get("SMTP_HOST")
# E-mail confirmation is enforced only when mail can actually be delivered (otherwise nobody could ever confirm).
REQUIRE_EMAIL_VERIFICATION = os.environ.get("REQUIRE_EMAIL_VERIFICATION", "1" if SMTP_HOST else "0") == "1"
MAX_FILES_PER_REQUEST = int(os.environ.get("MAX_FILES_PER_REQUEST", "10"))

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
