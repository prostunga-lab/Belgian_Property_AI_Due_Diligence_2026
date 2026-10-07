"""Generate the production secrets: ``python -m app.gen_secrets`` (prints KEY=VALUE lines to paste into Railway's Raw Editor).

Values are created locally with the OS random generator and printed once; nothing is stored or sent anywhere.
"""
from __future__ import annotations

import secrets
import sys

from . import invite


def generate() -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "COOKIE_SECURE": "1",
        "SECRET_KEY": secrets.token_hex(32),           # signs session cookies and e-mailed links
        "FILE_ENCRYPTION_KEY": secrets.token_hex(32),  # encrypts uploaded files at rest: LOSING IT LOSES THE FILES
        "INVITE_CODE": invite.generate(),               # XXXX-XXXX-XXXX-XXXX, no look-alike characters; case/hyphens ignored when typed
    }


if __name__ == "__main__":
    print("\n".join(f"{k}={v}" for k, v in generate().items()))
    print("\nStore FILE_ENCRYPTION_KEY in a password manager NOW: without it, uploaded files cannot be recovered.", file=sys.stderr)
