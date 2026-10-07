"""Credit packs via Stripe Checkout (one-off payment) + idempotent webhook."""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import config
from .auth import current_user, get_db
from .errors import AppError
from .models import Org, Payment, User
from .services import audit

router = APIRouter()
log = logging.getLogger("uvicorn.error")
PAID_EVENTS = {"checkout.session.completed", "checkout.session.async_payment_succeeded"}


def configured() -> bool:
    return bool(config.STRIPE_SECRET_KEY and config.STRIPE_PRICE_ID)


@router.post("/billing/checkout")
def checkout(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not configured():
        raise AppError(503, "err.payment_not_configured")
    import stripe

    session = stripe.checkout.Session.create(
        api_key=config.STRIPE_SECRET_KEY, mode="payment",
        line_items=[{"price": config.STRIPE_PRICE_ID, "quantity": 1}],
        client_reference_id=str(user.org_id), customer_email=user.email,
        success_url=f"{config.BASE_URL}/account?paid=1", cancel_url=f"{config.BASE_URL}/account",
    )
    audit(db, user, "billing.checkout", detail=session.id)
    db.commit()
    return RedirectResponse(session.url, status_code=303)


@router.post("/billing/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    import stripe

    payload = await request.body()
    try:  # signature + timestamp tolerance are verified by Stripe's library...
        stripe.Webhook.construct_event(payload, request.headers.get("stripe-signature", ""), config.STRIPE_WEBHOOK_SECRET)
        event = json.loads(payload)  # ...then read as plain JSON (StripeObject has no dict API in recent versions)
    except Exception:
        raise AppError(400, "err.invalid_signature")
    if event.get("type") in PAID_EVENTS:
        s = event.get("data", {}).get("object", {})
        ref = s.get("client_reference_id")
        if s.get("payment_status") == "paid" and ref and str(ref).isdigit() and db.get(Org, int(ref)):
            # Payment row + credit in ONE transaction; session_id is the primary key, so a replayed webhook is a no-op.
            db.add(Payment(session_id=s["id"], org_id=int(ref), credits=config.PACK_CREDITS))
            try:
                db.flush()
            except IntegrityError:
                db.rollback()
                return {"received": True, "duplicate": True}
            db.execute(update(Org).where(Org.id == int(ref)).values(credits=Org.credits + config.PACK_CREDITS))
            db.commit()
            log.info("credited org=%s +%s", ref, config.PACK_CREDITS)
    return {"received": True}
