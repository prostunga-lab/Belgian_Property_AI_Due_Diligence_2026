import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATA_DIR"] = _tmp
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp}/test.db")  # CI can point this at Postgres
os.environ.setdefault("LOGIN_MAX_ATTEMPTS", "1000")
os.environ.setdefault("FREE_CREDITS", "1000")
os.environ.setdefault("REQUIRE_EMAIL_VERIFICATION", "0")
os.environ.setdefault("BASE_URL", "http://testserver")
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("INVITE_CODE", None)
os.environ.pop("FILE_ENCRYPTION_KEY", None)
for _k in ("SMTP_HOST", "STRIPE_SECRET_KEY", "STRIPE_PRICE_ID", "STRIPE_WEBHOOK_SECRET"):
    os.environ.pop(_k, None)
