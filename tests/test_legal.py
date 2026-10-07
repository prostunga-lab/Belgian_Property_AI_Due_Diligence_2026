import re

import pytest
from fastapi.testclient import TestClient

from app import config, legal
from app.i18n import LANGS
from app.legal_texts import DOCS, TEXTS, TITLES
from app.main import app
from tests.helpers import page_text

PLACEHOLDER = re.compile(r"\{(\w+)\}")
KNOWN = {"company", "address", "enterprise", "email", "phone", "hosting", "hosting_region", "todo", "minutes"}


def get(lang, path):
    return TestClient(app, cookies={"lang": lang}).get(path)


@pytest.fixture(autouse=True)
def blank_identity(monkeypatch):
    for name, value in (("CONTACT_EMAIL", ""), ("COMPANY_NAME", ""), ("COMPANY_ADDRESS", ""), ("COMPANY_ENTERPRISE_NUMBER", ""), ("COMPANY_PHONE", ""),
                        ("HOSTING_PROVIDER", ""), ("HOSTING_REGION", ""), ("LEGAL_REVIEWED", False), ("STRIPE_SECRET_KEY", ""), ("ANTHROPIC_API_KEY", None), ("SMTP_HOST", None)):
        monkeypatch.setattr(config, name, value)


def shape(lang):
    return {d: [(len(items), [isinstance(i, tuple) for i in items]) for _, items in TEXTS[lang][d]] for d in DOCS}


def test_languages_have_identical_structure_and_known_placeholders():
    for lang in LANGS:
        assert shape(lang) == shape("fr"), f"{lang}: sections/items differ from the French reference"
        assert set(TITLES[lang]) == set(DOCS)
        for d in DOCS:
            for _, items in TEXTS[lang][d]:
                for it in items:
                    text = it[1] if isinstance(it, tuple) else it
                    assert set(PLACEHOLDER.findall(text)) <= KNOWN, f"{lang}/{d}: unknown placeholder in {text!r}"


@pytest.mark.parametrize("path,doc", [("/legal", "legal"), ("/privacy", "privacy"), ("/terms", "terms")])
def test_pages_are_public_translated_and_linked_from_every_footer(path, doc):
    for lang in LANGS:
        r = get(lang, path)
        assert r.status_code == 200 and f'hreflang="{lang}"' in r.text
        assert TITLES[lang][doc] in page_text(r) and "{" not in re.sub(r"<style.*?</style>|<script.*?</script>", "", r.text, flags=re.S)
        footer = r.text.split("<footer>")[1]
        assert all(f'href="/{p}"' in footer for p in ("legal", "privacy", "terms"))


def test_unknown_facts_are_marked_not_invented_and_configured_ones_shown(monkeypatch):
    body = get("fr", "/legal").text
    assert body.count('class="todo"') >= 6 and "Acme" not in body
    monkeypatch.setattr(config, "COMPANY_NAME", "Acme <b>BV</b>")
    monkeypatch.setattr(config, "CONTACT_EMAIL", "hello@acme.be")
    body = get("en", "/legal").text
    assert "Acme &lt;b&gt;BV&lt;/b&gt;" in body and "<b>BV</b>" not in body and "hello@acme.be" in body  # escaped


def test_draft_banner_until_reviewed(monkeypatch):
    assert 'role="note"' in get("fr", "/terms").text
    monkeypatch.setattr(config, "LEGAL_REVIEWED", True)
    assert 'role="note"' not in get("fr", "/terms").text


def test_third_parties_are_listed_only_when_really_used(monkeypatch):
    text = page_text(get("en", "/privacy"))
    assert "Stripe" not in text and "Anthropic" not in text
    monkeypatch.setattr(config, "STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "k")
    text = page_text(get("en", "/privacy"))
    assert "Stripe" in text and "Anthropic" in text


def test_cookie_statement_matches_the_cookies_the_app_really_sets():
    assert "session" in page_text(get("en", "/privacy")) and "lang" in page_text(get("en", "/privacy"))
    c = TestClient(app)
    c.get("/lang/nl?next=/")
    assert "lang" in c.cookies
    assert "12 hours" in page_text(get("en", "/privacy"))


def test_terms_state_the_processing_promise_from_config(monkeypatch):
    monkeypatch.setattr(config, "PROCESSING_PROMISE_MINUTES", 3)
    assert "3 minutes" in page_text(get("en", "/terms"))
