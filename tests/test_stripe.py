import json

import pytest
import stripe
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import billing, config, plans
from app.main import app
from app.models import Payment, SessionLocal, StripeEvent
from tests.helpers import new_client
from tests.org_helpers import force_credits, get_org, org_of, set_org, subscribe
from tests.stripe_helpers import SECRET, checkout_obj, event, invoice_obj, signed, subscription_obj


@pytest.fixture(autouse=True)
def stripe_config(monkeypatch):
    monkeypatch.setattr(config, "STRIPE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(config, "STRIPE_SECRET_KEY", "sk_test_123")


def hook(client, ev, **kw):
    body, headers = signed(ev, **kw)
    return client.post("/billing/webhook", content=body, headers=headers)


def payments(org_id):
    with SessionLocal() as db:
        return [(p.session_id, p.kind, p.credits, p.amount_cents, p.plan_id) for p in db.scalars(select(Payment).where(Payment.org_id == org_id))]


def org(email):
    c = new_client(email)
    return c, org_of(email)


# --- pay-per-dossier credits (investors) ---------------------------------------------------------------------

@pytest.mark.parametrize("plan_id,granted", [("single", 1), ("pack5", 5)])
def test_a_paid_checkout_grants_the_dossiers_of_that_plan(plan_id, granted):
    c, oid = org(f"st-pay-{plan_id}@x.be"); force_credits(oid, 0)
    r = hook(c, event("checkout.session.completed", checkout_obj(oid, plan_id, sid=f"cs_{plan_id}", amount=plans.get(plan_id).price_cents)))
    assert r.status_code == 200 and get_org(oid)["credits"] == granted
    assert payments(oid) == [(f"cs_{plan_id}", "credits", granted, plans.get(plan_id).price_cents, plan_id)]


def test_replays_never_credit_twice():
    c, oid = org("st-replay@x.be"); force_credits(oid, 0)
    ev = event("checkout.session.completed", checkout_obj(oid, "pack5", sid="cs_replay"), eid="evt_same")
    assert hook(c, ev).json()["outcome"] == "credited 5"
    assert hook(c, ev).json()["outcome"] == "duplicate event"  # Stripe retry: same event id
    other_event_same_session = event("checkout.session.async_payment_succeeded", checkout_obj(oid, "pack5", sid="cs_replay"))
    assert hook(c, other_event_same_session).json()["outcome"] == "duplicate payment"  # same payment announced by another event
    assert get_org(oid)["credits"] == 5 and len(payments(oid)) == 1


def test_unpaid_async_checkout_is_credited_only_when_the_payment_succeeds():
    c, oid = org("st-async@x.be"); force_credits(oid, 0)
    hook(c, event("checkout.session.completed", checkout_obj(oid, "single", paid="unpaid", sid="cs_async")))
    assert get_org(oid)["credits"] == 0
    hook(c, event("checkout.session.async_payment_succeeded", checkout_obj(oid, "single", paid="paid", sid="cs_async")))
    assert get_org(oid)["credits"] == 1


def test_unknown_organisation_plan_or_mode_is_ignored_without_error():
    c, oid = org("st-ign@x.be"); force_credits(oid, 0)
    assert hook(c, event("checkout.session.completed", checkout_obj(999999, "single"))).json()["outcome"].startswith("ignored")
    assert hook(c, event("checkout.session.completed", checkout_obj(oid, "no-such-plan"))).json()["outcome"].startswith("ignored")
    assert hook(c, event("checkout.session.completed", checkout_obj(oid, "agent", mode="payment"))).json()["outcome"].startswith("ignored")  # plan/mode mismatch
    assert hook(c, event("charge.refunded", {"id": "ch_1"})).json()["outcome"] == "ignored: event type"
    assert get_org(oid)["credits"] == 0 and payments(oid) == []


# --- subscription lifecycle (agents) -----------------------------------------------------------------------------

def test_subscription_checkout_activates_the_plan_and_remembers_the_stripe_ids():
    c, oid = org("st-sub@x.be")
    hook(c, event("checkout.session.completed", checkout_obj(oid, "agent", mode="subscription", customer="cus_9", subscription="sub_9", sid="cs_sub")))
    o = get_org(oid)
    assert (o["plan"], o["status"], o["customer"], o["subscription"], o["cycle_used"]) == ("agent", "active", "cus_9", "sub_9", 0)
    assert payments(oid) == []  # money is recorded from the invoice, not from the checkout, to avoid double counting


def test_invoices_are_recorded_but_never_touch_the_monthly_quota_clock():
    c, oid = org("st-renew@x.be"); subscribe(oid, used=0)
    set_org(oid, stripe_subscription_id="sub_1", stripe_customer_id="cus_1")
    first = invoice_obj(oid, iid="in_first", reason="subscription_create")
    assert hook(c, event("invoice.paid", first)).json()["outcome"] == "invoice recorded"
    set_org(oid, cycle_used=11)
    assert hook(c, event("invoice.paid", first)).json()["outcome"] in ("duplicate invoice", "duplicate event")
    assert get_org(oid)["cycle_used"] == 11  # a replayed first invoice must not hand out a fresh quota
    assert hook(c, event("invoice.paid", invoice_obj(oid, iid="in_renewal", reason="subscription_cycle"))).json()["outcome"] == "invoice recorded"
    assert get_org(oid)["cycle_used"] == 11  # the quota follows its own monthly anniversary, not invoices (semi-annual/annual payers)
    assert [p[0] for p in payments(oid)] == ["in_first", "in_renewal"] and {p[1] for p in payments(oid)} == {"subscription"}
    assert payments(oid)[1][3] == 4900


def test_renewal_found_by_ids_and_in_the_newer_stripe_invoice_shape():
    c, oid = org("st-ids@x.be"); subscribe(oid, used=7)  # sets sub_<oid> / cus_<oid>
    sub, cus = f"sub_{oid}", f"cus_{oid}"
    assert hook(c, event("invoice.paid", invoice_obj(None, iid="in_a", subscription=sub, customer=cus))).json()["outcome"] == "invoice recorded"  # found by ids, no metadata at all
    set_org(oid, cycle_used=5)
    new_shape = invoice_obj(oid, iid="in_b", subscription=sub, customer=cus, new_api=True)
    assert hook(c, event("invoice.paid", new_shape)).json()["outcome"] == "invoice recorded" and get_org(oid)["cycle_used"] == 5


def test_a_failed_payment_suspends_the_quota_and_a_paid_invoice_restores_it():
    c, oid = org("st-fail@x.be"); subscribe(oid, used=0, credits=0)
    hook(c, event("invoice.payment_failed", invoice_obj(oid)))
    assert get_org(oid)["status"] == "past_due"
    r = c.post("/cases", data={"title": "t"}, follow_redirects=False)
    cid = int(r.headers["location"].rsplit("/", 1)[1])
    from tests.fixtures import DEED, pdf
    c.post(f"/cases/{cid}/documents", files=[("files", ("a.pdf", pdf(DEED), "application/pdf"))])
    assert c.post(f"/cases/{cid}/analyze").status_code == 402
    hook(c, event("invoice.paid", invoice_obj(oid, iid="in_retry", reason="subscription_cycle")))
    assert get_org(oid)["status"] == "active" and c.post(f"/cases/{cid}/analyze", follow_redirects=False).status_code == 303


def test_cancellation_at_period_end_keeps_the_quota_until_the_subscription_is_deleted():
    c, oid = org("st-cancel@x.be"); subscribe(oid, used=2)
    hook(c, event("customer.subscription.updated", subscription_obj(oid, sid=f"sub_{oid}", cancel=True, customer=f"cus_{oid}")))
    o = get_org(oid)
    assert o["status"] == "active" and o["cancel_at_period_end"] is True  # still usable until the paid period ends
    assert "prend fin" in __import__("tests.helpers", fromlist=["page_text"]).page_text(c.get("/account"))
    hook(c, event("customer.subscription.deleted", subscription_obj(oid, sid=f"sub_{oid}", status="canceled", customer=f"cus_{oid}")))
    o = get_org(oid)
    assert o["status"] == "canceled" and o["cancel_at_period_end"] is False and o["credits"] == 0


def test_status_changes_are_followed_but_a_stale_incomplete_event_cannot_downgrade_an_active_plan():
    c, oid = org("st-status@x.be"); subscribe(oid)
    s = f"sub_{oid}"
    assert hook(c, event("customer.subscription.updated", subscription_obj(oid, sid=s, status="past_due"))).json()["outcome"] == "status=past_due"
    assert get_org(oid)["status"] == "past_due"
    hook(c, event("customer.subscription.updated", subscription_obj(oid, sid=s, status="active")))
    assert hook(c, event("customer.subscription.updated", subscription_obj(oid, sid=s, status="incomplete"))).json()["outcome"] == "ignored: stale status"
    assert get_org(oid)["status"] == "active"


def test_a_handler_failure_stores_nothing_so_stripe_can_retry(monkeypatch):
    c, oid = org("st-retry@x.be"); force_credits(oid, 0)
    ev = event("checkout.session.completed", checkout_obj(oid, "single", sid="cs_retry"), eid="evt_retry")
    real = billing._on_checkout
    monkeypatch.setattr(billing, "_on_checkout", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    boom = TestClient(app, raise_server_exceptions=False)
    assert hook(boom, ev).status_code == 500
    with SessionLocal() as db:
        assert db.get(StripeEvent, "evt_retry") is None  # the event id was rolled back with everything else
    monkeypatch.setattr(billing, "_on_checkout", real)
    assert hook(c, ev).json()["outcome"] == "credited 1" and get_org(oid)["credits"] == 1


# --- signature, transport ------------------------------------------------------------------------------------------

def test_bad_signature_old_timestamp_and_missing_secret_are_rejected(monkeypatch):
    c, oid = org("st-sig@x.be"); force_credits(oid, 0)
    ev = event("checkout.session.completed", checkout_obj(oid, "single"))
    assert hook(c, ev, secret="whsec_wrong").status_code == 400
    assert hook(c, ev, ts=1_600_000_000).status_code == 400
    assert c.post("/billing/webhook", content=json.dumps(ev)).status_code == 400
    assert get_org(oid)["credits"] == 0
    monkeypatch.setattr(config, "STRIPE_WEBHOOK_SECRET", "")
    assert hook(c, ev).status_code == 503


def test_webhook_needs_no_origin_header_but_pages_stay_protected():
    c, oid = org("st-origin@x.be"); force_credits(oid, 0)
    assert hook(c, event("checkout.session.completed", checkout_obj(oid, "single"))).status_code == 200
    assert c.post("/cases", data={"title": "x"}, headers={"origin": "https://evil.example"}).status_code == 403


# --- checkout + portal requests -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("plan_id", ["single", "pack5", "agent", "agency"])
def test_checkout_charges_exactly_the_catalogue_price(plan_id):
    c, oid = org(f"st-kw-{plan_id}@x.be")
    plan = plans.get(plan_id)
    from app.models import Org, User
    with SessionLocal() as db:
        o, u = db.get(Org, oid), db.scalar(select(User).where(User.org_id == oid))
        kw = billing.checkout_kwargs(o, u, plan, "nl")
    line = kw["line_items"][0]
    expected = {"org_id": str(oid), "plan_id": plan_id, **({"period": "monthly"} if plan.kind == "subscription" else {})}
    assert line["quantity"] == 1 and line["price_data"]["unit_amount"] == plan.price_cents and line["price_data"]["currency"] == "eur"
    assert kw["metadata"] == expected and kw["client_reference_id"] == str(oid) and kw["locale"] == "nl"
    assert kw["customer_email"] == f"st-kw-{plan_id}@x.be" and kw["success_url"].endswith("/account?paid=1") and kw["cancel_url"].endswith("/pricing")
    name = line["price_data"]["product_data"]["name"]
    assert ("dossier" in name) if plan.kind == "payg" else ("mensuel" in name.lower() or "mois" in name.lower() or "maand" in name.lower())
    if plan.kind == "subscription":
        assert kw["mode"] == "subscription" and line["price_data"]["recurring"] == {"interval": "month", "interval_count": 1} and kw["subscription_data"]["metadata"] == kw["metadata"]
    else:
        assert kw["mode"] == "payment" and "recurring" not in line["price_data"] and kw["payment_intent_data"]["metadata"] == kw["metadata"]


def test_an_existing_stripe_customer_is_reused_instead_of_an_email():
    c, oid = org("st-cust@x.be"); set_org(oid, stripe_customer_id="cus_keep")
    from app.models import Org, User
    with SessionLocal() as db:
        kw = billing.checkout_kwargs(db.get(Org, oid), db.scalar(select(User).where(User.org_id == oid)), plans.get("single"), "fr")
    assert kw["customer"] == "cus_keep" and "customer_email" not in kw


def fake_stripe(monkeypatch, seen):
    class Obj:
        id, url = "cs_fake", "https://checkout.stripe.test/pay"
    monkeypatch.setattr(stripe.checkout.Session, "create", lambda **kw: seen.append(kw) or Obj)
    monkeypatch.setattr(stripe.billing_portal.Session, "create", lambda **kw: seen.append(kw) or type("P", (), {"url": "https://billing.stripe.test/portal"}))


def test_checkout_route_redirects_to_stripe_and_rejects_bad_requests(monkeypatch):
    seen = []; fake_stripe(monkeypatch, seen)
    c, oid = org("st-route@x.be")
    r = c.post("/billing/checkout/pack5", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "https://checkout.stripe.test/pay"
    assert seen[0]["line_items"][0]["price_data"]["unit_amount"] == plans.get("pack5").price_cents
    assert c.post("/billing/checkout/nope").status_code == 404
    assert TestClient(app).post("/billing/checkout/single", headers={"accept": "text/html"}, follow_redirects=False).status_code == 303  # to /login
    monkeypatch.setattr(config, "STRIPE_SECRET_KEY", "")
    assert c.post("/billing/checkout/single").status_code == 503


def test_an_active_subscriber_cannot_start_a_second_subscription(monkeypatch):
    seen = []; fake_stripe(monkeypatch, seen)
    c, oid = org("st-twice@x.be"); subscribe(oid)
    r = c.post("/billing/checkout/agent")
    assert r.status_code == 409 and r.json()["code"] == "err.already_subscribed" and seen == []
    assert c.post("/billing/checkout/single", follow_redirects=False).status_code == 303  # but credits can still be bought


def test_customer_portal(monkeypatch):
    seen = []; fake_stripe(monkeypatch, seen)
    c, oid = org("st-portal@x.be")
    assert c.post("/billing/portal").status_code == 404  # nothing to manage yet
    subscribe(oid)
    r = c.post("/billing/portal", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "https://billing.stripe.test/portal"
    assert seen[-1]["customer"] == f"cus_{oid}" and seen[-1]["return_url"].endswith("/account")
