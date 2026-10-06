import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATA_DIR"] = _tmp
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp}/test.db")  # CI can point this at Postgres
os.environ.setdefault("LOGIN_MAX_ATTEMPTS", "1000")
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("INVITE_CODE", None)
os.environ.pop("FILE_ENCRYPTION_KEY", None)
