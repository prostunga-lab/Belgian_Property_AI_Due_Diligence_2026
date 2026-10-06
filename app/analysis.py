from __future__ import annotations

import datetime as dt
from sqlalchemy.orm import Session

from . import classify, extract, ingest, storage
from .models import Case, Document, Finding
from .rules import DocView, run_rules
from .scoring import score


def process_document(doc: Document) -> None:
    with storage.plaintext(doc.stored_path) as plain:
        res = ingest.extract_pages(plain)
    pages = res.pages
    doc.pages, doc.ocr_pages, doc.warnings = pages, res.ocr_pages, res.warnings
    doc.doc_type, doc.classification_confidence = classify.classify(pages, doc.filename)
    doc.fields = extract.extract(doc.doc_type, pages)


def _key(rule_id: str, title: str, sources: list) -> tuple:
    return (rule_id, title, tuple(sorted((s.get("doc_id"), s.get("page")) for s in sources)))


def analyze_case(db: Session, case: Case) -> None:
    """Re-run the full pipeline. Findings are matched by (rule_id, title) so human validation and comments survive re-analysis."""
    for d in case.documents:
        if not d.pages:
            process_document(d)
    views = [DocView(d.id, d.filename, d.doc_type, d.pages, d.fields, d.ocr_pages, d.warnings) for d in case.documents]
    results = run_rules(views)
    existing = {_key(f.rule_id, f.title, f.sources): f for f in case.findings}
    keep = set()
    for r in results:
        key = _key(r.rule_id, r.title, r.sources)
        while key in keep:  # never let two findings share a key
            key += ("dup",)
        f = existing.get(key) or Finding(case_id=case.id)
        f.rule_id, f.rule_version, f.domain, f.severity, f.kind = r.rule_id, r.rule_version, r.domain, r.severity, r.kind
        f.title, f.detail, f.recommendation, f.question_for, f.sources = r.title, r.detail, r.recommendation, r.question_for, r.sources
        if key not in existing:
            case.findings.append(f)
        keep.add(key)
    for key, f in existing.items():
        if key not in keep:
            case.findings.remove(f)
    db.flush()
    case.scores = score(case.findings)
    case.status = "analyzed"
    case.analyzed_at = dt.datetime.now(dt.timezone.utc)
    if not case.address:
        case.address = next((d.fields["address"]["value"] for d in case.documents if "address" in d.fields), "")
