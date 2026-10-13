"""Open registration (no invitation code) and the 3-day free trial of the subscription plans."""
import datetime as dt
import importlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import billing, config, plans
from app.i18n import CATALOGS, LANGS
from app.main import app, _attempts
from app.models import Org, SessionLocal, User
from app.services import balance
from tests.helpers import new_client, new_case, page_text
from tests.org_helpers import get_org, org_of, set_org
from tests.stripe_helpers import SECRET, checkout_obj, event, invoice_obj, subscription_obj
from tests.test_stripe import hook


def anon(lang="fr"):
    return TestClient(app, cookies={"lang": lang})


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    _attempts.clear()
    monkeypatch.setattr(config, "STRIPE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(config, "STRIPE_SECRET_KEY", "sk_test_123")


# --- open registration ---------------------------------------------------------------------------

def test_without_an_invitation_code_anyone_can_register_and_gets_the_trial_dossier(monkeypatch):
    monkeypatch.setattr(config, "INVITE_CODE", None)
    monkeypatch.setattr(config, "FREE_CREDITS", 1)
    r = anon().post("/register", data={"email": "open1@x.be", "password": "supersecret12", "account_type": "individual", "accept_terms": "1"}, follow_redirects=False)
    assert r.status_code == 303 and get_org(org_of("open1@x.be"))["credits"] == 1
    page = anon().get("/login").text
    assert 'name="invite_code"' not in page and 'href="/contact#access"' not in page  # no code field, no "ask for access" detour


def test_an_invitation_code_still_wins_when_both_are_configured(monkeypatch):
    monkeypatch.setattr(config, "INVITE_CODE", "abcd-efgh")
    r = anon().post("/register", data={"email": "closed@x.be", "password": "supersecret12", "account_type": "individual", "accept_terms": "1"})
    assert r.status_code == 403


def test_production_accepts_either_an_invitation_code_or_explicit_open_registration(monkeypatch):
    base = {"APP_ENV": "production", "SECRET_KEY": "s" * 40, "FILE_ENCRYPTION_KEY": "K0pM1cWk3nq1vCqg9UQ0b3mY3c9rVf2o3dYQmWfX3n4=", "COOKIE_SECURE": "1"}
    for k, v in base.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("INVITE_CODE", raising=False)
    monkeypatch.delenv("OPEN_REGISTRATION", raising=False)
    try:
        with pytest.raises(RuntimeError, match=r"INVITE_CODE \(or OPEN_REGISTRATION=1\)"):
            importlib.reload(config)
        monkeypatch.setenv("OPEN_REGISTRATION", "1")
        assert importlib.reload(config).OPEN_REGISTRATION is True
        monkeypatch.setenv("INVITE_CODE", "abcd-efgh-ijkl-mnop")
        assert importlib.reload(config).OPEN_REGISTRATION is False  # a configured code takes precedence
    finally:
        for k in list(base) + ["OPEN_REGISTRATION", "INVITE_CODE"]:
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("APP_ENV", "development")
        importlib.reload(config)


def test_one_address_cannot_farm_the_trial_with_unlimited_accounts(monkeypatch):
    monkeypatch.setattr(config, "INVITE_CODE", None)
    monkeypatch.setattr(config, "REGISTRATIONS_PER_IP_PER_DAY", 2)
    codes = [anon().post("/register", data={"email": f"farm{i}@x.be", "password": "supersecret12", "account_type": "individual", "accept_terms": "1"}, follow_redirects=False).status_code for i in range(4)]
    assert codes[:2] == [303, 303] and codes[2] == 429
    # failed attempts (bad e-mail) do not use up the daily allowance of honest visitors
    _attempts.clear()
    for i in range(3):
        anon().post("/register", data={"email": "bad", "password": "supersecret12", "account_type": "individual", "accept_terms": "1"})
    assert anon().post("/register", data={"email": "honest@x.be", "password": "supersecret12", "account_type": "individual", "accept_terms": "1"}, follow_redirects=False).status_code == 303


def test_health_states_the_registration_mode(monkeypatch):
    monkeypatch.setattr(config, "INVITE_CODE", None)
    assert anon().get("/health").json()["registration"] == "open"
    monkeypatch.setattr(config, "INVITE_CODE", "abcd-efgh")
    assert anon().get("/health").json()["registration"] == "invitation-only"


# --- free trial: checkout ----------------------------------------------------------------------------

def org_user(email):
    c = new_client(email)
    oid = org_of(email)
    with SessionLocal() as db:
        return c, db.get(Org, oid), db.scalar(select(User).where(User.org_id == oid))


@pytest.mark.parametrize("plan_id", ["agent", "agency"])
def test_subscriptions_start_with_a_stripe_trial_the_card_collected_up_front(plan_id):
    c, o, u = org_user(f"trial-{plan_id}@x.be")
    kw = billing.checkout_kwargs(o, u, plans.get(plan_id), "fr", "annual")
    assert kw["subscription_data"]["trial_period_days"] == 3 and kw["payment_method_collection"] == "always" and kw["metadata"]["trial"] == "1"
    msg = kw["custom_text"]["submit"]["message"]
    assert "3 jours" in msg and "automatiquement" in msg and "€" in msg  # the buyer is told what happens when the trial ends
    assert kw["line_items"][0]["price_data"]["unit_amount"] == plans.offer(plans.get(plan_id), "annual").total_cents  # the full price after the trial


def test_one_time_purchases_never_get_a_trial():
    c, o, u = org_user("trial-payg@x.be")
    kw = billing.checkout_kwargs(o, u, plans.get("single"), "fr")
    assert "trial_period_days" not in str(kw) and "trial" not in kw["metadata"] and kw["mode"] == "payment"


def test_the_trial_is_once_per_organisation_and_can_be_switched_off(monkeypatch):
    c, o, u = org_user("trial-once@x.be")
    o.trial_used = True
    assert "trial_period_days" not in billing.checkout_kwargs(o, u, plans.get("agent"), "fr")["subscription_data"]
    o.trial_used = False
    monkeypatch.setattr(config, "TRIAL_DAYS", 0)
    kw = billing.checkout_kwargs(o, u, plans.get("agent"), "fr")
    assert "trial_period_days" not in kw["subscription_data"] and "custom_text" not in kw


# --- free trial: webhooks and quota ---------------------------------------------------------------------

def start_trial(email, plan="agent"):
    c, o, u = org_user(email)
    obj = checkout_obj(o.id, plan, mode="subscription", paid="no_payment_required", customer=f"cus_{o.id}", subscription=f"sub_{o.id}", amount=0)
    obj["metadata"] |= {"period": "monthly", "trial": "1"}
    assert hook(c, event("checkout.session.completed", obj)).json()["outcome"] == "subscription started"
    return c, o.id


def test_a_trial_checkout_creates_a_trialing_subscription_with_a_limited_quota():
    c, oid = start_trial("trial-start@x.be")
    o = get_org(oid)
    assert o["status"] == "trialing" and o["trial_used"] is True and o["trial_ends_at"] is not None
    with SessionLocal() as db:
        b = balance(db.get(Org, oid))
    assert b["trialing"] and b["quota"] == 3 and b["quota_left"] == 3  # 3 during the trial, not the plan's 15


def test_the_zero_euro_invoice_that_opens_a_trial_does_not_end_it():
    c, oid = start_trial("trial-inv0@x.be")
    r = hook(c, event("invoice.paid", invoice_obj(oid, iid="in_trial0", amount=0, subscription=f"sub_{oid}", customer=f"cus_{oid}")))
    assert r.json()["outcome"] == "invoice recorded" and get_org(oid)["status"] == "trialing"


def test_the_first_real_payment_ends_the_trial_and_unlocks_the_full_quota():
    c, oid = start_trial("trial-paid@x.be")
    hook(c, event("invoice.paid", invoice_obj(oid, iid="in_real", amount=4900, subscription=f"sub_{oid}", customer=f"cus_{oid}")))
    assert get_org(oid)["status"] == "active"
    with SessionLocal() as db:
        assert balance(db.get(Org, oid))["quota"] == 15


def test_trial_end_date_follows_stripe_and_a_cancellation_stops_everything():
    c, oid = start_trial("trial-sub@x.be")
    end = int((dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2)).timestamp())
    hook(c, event("customer.subscription.updated", subscription_obj(oid, sid=f"sub_{oid}", status="trialing", customer=f"cus_{oid}") | {"trial_end": end}))
    assert abs(get_org(oid)["trial_ends_at"].timestamp() - end) < 2 and get_org(oid)["status"] == "trialing"
    hook(c, event("customer.subscription.deleted", subscription_obj(oid, sid=f"sub_{oid}", status="canceled", customer=f"cus_{oid}")))
    with SessionLocal() as db:
        assert balance(db.get(Org, oid))["quota"] == 0  # cancelled before the end: nothing owed, nothing left


