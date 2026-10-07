"""Direct database access for tests that need to put an organisation into a given billing state."""
from sqlalchemy import select

from app.models import Org, SessionLocal, User


def org_of(email: str) -> int:
    with SessionLocal() as db:
        return db.scalar(select(User).where(User.email == email)).org_id


def get_org(org_id: int) -> dict:
    with SessionLocal() as db:
        o = db.get(Org, org_id)
        return {"credits": o.credits, "plan": o.plan, "status": o.subscription_status, "cycle_used": o.cycle_used,
                "customer": o.stripe_customer_id, "subscription": o.stripe_subscription_id, "cancel_at_period_end": o.cancel_at_period_end}


def org_credits(org_id: int) -> int:
    return get_org(org_id)["credits"]


def set_org(org_id: int, **fields) -> None:
    with SessionLocal() as db:
        o = db.get(Org, org_id)
        for k, v in fields.items():
            setattr(o, k, v)
        db.commit()


def force_credits(org_id: int, n: int) -> None:
    set_org(org_id, credits=n)


def subscribe(org_id: int, status: str = "active", used: int = 0, credits: int = 0) -> None:
    set_org(org_id, plan="agent", subscription_status=status, cycle_used=used, credits=credits,
            stripe_customer_id=f"cus_{org_id}", stripe_subscription_id=f"sub_{org_id}")
