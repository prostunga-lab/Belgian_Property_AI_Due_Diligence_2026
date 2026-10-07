import html
import re

import pytest
from fastapi.testclient import TestClient

from app import config, plans
from app.i18n import CATALOGS, LANGS
from app.main import app
from tests.helpers import new_client, page_text
from tests.org_helpers import org_of, subscribe


def get(lang, path="/pricing", client=None):
    c = client or TestClient(app)
    return c.get(path, params={"lang": lang})


# --- the strategy, as executable rules ------------------------------------------------------------------------------

def test_defaults_follow_the_pricing_strategy():
    """Investors: pay per complete dossier, 15-29 EUR each. Agents: subscription 49-99 EUR/month, e.g. 15 dossiers a month."""
    catalogue = plans.load()
    lo, hi = plans.STRATEGY_PAYG_PER_DOSSIER_EUR
    for p in plans.by_kind("payg"):
        assert p.audience == "investor" and p.interval is None
        assert lo * 100 <= p.per_dossier_cents <= hi * 100, f"{p.id}: {p.per_dossier_cents / 100} EUR per dossier is outside {lo}-{hi}"
    smin, smax = plans.STRATEGY_SUBSCRIPTION_EUR_MONTH
    subs = plans.by_kind("subscription")
    assert [p.id for p in subs] == ["agent", "agency"]
    assert subs[0].audience == "agent" and subs[0].interval == "month" and subs[0].dossiers == 15
    assert smin * 100 <= subs[0].price_cents <= smax * 100
    assert subs[1].audience == "agency" and subs[1].price_cents == plans.STRATEGY_AGENCY_EUR_MONTH * 100 and subs[1].dossiers > subs[0].dossiers
    assert {p.audience for p in catalogue.values()} == {"investor", "agent", "agency"}
    assert max(p.per_dossier_cents for p in plans.by_kind("payg")) == hi * 100 and min(p.per_dossier_cents for p in plans.by_kind("payg")) == lo * 100  # the pack spans the range


def test_a_pack_is_cheaper_per_dossier_than_buying_one_by_one():
    single, pack = plans.get("single"), plans.get("pack5")
    assert pack.per_dossier_cents < single.per_dossier_cents and pack.dossiers == 5 and single.dossiers == 1


def test_prices_can_be_changed_without_touching_code(monkeypatch):
    monkeypatch.setenv("PLAN_AGENT_PRICE_EUR", "79,90")
    monkeypatch.setenv("PLAN_AGENT_DOSSIERS", "30")
    monkeypatch.setenv("PLAN_SINGLE_PRICE_EUR", "19")
    p = plans.get("agent")
    assert (p.price_cents, p.dossiers) == (7990, 30) and plans.get("single").price_cents == 1900
    for bad in ("", "abc", "-5", "0"):
        monkeypatch.setenv("PLAN_PACK5_PRICE_EUR", bad)
        assert plans.get("pack5").price_cents == 7500  # invalid values never produce a free or negative price
    monkeypatch.setenv("PLAN_AGENT_DOSSIERS", "zero")
    assert plans.get("agent").dossiers == 15  # an invalid override falls back to the default, not to an earlier value


def test_price_formatting_per_language():
    assert [plans.format_price(2900, l) for l in ("fr", "nl", "en")] == ["29 €", "€ 29", "€29"]
    assert [plans.format_price(4990, l) for l in ("fr", "nl", "en")] == ["49,90 €", "€ 49,90", "€49.90"]
    assert plans.get("nope") is None and plans.get(None) is None


# --- the pricing page ----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("lang", LANGS)
def test_pricing_page_shows_both_approaches_with_the_catalogue_prices(lang):
    r = get(lang)
    assert r.status_code == 200
    body = page_text(r)
    cat = CATALOGS[lang]
    assert f"<title>{cat['pricing.title']}</title>" in html.unescape(r.text) and body.count("<h1") == 1
    for key in ("pricing.investor.title", "pricing.investor.text", "pricing.agent.title", "pricing.agent.text", "pricing.sub_no_carryover", "pricing.sub_extra", "pricing.sub_cancel"):
        assert cat[key] in body, f"{lang}: {key}"
    for p in plans.load().values():
        assert plans.format_price(p.price_cents, lang) in body, f"{lang}: price of {p.id} missing"
    assert cat["pricing.sub_includes"].format(n=15) in body and cat["pricing.per_case"].format(price=plans.format_price(1500, lang)) in body
    assert cat["pricing.vat.incl"] in body
    assert "{" not in re.sub(r"<style.*?</style>|<script.*?</script>", "", body, flags=re.S)


