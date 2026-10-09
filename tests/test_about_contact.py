import datetime as dt
import html
import importlib
import re
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from app import config
from app.i18n import CATALOGS, LANGS
from app.main import app
from tests.helpers import new_client, page_text


def get(lang, path):
    return TestClient(app, cookies={"lang": lang}).get(path)


@pytest.fixture(autouse=True)
def no_publisher_identity(monkeypatch):
    for name, value in (("CONTACT_EMAIL", ""), ("COMPANY_NAME", ""), ("COMPANY_ADDRESS", ""), ("COMPANY_ENTERPRISE_NUMBER", ""), ("COMPANY_PHONE", ""), ("INVITE_CODE", None)):
        monkeypatch.setattr(config, name, value)


@pytest.mark.parametrize("path,prefix", [("/about", "about"), ("/contact", "contact")])
def test_pages_are_public_and_translated(path, prefix):
    for lang in LANGS:
        r = get(lang, path)
        assert r.status_code == 200
        body = html.unescape(r.text)
        assert f'<html lang="{lang}"' in body and f"<title>{CATALOGS[lang][prefix + '.title']}</title>" in body
        assert f"<h1>{CATALOGS[lang][prefix + '.h1']}</h1>" in body and body.count("<h1") == 1
        assert '<meta name="description"' in body and all(f'hreflang="{c}"' in body for c in LANGS)
        assert "{" not in re.sub(r"<style.*?</style>|<script.*?</script>", "", body, flags=re.S)  # no unfilled placeholder
    assert TestClient(app).get(path, headers={"accept": "text/html"}, follow_redirects=False).status_code == 200  # no login redirect


def test_about_only_states_facts_about_the_product():
    for lang in LANGS:
        body = page_text(get(lang, "/about"))
        for key in ("about.mission.text", "about.why.text", "about.status.text"):
            assert CATALOGS[lang][key] in body
        for i in (1, 2, 3, 4):
            assert CATALOGS[lang][f"about.principles.{i}.title"] in body
        low = body.lower()
        for invented in ("our team", "notre équipe", "ons team", "founded", "fondé", "opgericht", "years of experience", "ans d'expérience", "clients"):
            assert invented not in low, f"{lang}: about page claims {invented!r}"


def test_nothing_is_shown_for_unconfigured_identity():
    body = page_text(get("en", "/contact"))
    assert CATALOGS["en"]["contact.unavailable"] in body and "mailto:" not in body
    assert CATALOGS["en"]["contact.company.title"] not in body
    assert "Published by" not in page_text(get("en", "/about"))
    assert "<form" not in get("en", "/contact").text.split("</header>")[1]  # no form that could silently lose a message


def test_configured_details_are_displayed_and_escaped(monkeypatch):
    monkeypatch.setattr(config, "CONTACT_EMAIL", "info@example.be")
    monkeypatch.setattr(config, "COMPANY_NAME", "Acme <b>Vastgoed</b> BV")
    monkeypatch.setattr(config, "COMPANY_ADDRESS", "Kerkstraat 1\n9000 Gent")
    monkeypatch.setattr(config, "COMPANY_ENTERPRISE_NUMBER", "BE 0123.456.789")
    monkeypatch.setattr(config, "COMPANY_PHONE", "+32 9 123 45 67")
    raw = get("fr", "/contact").text
    assert "<b>Vastgoed</b>" not in raw and "&lt;b&gt;Vastgoed&lt;/b&gt;" in raw  # operator-provided text is escaped
    body = html.unescape(raw)
    for fragment in ("Acme <b>Vastgoed</b> BV", "Kerkstraat 1", "9000 Gent", "BE 0123.456.789", "+32 9 123 45 67", CATALOGS["fr"]["contact.company.title"]):
        assert fragment in body
    assert "Édité par Acme" in html.unescape(get("fr", "/about").text)


@pytest.mark.parametrize("lang", LANGS)
def test_mailto_link_has_translated_subject_and_the_exact_address(monkeypatch, lang):
    monkeypatch.setattr(config, "CONTACT_EMAIL", "info@example.be")
    body = get(lang, "/contact").text
    href = re.search(r'href="(mailto:[^"]+)"', body).group(1)
    assert href.startswith("mailto:info@example.be?subject=")
    assert unquote(href.split("subject=")[1]) == html.unescape(CATALOGS[lang]["contact.mail_subject"])
    assert "?" not in href.split("?subject=")[0] and href.count("?") == 1


def test_invalid_contact_email_values_are_ignored(monkeypatch):
    for bad in ("x@y.be?cc=a.com", "x@y.be&bcc=z@w.be", "a b@c.be", "<a@b.be>", "nobody", "a@b"):
        monkeypatch.setenv("CONTACT_EMAIL", bad)
        importlib.reload(config)
        assert config.CONTACT_EMAIL == "", bad
    monkeypatch.setenv("CONTACT_EMAIL", "  \"Info@Example.be\" ")
    importlib.reload(config)
    assert config.CONTACT_EMAIL == "Info@Example.be"  # surrounding whitespace/quotes from copy-paste are trimmed
    monkeypatch.undo()
    importlib.reload(config)


def test_invite_hint_only_in_invite_mode_and_privacy_note_present(monkeypatch):
    monkeypatch.setattr(config, "CONTACT_EMAIL", "info@example.be")
    assert CATALOGS["en"]["contact.invite"] not in page_text(get("en", "/contact"))
    monkeypatch.setattr(config, "INVITE_CODE", "secret-code-123")
    body = page_text(get("en", "/contact"))
    assert CATALOGS["en"]["contact.invite"] in body and CATALOGS["en"]["contact.privacy"] in body and "secret-code-123" not in body


def test_about_and_contact_are_in_the_header_menu_not_the_footer_on_every_kind_of_page():
    c = new_client("foot@x.be")
    pages = {"landing": TestClient(app).get("/"), "login": TestClient(app).get("/login"), "about": TestClient(app).get("/about"),
             "contact": TestClient(app).get("/contact"), "dashboard": c.get("/"), "account": c.get("/account"),
             "404": c.get("/cases/9999", headers={"accept": "text/html"})}
    for name, r in pages.items():
        footer = r.text.split("<footer>")[1]
        assert 'href="/about"' not in footer and 'href="/contact"' not in footer, f"{name}: footer must not link About/Contact"
        header = r.text.split("<header>")[1].split("</header>")[0]
        assert 'href="/about"' in header and 'href="/contact"' in header, f"{name}: header menu links missing"
        assert f"© {dt.date.today().year} Belgian Property Due Diligence" in html.unescape(footer)


def test_footer_uses_the_company_name_when_set(monkeypatch):
    monkeypatch.setattr(config, "COMPANY_NAME", "Acme BV")
    assert f"© {dt.date.today().year} Acme BV" in html.unescape(get("nl", "/").text.split("<footer>")[1])


def test_header_menu_order_is_about_pricing_contact():
    for lang in ("fr", "nl", "en"):
        header = get(lang, "/").text.split("<header>")[1].split("</nav>")[0]
        assert header.index('href="/about"') < header.index('href="/pricing"') < header.index('href="/contact"'), lang
