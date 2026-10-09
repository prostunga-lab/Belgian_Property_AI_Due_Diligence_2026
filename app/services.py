"""Business logic shared by the web UI and the public API."""
from __future__ import annotations

import datetime as dt
import shutil
import time
from pathlib import Path

from sqlalchemy import update
from sqlalchemy.orm import Session

from . import summary as property_summary
from . import config, plans, storage
from .errors import AppError
from .analysis import analyze_case, process_document
from .ingest import supported_extensions
from . import render
from .models import AuditLog, Case, Document, Org, User
from .rules import RULESET_VERSION


def audit(db: Session, user: User, action: str, case_id: int | None = None, detail: str = "") -> None:
    db.add(AuditLog(org_id=user.org_id, case_id=case_id, user_id=user.id, action=action, detail=detail))


def get_case(db: Session, user: User, case_id: int) -> Case:
    case = db.get(Case, case_id)
    if not case or case.org_id != user.org_id:  # strict tenant separation
        raise AppError(404, "err.not_found.case")
    return case


def require_verified(user: User) -> None:
    if config.REQUIRE_EMAIL_VERIFICATION and not user.email_verified:
        raise AppError(403, "err.email_unverified")


def case_dir(case: Case) -> Path:
    return config.UPLOAD_DIR / str(case.org_id) / str(case.id)


def add_document(db: Session, case: Case, filename: str, data: bytes) -> Document:
    if len(case.documents) >= config.DOSSIER_MAX_DOCUMENTS:
        raise AppError(400, "err.dossier_full", max=config.DOSSIER_MAX_DOCUMENTS)
    ext = Path(filename or "").suffix.lower()
    if ext not in supported_extensions():
        raise AppError(400, "err.unsupported_file", ext=ext or "?")
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise AppError(413, "err.file_too_large", mb=config.MAX_UPLOAD_MB)
    path = storage.save(case.org_id, case.id, filename, data)
    doc = Document(case_id=case.id, filename=path.name.split("_", 1)[1], stored_path=str(path))
    try:
        process_document(doc)
    except Exception as e:
        path.unlink(missing_ok=True)
        raise AppError(400, "err.unreadable_file", name=doc.filename, exc=type(e).__name__)
    case.documents.append(doc)
    return doc


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _aware(moment: dt.datetime) -> dt.datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=dt.timezone.utc)  # SQLite hands back naive datetimes


def subscription_active(org: Org) -> bool:
    plan = plans.get(org.plan)
    return org.subscription_status in plans.SUBSCRIPTION_ACTIVE and plan is not None and plan.kind == "subscription"


def quota_state(org: Org, now: dt.datetime | None = None) -> tuple[int, dt.datetime | None]:
    """(dossiers used in the CURRENT monthly cycle, date the quota renews). The quota clock is monthly whatever the billing period
    (monthly / 6-monthly / yearly invoices): it runs from the subscription anniversary, so a yearly payer still gets a fresh quota each month."""
    if not org.cycle_started_at:
        return org.cycle_used, None
    start, elapsed = plans.cycle(_aware(org.cycle_started_at), now or _utcnow())
    return (0 if elapsed else org.cycle_used), plans.add_months(start, 1)


def balance(org: Org, now: dt.datetime | None = None) -> dict:
    """What an organisation can still spend: monthly quota left (subscribers) + purchased dossier credits."""
    plan = plans.get(org.plan) if subscription_active(org) else None
    quota = plan.dossiers if plan else 0
    used, renews_on = quota_state(org, now) if plan else (0, None)
    left = max(0, quota - used) if plan else 0
    return {"credits": org.credits, "subscribed": bool(plan), "plan": plan, "quota": quota, "used": used, "quota_left": left,
            "renews_on": renews_on, "period": org.billing_period, "status": org.subscription_status,
            "cancel_at_period_end": bool(org.cancel_at_period_end), "available": left + org.credits}


def _roll_quota_cycle(db: Session, org: Org) -> None:
    """Start a new monthly cycle when the previous one has elapsed. Compare-and-set: concurrent requests reset it exactly once,
    and it happens inside the caller's transaction (undone with it if the analysis fails)."""
    now, loaded = _utcnow(), org.cycle_started_at
    if loaded is None:
        db.execute(update(Org).where(Org.id == org.id, Org.cycle_started_at.is_(None)).values(cycle_started_at=now))
        return
    start, elapsed = plans.cycle(_aware(loaded), now)
    if elapsed:
        new = start if loaded.tzinfo else start.replace(tzinfo=None)
        db.execute(update(Org).where(Org.id == org.id, Org.cycle_started_at == loaded).values(cycle_started_at=new, cycle_used=0))