def test_displayed_price_and_stripe_price_come_from_the_same_source(monkeypatch):
    monkeypatch.setenv("PLAN_AGENT_PRICE_EUR", "59")
    assert "59 €" in page_text(get("fr"))
    from app import billing
    from app.models import Org, SessionLocal, User
    from sqlalchemy import select
    c = new_client("pp-same@x.be")
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.email == "pp-same@x.be"))
        kw = billing.checkout_kwargs(db.get(Org, u.org_id), u, plans.get("agent"), "fr")
    assert kw["line_items"][0]["price_data"]["unit_amount"] == 5900


def test_visitors_are_sent_to_registration_and_buyers_get_checkout_buttons(monkeypatch):
    monkeypatch.setattr(config, "STRIPE_SECRET_KEY", "sk_test_1")
    anon = TestClient(app).get("/pricing").text
    assert anon.count('href="/login#register"') >= 3 and "/billing/checkout/" not in anon
    c = new_client("pp-buy@x.be")
    signed_in = c.get("/pricing").text
    for pid in ("single", "pack5", "agent"):
        assert f'action="/billing/checkout/{pid}"' in signed_in


def test_without_stripe_the_page_says_so_and_offers_contact(monkeypatch):
    monkeypatch.setattr(config, "STRIPE_SECRET_KEY", "")
    body = page_text(TestClient(app).get("/pricing"))
    assert CATALOGS["fr"]["pricing.unavailable"] in body
    c = new_client("pp-off@x.be")
    assert "/billing/checkout/" not in c.get("/pricing").text


def test_subscribers_are_offered_management_not_a_second_subscription(monkeypatch):
    monkeypatch.setattr(config, "STRIPE_SECRET_KEY", "sk_test_1")
    c = new_client("pp-sub@x.be"); subscribe(org_of("pp-sub@x.be"))
    body = c.get("/pricing").text
    assert 'action="/billing/checkout/agent"' not in body and 'href="/account"' in body and 'action="/billing/checkout/single"' in body


def test_vat_note_follows_the_configuration(monkeypatch):
    assert CATALOGS["en"]["pricing.vat.incl"] in page_text(get("en"))
    monkeypatch.setattr(config, "PRICES_VAT", "excl")
    assert CATALOGS["en"]["pricing.vat.excl"] in page_text(get("en")) and CATALOGS["en"]["pricing.vat.incl"] not in page_text(get("en"))


def test_free_dossier_is_announced_only_when_one_is_really_offered(monkeypatch):
    monkeypatch.setattr(config, "FREE_CREDITS", 1)
    assert "1 dossier complet offert" in page_text(get("fr"))
    monkeypatch.setattr(config, "FREE_CREDITS", 0)
    assert "offert à l'inscription" not in page_text(get("fr"))


def test_navigation_exposes_pricing_about_contact_on_every_page():
    c = new_client("pp-nav@x.be")
    for name, resp in {"landing": TestClient(app).get("/"), "login": TestClient(app).get("/login"), "pricing": TestClient(app).get("/pricing"),
                       "dashboard": c.get("/"), "account": c.get("/account")}.items():
        nav = re.search(r'<nav class="mainnav".*?</nav>', resp.text, re.S).group(0)
        for href in ("/pricing", "/about", "/contact"):
            assert f'href="{href}"' in nav, f"{name}: {href} missing from the header menu"
    assert 'aria-current="page"' in re.search(r'<nav class="mainnav".*?</nav>', TestClient(app).get("/pricing").text, re.S).group(0)
    assert re.search(r'<a href="/pricing" aria-current="page">', TestClient(app).get("/pricing").text)


def test_catalogue_names_exist_in_every_language():
    for lang in LANGS:
        for p in plans.load().values():
            assert f"plan.{p.id}.name" in CATALOGS[lang]