def test_during_the_trial_only_three_dossiers_can_be_analysed():
    c, oid = start_trial("trial-cap@x.be")
    set_org(oid, credits=0)  # (the test environment gives every new account many credits; here only the quota is under test)
    results = []
    for i in range(4):
        cid = new_case(c, f"t{i}")
        from tests.fixtures import DEED
        c.post(f"/cases/{cid}/documents", files=[("files", ("akte.txt", DEED.encode(), "text/plain"))])
        results.append(c.post(f"/cases/{cid}/analyze", follow_redirects=False).status_code)
    assert results == [303, 303, 303, 402]
    assert get_org(oid)["cycle_used"] == 3


# --- pages ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("lang", LANGS)
def test_pricing_and_landing_announce_the_trial_with_its_conditions(lang):
    pricing = page_text(anon(lang).get("/pricing"))
    assert CATALOGS[lang]["pricing.trial_badge"].format(days=3) in pricing
    note = CATALOGS[lang]["pricing.trial_note"].format(days=3, dossiers=3)
    assert note in pricing  # card required, automatic charge, cancel before the end, limited quota, once per organisation
    assert CATALOGS[lang]["landing.trial"].format(days=3) in page_text(anon(lang).get("/"))


def test_nothing_is_announced_when_the_trial_is_switched_off_or_already_used(monkeypatch):
    c, o, u = org_user("trial-used@x.be")
    set_org(o.id, trial_used=True)
    assert "d'essai gratuit" not in page_text(c.get("/pricing")) or "Essai gratuit" in page_text(c.get("/pricing"))  # used: no trial badge for this organisation
    assert CATALOGS["fr"]["pricing.trial_badge"].format(days=3) not in page_text(c.get("/pricing"))
    monkeypatch.setattr(config, "TRIAL_DAYS", 0)
    assert CATALOGS["fr"]["pricing.trial_badge"].format(days=3) not in page_text(anon().get("/pricing"))
    assert CATALOGS["fr"]["landing.trial"].format(days=3) not in page_text(anon().get("/"))


def test_the_account_page_shows_the_trial_end_and_what_happens_next():
    c, oid = start_trial("trial-acct@x.be")
    body = page_text(c.get("/account"))
    assert "Essai gratuit jusqu'au" in body and "résiliation avant cette date" in body


def test_the_terms_describe_the_trial_when_one_is_offered(monkeypatch):
    assert "Essai gratuit" in page_text(anon("fr").get("/terms")) and "3 jours" in page_text(anon("fr").get("/terms"))
    monkeypatch.setattr(config, "TRIAL_DAYS", 0)
    assert "Essai gratuit" not in page_text(anon("fr").get("/terms"))
