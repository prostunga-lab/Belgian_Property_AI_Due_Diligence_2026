"""Stripe billing: pay-per-dossier credits (investors) and a monthly subscription with a dossier quota (agents).

The price a visitor sees and the price Stripe charges both come from ``app.plans`` (inline ``price_data``), so they cannot diverge.
Webhooks are verified by Stripe's library, de-duplicated by event id, and applied in ONE transaction (all or nothing).
"""
from __future__ import annotations

import datetime as dt
import json
import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import config, i18n, plans
from .auth import current_user, get_db
from .errors import AppError
from .models import Org, Payment, StripeEvent, User
from .services import audit, require_verified

router = APIRouter()
log = logging.getLogger("uvicorn.error")
STRIPE_LOCALES = {"fr": "fr", "nl": "nl", "en": "en"}


def configured() -> bool:
    return bool(config.STRIPE_SECRET_KEY)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# --- checkout -----------------------------------------------------------------------------------------

def plan_name(plan: plans.Plan, lang: str) -> str:
    return i18n.t(f"plan.{plan.id}.name", lang, n=plan.dossiers)


def trial_available(org: Org | None) -> bool:
    """A free trial is offered when it is configured and this organisation has not had one yet."""
    return config.TRIAL_DAYS > 0 and not (org is not None and org.trial_used)


def checkout_kwargs(org: Org, user: User, plan: plans.Plan, lang: str, period: str = "monthly") -> dict:
    """Arguments for stripe.checkout.Session.create (kept separate so they can be inspected without calling Stripe)."""
    meta = {"org_id": str(org.id), "plan_id": plan.id}
    price_data = {"currency": "eur", "unit_amount": plan.price_cents, "product_data": {"name": plan_name(plan, lang)}}
    offer = plans.offer(plan, period)  # None for one-off plans
    if offer:
        meta["period"] = period
        price_data["unit_amount"] = offer.total_cents  # what is invoiced every offer.months months, discount included
        price_data["product_data"]["name"] = f"{plan_name(plan, lang)} — {i18n.t('period.' + period, lang)}"
    kwargs = {
        "api_key": config.STRIPE_SECRET_KEY, "client_reference_id": str(org.id), "metadata": meta,
        "locale": STRIPE_LOCALES.get(lang, "auto"),
        "success_url": f"{config.BASE_URL}/account?paid=1", "cancel_url": f"{config.BASE_URL}/pricing",
    }
    if org.stripe_customer_id:
        kwargs["customer"] = org.stripe_customer_id
    else:
        kwargs["customer_email"] = user.email
    if plan.kind == "subscription":
        price_data["recurring"] = {"interval": "year"} if offer.months == 12 else {"interval": "month", "interval_count": offer.months}
        sub_data = {"metadata": meta}
        if trial_available(org):  # free trial, once per organisation: the card is collected now and charged when the trial ends
            meta["trial"] = "1"
            sub_data["trial_period_days"] = config.TRIAL_DAYS
            kwargs["payment_method_collection"] = "always"
            kwargs["custom_text"] = {"submit": {"message": i18n.t("billing.trial_message", lang, days=config.TRIAL_DAYS, dossiers=config.TRIAL_DOSSIERS,
                                                                   price=plans.format_price(offer.total_cents, lang), period=i18n.t("period." + period, lang).lower())}}
        kwargs.update(mode="subscription", subscription_data=sub_data)
    else:
        kwargs.update(mode="payment", payment_intent_data={"metadata": meta})
    kwargs["line_items"] = [{"quantity": 1, "price_data": price_data}]
    return kwargs


