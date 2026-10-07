"""Invitation codes: forgiving to realistic typing/copy-paste mistakes, strict about everything else.

Both the configured code and what a visitor types are *normalised* before they are compared:
  * Unicode NFKC, then everything that is not a letter or a digit is dropped (spaces, hyphens, quotes, zero-width characters, BOM…)
  * upper-cased (phone keyboards capitalise the first letter),
  * O->0 and I/L->1 (the ambiguous look-alikes; generated codes never contain O, I or L in the first place).
A whole pasted line such as ``INVITE_CODE=ABCD-…`` is accepted too. The comparison is constant-time.
"""
from __future__ import annotations

import hmac
import secrets
import unicodedata

# 32 unambiguous symbols (Crockford base32 without I, L, O, U): 16 symbols = 80 bits, printed as XXXX-XXXX-XXXX-XXXX.
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_LOOKALIKES = str.maketrans({"O": "0", "I": "1", "L": "1"})
_LINE_PREFIX = "INVITE_CODE"


def normalize(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", value or "")
    return "".join(c for c in text if c.isalnum()).upper().translate(_LOOKALIKES)


def generate() -> str:
    raw = "".join(secrets.choice(ALPHABET) for _ in range(16))
    return "-".join(raw[i:i + 4] for i in range(0, 16, 4))


def matches(submitted: str | None, configured: str | None) -> bool:
    expected = normalize(configured)
    if not expected:
        return False
    got = normalize(submitted)
    prefix = normalize(_LINE_PREFIX)
    candidates = {got}
    if got.startswith(prefix):  # the visitor pasted the whole "INVITE_CODE=…" line
        candidates.add(got[len(prefix):])
    return any(hmac.compare_digest(c.encode(), expected.encode()) for c in candidates)
