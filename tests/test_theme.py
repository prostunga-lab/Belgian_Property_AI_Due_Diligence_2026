"""The page background must stay tinted (not white) and every text/background pair of the palette must keep WCAG AA contrast."""
import re

import pytest
from fastapi.testclient import TestClient

from app.i18n import CATALOGS
from app.main import app


def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    lin = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def ratio(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def palettes() -> dict[str, dict[str, str]]:
    css = TestClient(app).get("/login").text
    light = dict(re.findall(r"--([\w-]+):(#[0-9a-fA-F]{6})", re.search(r":root\{(.*?)\}", css).group(1)))
    dark_block = re.search(r"prefers-color-scheme:dark\)\{:root\{(.*?)\}\}", css).group(1)
    dark = light | dict(re.findall(r"--([\w-]+):(#[0-9a-fA-F]{6})", dark_block))
    return {"light": light, "dark": dark}


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_page_background_is_never_white(theme):
    p = palettes()[theme]
    assert p["bg"].lower() not in ("#fff", "#ffffff", "#fafafa", "#f8fafc"), f"{theme}: page background is (nearly) white: {p['bg']}"
    assert ratio(p["bg"], "#ffffff") >= 1.1 or theme == "dark"  # a visible tint against pure white
    css = TestClient(app).get("/login").text
    assert re.search(r"body\{[^}]*background-color:var\(--bg\)", css) and "html{background:var(--bg)}" in css  # also behind short pages


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_palette_keeps_aa_contrast(theme):
    p = palettes()[theme]
    pairs = [("fg on bg", p["fg"], p["bg"]), ("fg on bg2 (gradient top)", p["fg"], p["bg2"]), ("muted on bg", p["mut"], p["bg"]),
             ("muted on bg2", p["mut"], p["bg2"]), ("muted on card", p["mut"], p["card"]), ("link on bg", p["acc"], p["bg"]),
             ("error on bg", p["high"], p["bg"]), ("ok on bg", p["ok"], p["bg"]), ("button text on button", "#ffffff", p["btn"]),
             ("muted on code chip", p["mut"], p["code"]), ("header text", "#ffffff", p["hdr"]), ("header links", "#dbe6f3", p["hdr"])]
    if theme == "light":  # severity colours are used on white cards
        pairs += [(f"{k} on card", p[k], p["card"]) for k in ("high", "medium", "low", "info")]
    low = [(n, round(ratio(a, b), 2)) for n, a, b in pairs if ratio(a, b) < 4.5]
    assert low == [], f"{theme}: contrast below WCAG AA 4.5:1 -> {low}"


def test_french_uses_telecharger_not_televerser():
    fr = " ".join(CATALOGS["fr"].values()).lower()
    assert "téléver" not in fr
    assert CATALOGS["fr"]["case.upload"] == "Télécharger" and CATALOGS["fr"]["landing.how.1.title"] == "Téléchargez"
