"""Pricing catalogue = single source of truth for what is displayed AND what Stripe charges (inline ``price_data``).

Strategy (two audiences):
  * Private investor  -> pay per complete dossier (credits), 15-29 EUR per dossier. No monthly commitment.
  * Real-estate agent -> monthly subscription, 49-99 EUR / month, e.g. limited to 15 dossiers per month.
  * Agency            -> subscription at 149 EUR / month (larger quota).
Subscriptions can be paid monthly, every 6 months or yearly, with a progressive discount (default 0 % / 5 % / 10 %).
The dossier QUOTA is always monthly, whatever the billing period: it is renewed by our own monthly clock (see ``cycle``), not by invoices.
Defaults can be changed without touching code (env PLAN_<ID>_PRICE_EUR, PLAN_<ID>_DOSSIERS, DISCOUNT_SEMIANNUAL_PCT, DISCOUNT_ANNUAL_PCT).
One *dossier* = one complete case analysed (up to ``config.DOSSIER_MAX_DOCUMENTS`` documents); re-analysing it is free.
"""
from __future__ import annotations

import calendar
import datetime as dt
import os
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation

STRATEGY_PAYG_PER_DOSSIER_EUR = (15, 29)       # range per dossier for private investors
STRATEGY_SUBSCRIPTION_EUR_MONTH = (49, 99)     # range per month for agents
STRATEGY_AGENCY_EUR_MONTH = 149                # agencies
PERIODS = {"monthly": 1, "semiannual": 6, "annual": 12}  # billing period -> months paid per invoice
DEFAULT_DISCOUNTS = {"monthly": 0, "semiannual": 5, "annual": 10}  # progressive: the longer the commitment, the bigger the discount
SUBSCRIPTION_ACTIVE = ("active", "trialing")


@dataclass(frozen=True)
class Plan:
    id: str
    kind: str            # "payg" (one-off purchase of dossier credits) | "subscription" (monthly quota)
    audience: str        # "investor" | "agent"
    dossiers: int        # payg: credits granted per purchase | subscription: dossiers included per month
    price_cents: int
    interval: str | None = None   # "month" for subscriptions

    @property
    def per_dossier_cents(self) -> int:
        return round(self.price_cents / self.dossiers)


DEFAULTS = (
    Plan("single", "payg", "investor", 1, 2900),                    # top of the 15-29 range: one dossier on its own
    Plan("pack5", "payg", "investor", 5, 7500),                     # bottom of the range: 15 EUR per dossier in a pack of five
    Plan("agent", "subscription", "agent", 15, 4900, "month"),      # bottom of the 49-99 range, 15 dossiers / month
    Plan("agency", "subscription", "agency", 60, 14900, "month"),   # 149 EUR / month; the quota is an assumption (env PLAN_AGENCY_DOSSIERS)
)


def _eur_to_cents(raw: str | None) -> int | None:
    try:
        cents = int((Decimal((raw or "").strip().replace(",", ".")) * 100).to_integral_value())
    except (InvalidOperation, ValueError):
        return None
    return cents if cents > 0 else None


def _int(raw: str | None) -> int | None:
    try:
        value = int((raw or "").strip())
    except ValueError:
        return None
    return value if value > 0 else None


def load() -> dict[str, Plan]:
    """Defaults + env overrides, re-read on every call so a redeploy with new variables is enough."""
    plans = {}
    for p in DEFAULTS:
        price = _eur_to_cents(os.environ.get(f"PLAN_{p.id.upper()}_PRICE_EUR"))
        dossiers = _int(os.environ.get(f"PLAN_{p.id.upper()}_DOSSIERS"))
        plans[p.id] = replace(p, price_cents=price or p.price_cents, dossiers=dossiers or p.dossiers)
    return plans


def discounts() -> dict[str, int]:
    """Discount in % per billing period. Invalid or non-progressive overrides fall back to the defaults (never a surprise price)."""
    semi, annual = _pct(os.environ.get("DISCOUNT_SEMIANNUAL_PCT")), _pct(os.environ.get("DISCOUNT_ANNUAL_PCT"))
    d = dict(DEFAULT_DISCOUNTS)
    if semi is not None:
        d["semiannual"] = semi
    if annual is not None:
        d["annual"] = annual
    return d if 0 <= d["semiannual"] <= d["annual"] <= 60 else dict(DEFAULT_DISCOUNTS)


def _pct(raw: str | None) -> int | None:
    try:
        value = int((raw or "").strip())
    except ValueError:
        return None
    return value if 0 <= value <= 60 else None


@dataclass(frozen=True)
class Offer:
    """One way to pay for a subscription plan."""
    period: str
    months: int
    discount_pct: int
    total_cents: int          # what is invoiced every ``months`` months
    list_total_cents: int     # the same months at the monthly list price
    per_month_cents: int      # effective monthly price


def offer(plan: Plan, period: str) -> Offer | None:
    if plan.kind != "subscription" or period not in PERIODS:
        return None
    months, pct = PERIODS[period], discounts()[period]
    listed = plan.price_cents * months
    total = round(listed * (100 - pct) / 100)
    return Offer(period, months, pct, total, listed, round(total / months))


def offers(plan: Plan) -> list[Offer]:
    return [o for period in PERIODS if (o := offer(plan, period))]


def add_months(moment: dt.datetime, n: int) -> dt.datetime:
    """Calendar-month arithmetic that clamps the day (31 Jan + 1 month = 28/29 Feb)."""
    year, month0 = divmod(moment.month - 1 + n, 12)
    year, month = moment.year + year, month0 + 1
    return moment.replace(year=year, month=month, day=min(moment.day, calendar.monthrange(year, month)[1]))


def cycle(start: dt.datetime, now: dt.datetime) -> tuple[dt.datetime, int]:
    """Current monthly quota cycle for a subscription that started at ``start``: (cycle start, whole months elapsed)."""
    elapsed = 0
    while elapsed < 600 and add_months(start, elapsed + 1) <= now:
        elapsed += 1
    return add_months(start, elapsed), elapsed


def get(plan_id: str | None) -> Plan | None:
    return load().get(plan_id or "")


def by_kind(kind: str) -> list[Plan]:
    return [p for p in load().values() if p.kind == kind]


def format_price(cents: int, lang: str = "fr") -> str:
    amount = cents / 100
    number = f"{amount:.0f}" if cents % 100 == 0 else f"{amount:.2f}"
    if lang == "en":
        return f"€{number}"
    if lang == "nl":
        return f"€ {number.replace('.', ',')}"
    return f"{number.replace('.', ',')} €"
