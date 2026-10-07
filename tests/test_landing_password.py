import html
import re

import pytest
from fastapi.testclient import TestClient

from app import config
from app.i18n import CATALOGS, LANGS
from app.main import app
from tests.helpers import new_client, page_text


def get(lang, path="/", **kw):
    return TestClient(app, cookies={"lang": lang}).get(path, **kw)


# --- landing page -----------------------------------------------------------------------------------

@pytest.mark.parametrize("lang,h1,cta,login", [
    ("fr", "Téléversez les documents du bien. Découvrez les risques avant l'acheteur.", "Créer un compte", "Se connecter"),
    ("nl", "Upload de documenten van het pand. Ontdek de risico's vóór de koper.", "Account aanmaken", "Inloggen"),
    ("en", "Upload the property documents. Get the risks before the buyer does.", "Create an account", "Log in"),
])
def test_visitors_see_the_landing_page_in_their_language(lang, h1, cta, login):
    r = get(lang)
    assert r.status_code == 200
    body = html.unescape(r.text)
    assert f'<html lang="{lang}"' in body and h1 in body and cta in body and login in body
    assert 'href="/login#register"' in body and 'href="/login#login"' in body
    assert re.search(r'<h1>', body) and body.count("<h1") == 1  # one main heading
    assert '<meta name="description"' in body and "<title>Belgian Property Due Diligence" in body
    for code in LANGS:  # alternate-language links for search engines + the visible switcher
        assert f'hreflang="{code}"' in body and f"/lang/{code}?next=" in body


def test_landing_sections_come_from_the_catalog_in_every_language():
    for lang in LANGS:
        body = html.unescape(get(lang).text)
        for key in ("landing.how.title", "landing.checks.title", "landing.trust.title", "landing.coverage.title", "landing.pricing.title",
                    "landing.faq.title", "landing.final.title", "landing.example.title"):
            assert CATALOGS[lang][key] in body, f"{lang}: {key} missing from the page"
        # the illustrative finding reuses the real rule texts, so the example can never drift from the product
        assert CATALOGS[lang]["rule.X-SURFACE.title"] in body and "185" in body and "240" in body
        assert "{" not in re.sub(r"<style.*?</style>|<script.*?</script>", "", body, flags=re.S)  # no unfilled placeholder
        assert "landing." not in body  # no missing key shown to visitors


def test_landing_states_free_credits_and_upload_limits(monkeypatch):
    monkeypatch.setattr(config, "FREE_CREDITS", 6)
    assert "6 crédits offerts" in page_text(get("fr"))
    monkeypatch.setattr(config, "FREE_CREDITS", 1)
    assert "1 crédit offert" in page_text(get("fr")) and "1 free credit" in page_text(get("en"))
    monkeypatch.setattr(config, "FREE_CREDITS", 0)
    assert "free credit" not in page_text(get("en"))  # no promise when nothing is offered
    assert f"{config.MAX_UPLOAD_MB} MB" in page_text(get("en"))


def test_invite_only_notice_only_when_an_invite_code_is_configured(monkeypatch):
    monkeypatch.setattr(config, "INVITE_CODE", None)
    assert "by invitation" not in page_text(get("en"))
    monkeypatch.setattr(config, "INVITE_CODE", "x-y-z")
    assert "by invitation" in page_text(get("en")) and "sur invitation" in page_text(get("fr")) and "op uitnodiging" in page_text(get("nl"))
    assert "x-y-z" not in get("en").text  # the code itself is never shown


def test_signed_in_users_still_get_the_dashboard_at_root():
    c = new_client("home1@x.be")
    body = page_text(c.get("/"))
    assert "Créer le dossier" in body  # the dashboard's "create a case" form
    assert "Créer un compte" not in body  # not the marketing page
    anon = page_text(TestClient(app).get("/"))
    assert "Créer un compte" in anon


def test_landing_is_public_without_redirect_and_login_still_works():
    r = TestClient(app).get("/", headers={"accept": "text/html"}, follow_redirects=False)
    assert r.status_code == 200
    assert TestClient(app).get("/login").status_code == 200
    assert TestClient(app).get("/cases/1", headers={"accept": "text/html"}, follow_redirects=False).status_code == 303  # app pages stay private


def test_landing_makes_no_claims_the_product_cannot_back():
    """Guard against marketing drift: forbidden promises must not appear in any language."""
    banned = ["GDPR compliant", "RGPD", "100%", "guarantee", "garantie", "garantie", "EU-hosted", "hébergé en", "AVG-conform", "ISO 27001", "SOC 2"]
    for lang in LANGS:
        text = " ".join(v for k, v in CATALOGS[lang].items() if k.startswith("landing.")).lower()
        for b in banned:
            assert b.lower() not in text, f"{lang}: landing text promises {b!r}"
    # and the legal-advice disclaimer is on the page
    assert "not legal advice" in page_text(get("en")).lower() or "not advice" in page_text(get("en")).lower()


# --- password visibility ------------------------------------------------------------------------------

PASSWORD_PAGES = [("/login", 2), ("/reset?token=x", 1)]


@pytest.mark.parametrize("path,count", PASSWORD_PAGES)
def test_every_password_field_has_an_accessible_toggle(path, count):
    body = TestClient(app).get(path).text
    assert len(re.findall(r'<input[^>]*type="password"', body)) == count
    toggles = re.findall(r'<button type="button" class="pwtoggle"[^>]*>', body)
    assert len(toggles) == count
    for t in toggles:
        assert 'aria-pressed="false"' in t and "aria-label=" in t and "data-show=" in t and "data-hide=" in t
    assert 'autocomplete="current-password"' in body or 'autocomplete="new-password"' in body  # password managers still work


def test_account_delete_password_field_has_a_toggle():
    c = new_client("pw1@x.be")
    body = c.get("/account").text
    assert len(re.findall(r'<input[^>]*type="password"', body)) == 1 and body.count('class="pwtoggle"') == 1


def test_toggle_labels_are_translated_and_hidden_without_js():
    for lang, show in (("fr", "Afficher le mot de passe"), ("nl", "Wachtwoord tonen"), ("en", "Show password")):
        body = TestClient(app, cookies={"lang": lang}).get("/login").text
        assert f'aria-label="{show}"' in body
    css = TestClient(app).get("/login").text
    assert ".pwtoggle{display:none" in css and ".js .pwtoggle{display:inline-flex}" in css  # visible only once JS has run


def test_password_value_is_never_rendered_back_into_the_page():
    c = TestClient(app)
    r = c.post("/login", data={"email": "nobody@x.be", "password": "MySuperSecretPassw0rd!"})
    assert r.status_code == 400 and "MySuperSecretPassw0rd" not in r.text


def test_pages_ship_an_inline_favicon_so_browsers_do_not_request_one():
    assert '<link rel="icon" href="data:image/svg+xml' in TestClient(app).get("/").text
    assert 'class="grid trust"' in TestClient(app).get("/").text  # five trust cards laid out as one row on desktop
