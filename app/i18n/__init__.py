"""Minimal, dependency-free i18n: French, Dutch, English.

Messages live in fr.py / nl.py / en.py as flat ``key -> template`` dicts (``str.format`` placeholders).
Lookup falls back to English, then to the key itself, so a missing translation is visible instead of crashing.
"""
from __future__ import annotations

import re
from typing import Callable

from . import en, fr, nl

LANGS = ("fr", "nl", "en")
LANG_NAMES = {"fr": "Français", "nl": "Nederlands", "en": "English"}
DEFAULT_LANG = "fr"
CATALOGS: dict[str, dict[str, str]] = {"fr": fr.MESSAGES, "nl": nl.MESSAGES, "en": en.MESSAGES}
COOKIE = "lang"


def normalize(code: str | None) -> str | None:
    """'nl-BE' / 'NL' / 'fr_FR' -> 'nl' / 'nl' / 'fr'; unsupported -> None."""
    if not code:
        return None
    base = re.split(r"[-_]", code.strip().lower())[0]
    return base if base in LANGS else None


def from_accept_language(header: str | None) -> str | None:
    """First supported language of an Accept-Language header, honouring q-values."""
    if not header:
        return None
    ranked = []
    for part in header.split(","):
        bits = part.strip().split(";")
        q = 1.0
        for b in bits[1:]:
            b = b.strip()
            if b.startswith("q="):
                try:
                    q = float(b[2:])
                except ValueError:
                    q = 0.0
        lang = normalize(bits[0])
        if lang and q > 0:
            ranked.append((q, lang))
    return max(ranked, key=lambda x: x[0])[1] if ranked else None


def _lookup(key: str, lang: str, n) -> str | None:
    """Plural forms: '<key>.one' / '<key>.other' are used when the call passes n=<count>."""
    for code in (lang, "en"):
        cat = CATALOGS.get(code, {})
        if n is not None and f"{key}.other" in cat:
            return cat[f"{key}.one"] if n == 1 and f"{key}.one" in cat else cat[f"{key}.other"]
        if key in cat:
            return cat[key]
    return None


def t(key: str, lang: str = DEFAULT_LANG, **params) -> str:
    msg = _lookup(key, lang, params.get("n"))
    if msg is None:
        return key
    try:
        return msg.format(**params) if params or "{" in msg else msg
    except (KeyError, IndexError, ValueError):
        return msg  # never break a page over a formatting slip


def has(key: str, lang: str = "en") -> bool:
    return _lookup(key, lang, None) is not None


def translator(lang: str) -> Callable[..., str]:
    return lambda key, **params: t(key, lang, **params)
