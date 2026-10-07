from __future__ import annotations

import hashlib
import hmac
import os
import secrets

from fastapi import Depends, Header, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .errors import AppError
from .models import ApiKey, SessionLocal, User


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1)
    return salt.hex() + "$" + h.hex()


def verify_password(pw: str, stored: str) -> bool:
    salt, h = stored.split("$")
    cand = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
    return hmac.compare_digest(cand.hex(), h)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    uid = request.session.get("uid")
    user = db.get(User, uid) if uid else None
    # The session carries a fingerprint of the password it was opened with: changing/resetting it logs out other sessions.
    if not user or not hmac.compare_digest(str(request.session.get("pwf", "")), pw_fingerprint(user)):
        raise AppError(401, "err.not_authenticated")
    return user


def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    """Like current_user but returns None instead of failing (for harmless endpoints such as the language switch)."""
    try:
        return current_user(request, db)
    except AppError:
        return None


def open_session(request: Request, user: User) -> None:
    request.session.clear()
    request.session["uid"] = user.id
    request.session["pwf"] = pw_fingerprint(user)


# --- signed, purpose-bound, expiring tokens (e-mail confirmation, password reset) -------------------

def _ser(purpose: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(config.SECRET_KEY, salt=f"dd-{purpose}")


def make_token(purpose: str, uid: int, extra: str = "") -> str:
    return _ser(purpose).dumps([uid, extra])


def read_token(purpose: str, token: str, max_age: int) -> tuple[int, str] | None:
    try:
        uid, extra = _ser(purpose).loads(token, max_age=max_age)
        return int(uid), extra
    except (BadSignature, SignatureExpired, ValueError, TypeError):
        return None


def pw_fingerprint(user: User) -> str:
    """Changes when the password changes, which makes reset links single-use."""
    return hashlib.sha256(user.password_hash.encode()).hexdigest()[:16]


# --- API keys -----------------------------------------------------------------------------------

def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_api_key() -> tuple[str, str, str]:
    key = "sk_live_" + secrets.token_urlsafe(32)
    return key, key[:12], sha(key)


def api_user(x_api_key: str = Header(default=""), db: Session = Depends(get_db)) -> User:
    k = db.scalar(select(ApiKey).where(ApiKey.key_hash == sha(x_api_key), ApiKey.revoked == False)) if x_api_key else None  # noqa: E712
    user = db.get(User, k.user_id) if k else None
    if not user:
        raise AppError(401, "err.invalid_api_key")
    return user
