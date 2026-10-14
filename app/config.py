import os
import re
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
# Open registration: anyone may create an account (no invitation code). Explicit opt-in, because it also opens the free trial to everybody.
OPEN_REGISTRATION = _clean("OPEN_REGISTRATION", "0") == "1" and not INVITE_CODE  # an invitation code, when set, always wins
REGISTRATIONS_PER_IP_PER_DAY = int(os.environ.get("REGISTRATIONS_PER_IP_PER_DAY", "5"))
# Free trial of the subscription plans (Stripe trial period): days, and the dossiers that can be analysed during it. 0 days = no trial.
TRIAL_DAYS = int(os.environ.get("TRIAL_DAYS", "3"))
TRIAL_DOSSIERS = int(os.environ.get("TRIAL_DOSSIERS", "3"))
ADMIN_EMAILS = {e.strip().lower() for e in _clean("ADMIN_EMAILS").split(",") if e.strip()}  # may read the access requests at /admin/requests
AUTO_MIGRATE = os.environ.get("AUTO_MIGRATE", "1") == "1"
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
COOKIE_SECURE = _clean("COOKIE_SECURE", "0") == "1"  # set to 1 behind HTTPS
CSP_MODE = _clean("CSP_MODE", "enforce").lower()  # enforce | report-only | off (report-only lets you watch the browser console before enforcing)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-5-5")
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "25"))
# Configurable retention (GDPR): cases older than this are purged by `python -m app.purge`.
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "365"))

# Publisher identity shown on /about and /contact and in the footer. Nothing is invented: a field that is not set is not shown.
COMPANY_NAME = _clean("COMPANY_NAME")
COMPANY_ADDRESS = _clean("COMPANY_ADDRESS")
COMPANY_ENTERPRISE_NUMBER = _clean("COMPANY_ENTERPRISE_NUMBER")  # BCE/KBO number and/or VAT number
COMPANY_PHONE = _clean("COMPANY_PHONE")
HOSTING_PROVIDER = _clean("HOSTING_PROVIDER")  # e.g. "Railway"; shown in the legal pages
HOSTING_REGION = _clean("HOSTING_REGION")
RULES_VALIDATED = os.environ.get("RULES_VALIDATED", "0") == "1"  # set to 1 only once a professional has validated the rule set (see docs/REGLES.md)
LEGAL_REVIEWED = os.environ.get("LEGAL_REVIEWED", "0") == "1"  # hides the "draft" banner once a lawyer has reviewed the texts
_email = _clean("CONTACT_EMAIL")
CONTACT_EMAIL = _email if re.fullmatch(r"[A-Za-z0-9._+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}", _email) else ""  # strict: it ends up in a mailto: link

# Accounts, credits, billing, e-mail
# Public URL used in e-mailed links and Stripe redirects. Railway/Render expose their public host automatically.
def _base_url() -> str:
    if explicit := os.environ.get("BASE_URL"):
        return explicit.rstrip("/")
    if domain := os.environ.get("RAILWAY_PUBLIC_DOMAIN"):  # host only, no scheme
        return f"https://{domain}"
    return (os.environ.get("RENDER_EXTERNAL_URL") or "http://localhost:8000").rstrip("/")


BASE_URL = _base_url()
FREE_CREDITS = int(os.environ.get("FREE_CREDITS", "1"))  # complete dossiers offered to each new organisation (1 credit = 1 dossier)
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
# A dossier is one complete case; billing is per dossier, so a case is capped to keep that unit meaningful.
DOSSIER_MAX_DOCUMENTS = int(os.environ.get("DOSSIER_MAX_DOCUMENTS", "25"))
# Prices are shown VAT-inclusive by default (required for consumers); set PRICES_VAT=excl for a B2B-only offer.
PRICES_VAT = _clean("PRICES_VAT", "incl").lower() if _clean("PRICES_VAT", "incl").lower() in ("incl", "excl") else "incl"
# Public promise on processing time of a complete dossier (minutes). Measured and tested: see tests/test_promise.py.
PROCESSING_PROMISE_MINUTES = int(os.environ.get("PROCESSING_PROMISE_MINUTES", "2"))
SMTP_HOST = os.environ.get("SMTP_HOST")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")  # HTTPS e-mail API (works where outbound SMTP is blocked, e.g. Railway trial/hobby)
MAIL_ENABLED = bool(SMTP_HOST or RESEND_API_KEY)
TURNSTILE_SITE_KEY = os.environ.get("TURNSTILE_SITE_KEY")  # Cloudflare Turnstile captcha on registration (optional: both keys needed)
TURNSTILE_SECRET_KEY = os.environ.get("TURNSTILE_SECRET_KEY")
# E-mail confirmation is enforced only when mail can actually be delivered (otherwise nobody could ever confirm).
REQUIRE_EMAIL_VERIFICATION = os.environ.get("REQUIRE_EMAIL_VERIFICATION", "1" if MAIL_ENABLED else "0") == "1"
MAX_FILES_PER_REQUEST = int(os.environ.get("MAX_FILES_PER_REQUEST", "25"))

# OCR (Tesseract). Pages with fewer than OCR_MIN_CHARS extracted characters are treated as scans.
OCR_ENABLED = os.environ.get("OCR_ENABLED", "1") != "0"
OCR_LANGS = os.environ.get("OCR_LANGS", "nld+fra+eng")
OCR_DPI = int(os.environ.get("OCR_DPI", "300"))
OCR_MIN_CHARS = int(os.environ.get("OCR_MIN_CHARS", "30"))
OCR_TIMEOUT_S = int(os.environ.get("OCR_TIMEOUT_S", "120"))

if APP_ENV == "production":
    missing = [n for n, ok in [("SECRET_KEY", SECRET_KEY != "dev-only-change-me"), ("FILE_ENCRYPTION_KEY", bool(FILE_ENCRYPTION_KEY)),
                               ("INVITE_CODE (or OPEN_REGISTRATION=1)", bool(INVITE_CODE) or OPEN_REGISTRATION), ("COOKIE_SECURE=1", COOKIE_SECURE)] if not ok]
    if missing:
        raise RuntimeError(f"APP_ENV=production but not configured: {', '.join(missing)}")

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
