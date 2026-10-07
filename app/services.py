"""Business logic shared by the web UI and the public API."""
from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy import update
from sqlalchemy.orm import Session

from . import config, storage
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


def charge_for_analysis(db: Session, case: Case) -> int:
    """Debit 1 credit per not-yet-billed document, atomically (no negative balance, no double spend).

    Runs inside the caller's transaction: if analysis fails afterwards and the transaction is rolled back,
    the credits are restored automatically.
    """
    todo = [d for d in case.documents if not d.billed]
    if not todo:
        return 0
    res = db.execute(update(Org).where(Org.id == case.org_id, Org.credits >= len(todo)).values(credits=Org.credits - len(todo)))
    if res.rowcount == 0:
        raise AppError(402, "err.insufficient_credits", n=len(todo))
    for d in todo:
        d.billed = True
    return len(todo)


def run_analysis(db: Session, user: User, case: Case, lang: str = "en") -> int:
    require_verified(user)
    if not case.documents:
        raise AppError(400, "err.no_documents")
    spent = charge_for_analysis(db, case)
    analyze_case(db, case, lang)
    audit(db, user, "case.analyze", case.id, f"{RULESET_VERSION}; credits={spent}")
    return spent


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
        "documents": [{"id": d.id, "filename": d.filename, "type": d.doc_type, "confidence": d.classification_confidence,
                       "fields": d.fields, "ocr_pages": d.ocr_pages, "ai_analysis": d.ai_analysis} for d in case.documents],
        "findings": [finding_view(f, lang) | {"params": f.params} for f in case.findings],
    }


def finding_view(f, lang: str) -> dict:
    """A finding with its text rendered in ``lang`` (rows from before i18n fall back to their stored English text)."""
    text = render.finding_text(f.rule_id, f.params, lang, {"title": f.title, "detail": f.detail, "recommendation": f.recommendation})
    return {"id": f.id, "rule": f.rule_id, "rule_id": f.rule_id, "domain": f.domain, "severity": f.severity, "kind": f.kind,
            "sources": f.sources, "review_status": f.review_status, "question_for": f.question_for, **text}