@router.post("/billing/checkout/{plan_id}")
def checkout(plan_id: str, request: Request, period: str = Form("monthly"), user: User = Depends(current_user), db: Session = Depends(get_db)):
    plan = plans.get(plan_id)
    if not plan:
        raise AppError(404, "err.unknown_plan")
    if plan.kind == "subscription" and period not in plans.PERIODS:
        raise AppError(400, "err.unknown_period")
    if not configured():
        raise AppError(503, "err.payment_not_configured")
    require_verified(user)
    org = db.get(Org, user.org_id)
    if plan.kind == "subscription" and org.subscription_status in plans.SUBSCRIPTION_ACTIVE:
        raise AppError(409, "err.already_subscribed")  # change or cancel through the customer portal, never a second subscription
    import stripe

    session = stripe.checkout.Session.create(**checkout_kwargs(org, user, plan, request.state.lang, period))
    audit(db, user, "billing.checkout", detail=f"{plan.id}:{period if plan.kind == 'subscription' else 'once'}:{session.id}")
    db.commit()
    return RedirectResponse(session.url, status_code=303)


@router.post("/billing/portal")
def portal(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Stripe customer portal: update the card, see invoices, cancel the subscription."""
    org = db.get(Org, user.org_id)
    if not configured():
        raise AppError(503, "err.payment_not_configured")
    if not org.stripe_customer_id:
        raise AppError(404, "err.no_subscription")
    import stripe

    session = stripe.billing_portal.Session.create(api_key=config.STRIPE_SECRET_KEY, customer=org.stripe_customer_id,
                                                   return_url=f"{config.BASE_URL}/account")
    return RedirectResponse(session.url, status_code=303)


# --- webhook ------------------------------------------------------------------------------------------

def _metadata(obj: dict) -> dict:
    """Metadata may sit on the object itself or (invoices, newer API versions) under the subscription details."""
    md = dict(obj.get("metadata") or {})
    for details in ((obj.get("subscription_details") or {}), ((obj.get("parent") or {}).get("subscription_details") or {})):
        md = {**(details.get("metadata") or {}), **md}
    return md


def _find_org(db: Session, obj: dict) -> Org | None:
    md = _metadata(obj)
    for ref in (md.get("org_id"), obj.get("client_reference_id")):
        if ref is not None and str(ref).isdigit() and (org := db.get(Org, int(ref))):
            return org
    sub_id = obj.get("subscription") or ((obj.get("parent") or {}).get("subscription_details") or {}).get("subscription")
    if obj.get("object") == "subscription":
        sub_id = obj.get("id")
    for col, val in ((Org.stripe_subscription_id, sub_id), (Org.stripe_customer_id, obj.get("customer"))):
        if isinstance(val, str) and val and (org := db.scalar(select(Org).where(col == val))):
            return org
    return None


def _record_payment(db: Session, ext_id: str, org: Org, *, credits: int, kind: str, plan_id: str | None, amount: int | None) -> bool:
    """Accounting row keyed by the Stripe id; False when this payment was already recorded."""
    db.add(Payment(session_id=ext_id, org_id=org.id, credits=credits, kind=kind, plan_id=plan_id, amount_cents=amount))
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return False
    return True


def _on_checkout(db: Session, event_type: str, s: dict) -> str:
    org = _find_org(db, s)
    if not org:
        return "ignored: unknown organisation"
    plan = plans.get(_metadata(s).get("plan_id"))
    if not plan:
        return "ignored: unknown plan"
    mode, paid = s.get("mode"), s.get("payment_status")
    if mode == "payment" and plan.kind == "payg":
        if paid != "paid":
            return "ignored: not paid yet"  # async payment methods: credited by async_payment_succeeded
        if not _record_payment(db, s["id"], org, credits=plan.dossiers, kind="credits", plan_id=plan.id, amount=s.get("amount_total")):
            return "duplicate payment"
        db.execute(update(Org).where(Org.id == org.id).values(credits=Org.credits + plan.dossiers))
        return f"credited {plan.dossiers}"
    if mode == "subscription" and plan.kind == "subscription":
        period = _metadata(s).get("period")
        org.billing_period = period if period in plans.PERIODS else "monthly"
        org.plan, org.stripe_customer_id, org.stripe_subscription_id = plan.id, s.get("customer") or org.stripe_customer_id, s.get("subscription")
        org.subscription_status = "active" if paid in ("paid", "no_payment_required") else "incomplete"
        if _metadata(s).get("trial") == "1" and paid == "no_payment_required":  # started with a free trial: limited quota until the first payment
            org.subscription_status, org.trial_used = "trialing", True
            org.trial_ends_at = _now() + dt.timedelta(days=config.TRIAL_DAYS)
        org.cancel_at_period_end, org.cycle_started_at, org.cycle_used = False, _now(), 0
        return "subscription started"
    return "ignored: mode/plan mismatch"


def _on_invoice_paid(db: Session, inv: dict) -> str:
    org = _find_org(db, inv)
    if not org:
        return "ignored: unknown organisation"
    if not _record_payment(db, inv["id"], org, credits=0, kind="subscription", plan_id=org.plan, amount=inv.get("amount_paid")):
        return "duplicate invoice"
    if (inv.get("amount_paid") or 0) > 0 or org.subscription_status != "trialing":
        org.subscription_status = "active"  # a paid invoice means the subscription is (again) in good standing
    # (the 0 EUR invoice that opens a free trial must NOT end the trial: only a real payment does)
    # The monthly QUOTA is not renewed here: with 6-monthly or yearly billing an invoice only comes every 6/12 months, while the quota
    # must come back every month. It follows its own clock (services._roll_quota_cycle).
    return "invoice recorded"


def _on_subscription(db: Session, event_type: str, sub: dict) -> str:
    org = _find_org(db, sub)
    if not org:
        return "ignored: unknown organisation"
    if event_type.endswith("deleted"):
        org.subscription_status, org.cancel_at_period_end = "canceled", False
        return "canceled"
    status = sub.get("status")
    if status in ("incomplete", "incomplete_expired") and org.subscription_status in plans.SUBSCRIPTION_ACTIVE:
        return "ignored: stale status"  # an early 'incomplete' event arriving after the subscription became active
    org.subscription_status, org.cancel_at_period_end = status, bool(sub.get("cancel_at_period_end"))
    if status == "trialing":
        org.trial_used = True
    if isinstance(sub.get("trial_end"), (int, float)):
        org.trial_ends_at = dt.datetime.fromtimestamp(sub["trial_end"], dt.timezone.utc)
    if sub.get("id"):
        org.stripe_subscription_id = sub["id"]
    return f"status={status}"


def apply_event(db: Session, event: dict) -> str:
    """Apply one verified Stripe event. Idempotent per event id; raises on bugs so Stripe retries (nothing is half-applied)."""
    etype, obj = event.get("type", ""), (event.get("data") or {}).get("object") or {}
    db.add(StripeEvent(id=event["id"], type=etype))
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return "duplicate event"
    if etype in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        return _on_checkout(db, etype, obj)
    if etype == "invoice.paid":
        return _on_invoice_paid(db, obj)
    if etype == "invoice.payment_failed":
        org = _find_org(db, obj)
        if org:
            org.subscription_status = "past_due"
        return "past_due"
    if etype in ("customer.subscription.updated", "customer.subscription.deleted"):
        return _on_subscription(db, etype, obj)
    return "ignored: event type"


@router.post("/billing/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    import stripe

    if not config.STRIPE_WEBHOOK_SECRET:
        raise AppError(503, "err.payment_not_configured")
    payload = await request.body()
    try:  # signature + timestamp tolerance are verified by Stripe's library...
        stripe.Webhook.construct_event(payload, request.headers.get("stripe-signature", ""), config.STRIPE_WEBHOOK_SECRET)
        event = json.loads(payload)  # ...then read as plain JSON (StripeObject has no dict API in recent versions)
    except Exception:
        raise AppError(400, "err.invalid_signature")
    outcome = apply_event(db, event)
    db.commit()
    log.info("stripe %s %s -> %s", event.get("type"), event.get("id"), outcome)
    return {"received": True, "outcome": outcome}
