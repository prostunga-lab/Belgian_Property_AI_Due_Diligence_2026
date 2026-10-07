"""Presentation of the plan catalogue (prices are formatted from app.plans, the same numbers Stripe is asked to charge)."""
from __future__ import annotations

from . import plans
from .billing import plan_name


def card(plan: plans.Plan, lang: str) -> dict:
    c = _base(plan, lang)
    if plan.kind == "subscription":
        c["offers"] = [{"period": o.period, "months": o.months, "discount_pct": o.discount_pct, "total": plans.format_price(o.total_cents, lang),
                        "per_month": plans.format_price(o.per_month_cents, lang), "list_total": plans.format_price(o.list_total_cents, lang),
                        "total_cents": o.total_cents} for o in plans.offers(plan)]
    return c


def _base(plan: plans.Plan, lang: str) -> dict:
    return {"id": plan.id, "kind": plan.kind, "name": plan_name(plan, lang), "dossiers": plan.dossiers,
            "price": plans.format_price(plan.price_cents, lang), "per_case": plans.format_price(plan.per_dossier_cents, lang),
            "price_cents": plan.price_cents}


def cards(lang: str) -> dict:
    return {"payg": [card(p, lang) for p in plans.by_kind("payg")], "subscription": [card(p, lang) for p in plans.by_kind("subscription")]}