def billing_preview(org: Org, case: Case) -> str:
    """What analysing this case would do: 'billed' (already paid), 'quota', 'credit' or 'none' (nothing left to spend)."""
    if case.billed:
        return "billed"
    b = balance(org)
    return "quota" if b["quota_left"] > 0 else "credit" if b["credits"] > 0 else "none"


def charge_for_analysis(db: Session, case: Case) -> str | None:
    """Spend ONE dossier for a case that has not been paid yet: monthly quota first, then purchased credits.

    Both debits are conditional UPDATEs (never negative, never double spent under concurrency) and run inside the caller's
    transaction: if the analysis fails afterwards and the transaction is rolled back, nothing was spent.
    Returns the source ('quota' | 'credit') or None when the case was already paid (re-analysis is free).
    """
    if case.billed:
        return None
    if len(case.documents) > config.DOSSIER_MAX_DOCUMENTS:
        raise AppError(400, "err.too_many_documents", max=config.DOSSIER_MAX_DOCUMENTS)
    org = db.get(Org, case.org_id)
    source = None
    plan = plans.get(org.plan)
    if plan and plan.kind == "subscription":
        if org.subscription_status in plans.SUBSCRIPTION_ACTIVE:
            _roll_quota_cycle(db, org)
        res = db.execute(update(Org).where(Org.id == org.id, Org.subscription_status.in_(plans.SUBSCRIPTION_ACTIVE), Org.cycle_used < plan.dossiers)
                         .values(cycle_used=Org.cycle_used + 1))
        source = "quota" if res.rowcount else None
    if source is None:
        res = db.execute(update(Org).where(Org.id == org.id, Org.credits >= 1).values(credits=Org.credits - 1))
        source = "credit" if res.rowcount else None
    if source is None:
        raise AppError(402, "err.quota_exhausted" if subscription_active(org) else "err.insufficient_credits")
    case.billed, case.billing_source, case.billed_at = True, source, dt.datetime.now(dt.timezone.utc)
    return source


def run_analysis(db: Session, user: User, case: Case, lang: str = "en") -> str | None:
    require_verified(user)
    if not case.documents:
        raise AppError(400, "err.no_documents")
    source = charge_for_analysis(db, case)
    started = time.perf_counter()
    analyze_case(db, case, lang)
    case.analysis_seconds = round(time.perf_counter() - started, 3)
    audit(db, user, "case.analyze", case.id, f"{RULESET_VERSION}; billed={source or 'no'}; seconds={case.analysis_seconds}")
    return source


def delete_case_data(db: Session, case: Case) -> None:
    folder = case_dir(case)
    db.delete(case)
    db.flush()
    shutil.rmtree(folder, ignore_errors=True)


def case_payload(case: Case, lang: str = "en") -> dict:
    """Case as JSON. Finding texts are rendered in ``lang``; ``title_code``-style identifiers (rule, params) stay stable."""
    return {
        "id": case.id, "title": case.title, "address": case.address, "status": case.status, "scores": case.scores,
        "ruleset": RULESET_VERSION, "lang": lang, "ai_summary": case.ai_summary,
        "billing": {"billed": case.billed, "source": case.billing_source}, "analysis_seconds": case.analysis_seconds,
        "summary": property_summary.build(case.documents, lang), "timeline": property_summary.timeline(case.documents, lang),
        "documents": [{"id": d.id, "filename": d.filename, "type": d.doc_type, "confidence": d.classification_confidence,
                       "fields": d.fields, "ocr_pages": d.ocr_pages, "ai_analysis": d.ai_analysis} for d in case.documents],
        "findings": [finding_view(f, lang) | {"params": f.params} for f in case.findings],
    }


def finding_view(f, lang: str) -> dict:
    """A finding with its text rendered in ``lang`` (rows from before i18n fall back to their stored English text)."""
    text = render.finding_text(f.rule_id, f.params, lang, {"title": f.title, "detail": f.detail, "recommendation": f.recommendation})
    return {"id": f.id, "rule": f.rule_id, "rule_id": f.rule_id, "domain": f.domain, "severity": f.severity, "kind": f.kind,
            "sources": f.sources, "review_status": f.review_status, "question_for": f.question_for, **text}
