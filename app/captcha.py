"""Optional Cloudflare Turnstile check on registration. Disabled unless both TURNSTILE_* keys are set; fails closed when enabled."""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request

from . import config

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
HOST = "https://challenges.cloudflare.com"
log = logging.getLogger("uvicorn.error")


def enabled() -> bool:
    return bool(config.TURNSTILE_SITE_KEY and config.TURNSTILE_SECRET_KEY)


def verify(token: str, ip: str | None = None) -> bool:
    """True when the visitor passed the challenge (or when the captcha is disabled)."""
    if not enabled():
        return True
    if not token:
        return False
    data = urllib.parse.urlencode({"secret": config.TURNSTILE_SECRET_KEY, "response": token, **({"remoteip": ip} if ip else {})}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(VERIFY_URL, data=data, method="POST"), timeout=8) as resp:
            return bool(json.load(resp).get("success"))
    except Exception as exc:  # network trouble: refuse rather than let bots through
        log.warning("turnstile verification unavailable: %s", exc)
        return False
