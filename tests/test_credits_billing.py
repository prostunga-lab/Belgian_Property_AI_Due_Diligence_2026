import hashlib
import hmac
import json
import time

import pytest
from sqlalchemy import select

from app import config
from app.models import Org, Payment, SessionLocal
from tests.fixtures import ASB, DEED, ELEC, EPC, pdf
from tests.helpers import credits_of, new_case, new_client, page_text


def put(c, cid, *docs):
    files = [("files", (n, pdf(t), "application/pdf")) for n, t in docs]
    assert c.post(f"/cases/{cid}/documents", files=files, follow_redirects=False).status_code == 303


def set_credits(email_client, n):
    with SessionLocal() as db:
        from app.models import User
        # find the org through the account page
        import re
        name = re.search(r"<b>(Org)</b>", email_client.get("/account").text)
        assert name
        org = db.scalars(select(Org).order_by(Org.id.desc())).first()
        return org.id


def org_credits(org_id):
    with SessionLocal() as db:
        return db.get(Org, org_id).credits


def org_of(email):
    from app.models import User
    with SessionLocal() as db:
        return db.scalar(select(User).where(User.email == email)).org_id


def force_credits(org_id, n):
    with SessionLocal() as db:
        db.get(Org, org_id).credits = n
        db.commit()


def test_one_credit_per_document_and_reanalysis_is_free():
    c = new_client("cr1@x.be")
    oid = org_of("cr1@x.be")
    force_credits(oid, 5)
    cid = new_case(c)
    put(c, cid, ("akte.pdf", DEED), ("epc.pdf", EPC))
    assert c.post(f"/cases/{cid}/analyze", follow_redirects=False).status_code == 303
    assert org_credits(oid) == 3
    c.post(f"/cases/{cid}/analyze")  # re-analysis: documents already billed
    assert org_credits(oid) == 3
    put(c, cid, ("asbest.pdf", ASB))  # only the new document is charged
    c.post(f"/cases/{cid}/analyze")
    assert org_credits(oid) == 2


def test_insufficient_credits_blocks_and_charges_nothing():
    c = new_client("cr2@x.be")
    oid = org_of("cr2@x.be")
    force_credits(oid, 1)
    cid = new_case(c)
    put(c, cid, ("akte.pdf", DEED), ("epc.pdf", EPC))
    r = c.post(f"/cases/{cid}/analyze", follow_redirects=False)
    assert r.status_code == 402 and "insuffisants" in r.json()["detail"]
    assert org_credits(oid) == 1
    assert c.get(f"/api/cases/{cid}").json()["status"] == "draft"


def test_failed_analysis_restores_credits(monkeypatch):
    import app.services as services
    c = new_client("cr3@x.be")
    oid = org_of("cr3@x.be")
    force_credits(oid, 4)
    cid = new_case(c)
    put(c, cid, ("akte.pdf", DEED), ("epc.pdf", EPC))
    monkeypatch.setattr(services, "analyze_case", lambda db, case: (_ for _ in ()).throw(RuntimeError("boom")))
    from fastapi.testclient import TestClient
    from app.main import app
    boom = TestClient(app, raise_server_exceptions=False)
    boom.cookies = c.cookies
    assert boom.post(f"/cases/{cid}/analyze").status_code == 500
    assert org_credits(oid) == 4  # debit rolled back with the failed transaction
    assert [d["type"] for d in c.get(f"/api/cases/{cid}").json()["documents"]]  # docs still there


def test_concurrent_style_double_spend_is_impossible():
    """Two cases competing for the last credits: the conditional UPDATE lets only one succeed."""
    c = new_client("cr4@x.be")
    oid = org_of("cr4@x.be")
    force_credits(oid, 2)
    a, b = new_case(c, "a"), new_case(c, "b")
    put(c, a, ("akte.pdf", DEED), ("epc.pdf", EPC))
    put(c, b, ("asbest.pdf", ASB), ("keuring.pdf", ELEC))
    assert c.post(f"/cases/{a}/analyze", follow_redirects=False).status_code == 303
    assert c.post(f"/cases/{b}/analyze").status_code == 402
    assert org_credits(oid) == 0


