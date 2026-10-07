import hashlib
import hmac
import json
import time
import uuid

SECRET = "whsec_test_secret"


def signed(event: dict, secret: str = SECRET, ts: int | None = None):
    body = json.dumps(event)
    ts = ts or int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()
    return body, {"stripe-signature": f"t={ts},v1={sig}", "content-type": "application/json"}


def event(etype: str, obj: dict, eid: str | None = None) -> dict:
    return {"id": eid or f"evt_{uuid.uuid4().hex[:12]}", "object": "event", "type": etype, "api_version": "2020-08-27", "data": {"object": obj}}


def checkout_obj(org_id, plan_id, *, mode="payment", paid="paid", sid=None, customer=None, subscription=None, amount=2900) -> dict:
    return {"id": sid or f"cs_{uuid.uuid4().hex[:10]}", "object": "checkout.session", "mode": mode, "payment_status": paid,
            "client_reference_id": str(org_id), "metadata": {"org_id": str(org_id), "plan_id": plan_id}, "customer": customer,
            "subscription": subscription, "amount_total": amount}


def invoice_obj(org_id=None, *, iid=None, reason="subscription_cycle", amount=4900, subscription="sub_1", customer="cus_1", new_api=False) -> dict:
    inv = {"id": iid or f"in_{uuid.uuid4().hex[:10]}", "object": "invoice", "billing_reason": reason, "amount_paid": amount, "customer": customer}
    meta = {"org_id": str(org_id)} if org_id is not None else {}
    if new_api:  # API versions since 2025-03-31: the subscription moved under "parent"
        inv["parent"] = {"subscription_details": {"subscription": subscription, "metadata": meta}}
    else:
        inv["subscription"] = subscription
        inv["subscription_details"] = {"metadata": meta}
    return inv


def subscription_obj(org_id=None, *, sid="sub_1", status="active", cancel=False, customer="cus_1") -> dict:
    return {"id": sid, "object": "subscription", "status": status, "cancel_at_period_end": cancel, "customer": customer,
            "metadata": {"org_id": str(org_id)} if org_id is not None else {}}
