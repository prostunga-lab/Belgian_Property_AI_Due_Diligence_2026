"""Turn language-neutral findings (rule_id + params) into text in the reader's language."""
from __future__ import annotations

from . import i18n


def warning_text(code: str, lang: str) -> str:
    """Ingest warnings are stored as codes ('ocr_failed:3'); unknown (legacy) values are shown as they are."""
    name, _, arg = code.partition(":")
    key = f"warn.{name}"
    return i18n.t(key, lang, arg=arg) if i18n.has(key) else code


def _params(params: dict, lang: str) -> dict:
    p = {k: v for k, v in (params or {}).items() if k != "variant"}
    if "warnings" in p:
        p["warnings"] = " ".join(warning_text(w, lang) for w in p["warnings"])
    if "warning" in p:
        p["warning"] = warning_text(p["warning"], lang)
    return p


def finding_text(rule_id: str, params: dict | None, lang: str, fallback: dict | None = None) -> dict:
    """{'title','detail','recommendation'} for a finding. Rows written before i18n (no params) use their stored text."""
    base = f"rule.{rule_id}"
    if params is None and fallback and not i18n.has(f"{base}.title"):
        return fallback
    variant = (params or {}).get("variant")
    p = _params(params or {}, lang)

    def part(name: str, required: bool) -> str:
        for key in ([f"{base}.{name}.{variant}"] if variant else []) + [f"{base}.{name}"]:
            if i18n.has(key):
                return i18n.t(key, lang, **p)
        return f"{base}.{name}" if required else ""

    return {"title": part("title", True), "detail": part("detail", True), "recommendation": part("rec", False)}
