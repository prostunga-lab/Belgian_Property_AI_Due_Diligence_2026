"""Switching plan / billing period on the existing Stripe subscription (no second subscription, prorated by Stripe)."""
import pytest
import stripe

from app import config, plans
from tests.helpers import new_client, page_text
from tests.org_helpers import get_org, org_of, set_org, subscribe


def org_row(oid):
    from app.models import Org, SessionLocal
    with SessionLocal() as db:
        return db.get(Org, oid)


class FakeStripe:
    def __init__(self, monkeypatch, fail=False):
        self.calls = []
        monkeypatch.setattr(config, "STRIPE_SECRET_KEY", "sk_test_123")
        monkeypatch.setattr(stripe.Subscription, "retrieve", lambda sid, **kw: {"id": sid, "metadata": {"org_id": "1", "trial": "1"}, "items": {"data": [{"id": "si_1"}]}})
        monkeypatch.setattr(stripe.Product, "create", lambda **kw: {"id": "prod_new", **kw})

        def modify(sid, **kw):
            if fail:
                raise stripe.error.CardError("declined", "card", "card_declined")
            self.calls.append((sid, kw))
        monkeypatch.setattr(stripe.Subscription, "modify", modify)


def sub_client(email, status="active", plan="agent", period="monthly"):
    c = new_client(email)
    oid = org_of(email)
    subscribe(oid, status)
    set_org(oid, plan=plan, billing_period=period)
    return c, oid


def test_upgrade_reprices_the_same_subscription_with_proration(monkeypatch):
    fake = FakeStripe(monkeypatch)
    c, oid = sub_client("chg-up@x.be")
    r = c.post("/billing/change", data={"plan_id": "agency", "period": "annual"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/account?changed=1"
    (sid, kw), = fake.calls
    assert sid == f"sub_{oid}" and kw["proration_behavior"] == "always_invoice" and kw["payment_behavior"] == "error_if_incomplete"
    item = kw["items"][0]
    offer = plans.offer(plans.get("agency"), "annual")
    assert item["id"] == "si_1" and item["price_data"]["unit_amount"] == offer.total_cents and item["price_data"]["recurring"] == {"interval": "year"}
    assert item["price_data"]["product"] == "prod_new" and kw["metadata"]["plan_id"] == "agency" and kw["metadata"]["period"] == "annual"
    assert get_org(oid)["plan"] == "agency" and org_row(oid).billing_period == "annual"


def test_semiannual_uses_a_six_month_interval(monkeypatch):
    fake = FakeStripe(monkeypatch)
    c, _ = sub_client("chg-semi@x.be")
    c.post("/billing/change", data={"plan_id": "agent", "period": "semiannual"})
    assert fake.calls[0][1]["items"][0]["price_data"]["recurring"] == {"interval": "month", "interval_count": 6}


def test_during_the_free_trial_nothing_is_prorated_and_the_trial_status_is_kept(monkeypatch):
    fake = FakeStripe(monkeypatch)
    c, oid = sub_client("chg-trial@x.be", status="trialing")
    c.post("/billing/change", data={"plan_id": "agency", "period": "monthly"})
    assert fake.calls[0][1]["proration_behavior"] == "none"
    assert org_row(oid).subscription_status == "trialing" and get_org(oid)["plan"] == "agency"


def test_a_refused_payment_leaves_the_subscription_unchanged(monkeypatch):
    FakeStripe(monkeypatch, fail=True)
    c, oid = sub_client("chg-fail@x.be")
    r = c.post("/billing/change", data={"plan_id": "agency", "period": "monthly"})
    assert r.status_code == 502 and get_org(oid)["plan"] == "agent"


def test_same_plan_unknown_plan_and_payg_are_refused(monkeypatch):
    fake = FakeStripe(monkeypatch)
    c, _ = sub_client("chg-bad@x.be")
    assert c.post("/billing/change", data={"plan_id": "agent", "period": "monthly"}).status_code == 409
    assert c.post("/billing/change", data={"plan_id": "nope", "period": "monthly"}).status_code == 404
    assert c.post("/billing/change", data={"plan_id": "pack5", "period": "monthly"}).status_code == 404
    assert c.post("/billing/change", data={"plan_id": "agency", "period": "weekly"}).status_code == 400
    assert not fake.calls


@pytest.mark.parametrize("status", ["canceled", "past_due", None])
def test_only_active_or_trialing_subscriptions_can_change(monkeypatch, status):
    fake = FakeStripe(monkeypatch)
    c = new_client(f"chg-inactive-{str(status).lower()}@x.be")
    set_org(org_of(f"chg-inactive-{str(status).lower()}@x.be"), plan="agent", subscription_status=status, stripe_subscription_id="sub_x")
    assert c.post("/billing/change", data={"plan_id": "agency", "period": "monthly"}).status_code == 409 and not fake.calls


def test_anonymous_visitors_cannot_change_a_plan(monkeypatch):
    FakeStripe(monkeypatch)
    from fastapi.testclient import TestClient
    from app.main import app
    r = TestClient(app).post("/billing/change", data={"plan_id": "agency", "period": "monthly"}, follow_redirects=False)
    assert r.status_code in (303, 401)


@pytest.mark.parametrize("lang", ["fr", "nl", "en"])
def test_account_and_pricing_pages_offer_the_other_plans_only(monkeypatch, lang):
    FakeStripe(monkeypatch)
    c, _ = sub_client(f"chg-ui-{lang}@x.be")
    c.get(f"/lang/{lang}?next=/account")
    acct = page_text(c.get("/account"))
    assert acct.count('action="/billing/change"') == 5  # 2 plans x 3 periods, minus the current one
    pricing = page_text(c.get("/pricing"))
    assert pricing.count('action="/billing/change"') == 5 and "/billing/checkout/agent" not in pricing


def test_quota_follows_the_new_plan_but_used_dossiers_still_count(monkeypatch):
    from app import services
    FakeStripe(monkeypatch)
    c, oid = sub_client("chg-quota@x.be")
    set_org(oid, cycle_used=7)
    c.post("/billing/change", data={"plan_id": "agency", "period": "monthly"})
    from app.models import Org, SessionLocal
    with SessionLocal() as db:
        b = services.balance(db.get(Org, oid))
    assert b["quota"] == plans.get("agency").dossiers and b["used"] == 7


# --- pricing page for visitors without an account -----------------------------------------------------------

@pytest.mark.parametrize("lang,label", [("fr", "Choisissez votre formule"), ("nl", "Kies uw formule"), ("en", "Choose your plan")])
def test_visitors_are_asked_to_choose_a_plan_then_create_an_account_and_come_back(lang, label):
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    c.get(f"/lang/{lang}")
    body = page_text(c.get("/pricing"))
    assert body.count(label) >= 3 and 'href="/login?next=/pricing#register"' in body
    login = page_text(c.get("/login?next=/pricing"))
    assert login.count('name="next" value="/pricing"') == 2
    r = c.post("/register", data={"org_name": "Org", "email": f"next-{lang}@example.com", "password": "supersecret12", "accept_terms": "1", "next": "/pricing"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/pricing"


def test_the_return_target_is_whitelisted():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    assert 'name="next"' not in c.get("/login?next=https://evil.example").text
    r = c.post("/register", data={"org_name": "Org", "email": "next-evil@example.com", "password": "supersecret12", "accept_terms": "1", "next": "//evil.example"}, follow_redirects=False)
    assert r.headers["location"] == "/"