def test_credits_shown_and_new_org_gets_free_credits(monkeypatch):
    monkeypatch.setattr(config, "FREE_CREDITS", 7)
    c = new_client("cr5@x.be")
    assert credits_of(c) == 7


# --- Stripe webhook ---------------------------------------------------------------------------------

SECRET = "whsec_test_secret"


def signed(payload: dict, secret=SECRET, ts=None):
    body = json.dumps(payload)
    ts = ts or int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()
    return body, {"stripe-signature": f"t={ts},v1={sig}", "content-type": "application/json"}


def event(org_id, session_id="cs_1", paid="paid", etype="checkout.session.completed"):
    return {"id": "evt_" + session_id, "object": "event", "type": etype, "api_version": "2020-08-27",
            "data": {"object": {"id": session_id, "object": "checkout.session", "client_reference_id": str(org_id), "payment_status": paid}}}


@pytest.fixture
def stripe_cfg(monkeypatch):
    monkeypatch.setattr(config, "STRIPE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(config, "PACK_CREDITS", 20)


def test_webhook_credits_once_and_is_idempotent(stripe_cfg):
    c = new_client("st1@x.be")
    oid = org_of("st1@x.be")
    force_credits(oid, 0)
    body, h = signed(event(oid, "cs_idem"))
    assert c.post("/billing/webhook", content=body, headers=h).status_code == 200
    assert org_credits(oid) == 20
    again = c.post("/billing/webhook", content=body, headers=h)  # Stripe retries deliver the same event
    assert again.status_code == 200 and again.json().get("duplicate") is True
    assert org_credits(oid) == 20
    with SessionLocal() as db:
        assert db.get(Payment, "cs_idem").org_id == oid


def test_webhook_rejects_bad_signature_and_old_timestamp(stripe_cfg):
    c = new_client("st2@x.be")
    oid = org_of("st2@x.be")
    force_credits(oid, 0)
    body, h = signed(event(oid, "cs_bad"), secret="whsec_wrong")
    assert c.post("/billing/webhook", content=body, headers=h).status_code == 400
    body, h = signed(event(oid, "cs_old"), ts=int(time.time()) - 3600)
    assert c.post("/billing/webhook", content=body, headers=h).status_code == 400
    assert c.post("/billing/webhook", content=body).status_code == 400
    assert org_credits(oid) == 0


def test_webhook_ignores_unpaid_and_unknown_org(stripe_cfg):
    c = new_client("st3@x.be")
    oid = org_of("st3@x.be")
    force_credits(oid, 0)
    for ev in (event(oid, "cs_unpaid", paid="unpaid"), event(999999, "cs_ghost"), event("abc", "cs_nan")):
        body, h = signed(ev)
        assert c.post("/billing/webhook", content=body, headers=h).status_code == 200
    assert org_credits(oid) == 0
    # async payment methods: credited when the async success event arrives
    body, h = signed(event(oid, "cs_async", etype="checkout.session.async_payment_succeeded"))
    c.post("/billing/webhook", content=body, headers=h)
    assert org_credits(oid) == 20


def test_checkout_not_configured_returns_503():
    c = new_client("st4@x.be")
    assert c.post("/billing/checkout").status_code == 503
    assert "n'est pas configuré" in page_text(c.get("/account"))


def test_webhook_works_without_origin_header_but_pages_still_csrf_protected(stripe_cfg):
    c = new_client("st5@x.be")
    oid = org_of("st5@x.be")
    body, h = signed(event(oid, "cs_noorigin"))
    assert c.post("/billing/webhook", content=body, headers=h).status_code == 200
    assert c.post("/cases", data={"title": "x"}, headers={"origin": "https://evil.example"}).status_code == 403


def test_browser_gets_readable_error_page_with_buy_link():
    c = new_client("cr6@x.be")
    oid = org_of("cr6@x.be")
    force_credits(oid, 0)
    cid = new_case(c)
    put(c, cid, ("akte.pdf", DEED))
    r = c.post(f"/cases/{cid}/analyze", headers={"accept": "text/html"})
    assert r.status_code == 402 and "Acheter des crédits" in r.text and "Crédits insuffisants" in r.text
    assert c.post(f"/cases/{cid}/analyze").json()["detail"].startswith("Crédits insuffisants")  # API clients still get JSON
