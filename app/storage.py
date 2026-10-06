"""Uploaded-file storage with encryption at rest (Fernet / AES-128-CBC + HMAC). Plaintext only ever lives in a temp dir during processing."""
from __future__ import annotations

import base64
import hashlib
import re
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from . import config


def _fernet() -> Fernet | None:
    if not config.FILE_ENCRYPTION_KEY:
        return None
    # Any passphrase works: derive a 32-byte urlsafe key from it.
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(config.FILE_ENCRYPTION_KEY.encode()).digest()))


def save(org_id: int, case_id: int, filename: str, data: bytes) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename).name)
    folder = config.UPLOAD_DIR / str(org_id) / str(case_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex}_{safe}"
    f = _fernet()
    path.write_bytes(f.encrypt(data) if f else data)
    return path


def read(path: str | Path) -> bytes:
    raw = Path(path).read_bytes()
    f = _fernet()
    if not f:
        return raw
    try:
        return f.decrypt(raw)
    except InvalidToken:
        raise RuntimeError("Cannot decrypt stored file: wrong FILE_ENCRYPTION_KEY or corrupted file")


@contextmanager
def plaintext(path: str | Path):
    """Yield a temporary decrypted copy that keeps the original extension (OCR/PDF readers need it)."""
    suffix = Path(path).suffix
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / f"doc{suffix}"
        p.write_bytes(read(path))
        yield p
