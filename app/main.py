from __future__ import annotations

import datetime as dt
import hmac
import os
import shutil
import time
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from . import config, storage
from .analysis import analyze_case, process_document
from .ingest import supported_extensions
from .auth import current_user, get_db, hash_password, verify_password
from .models import AuditLog, Case, Comment, Document, Finding, Org, User, init_db
from .report import build_pdf
from .rules import RULESET_VERSION

app = FastAPI(title="Belgian Property Due Diligence")
app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY, same_site="lax", https_only=config.COOKIE_SECURE, max_age=60 * 60 * 12)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
init_db()


@app.middleware("http")
async def csrf_origin_check(request: Request, call_next):
    """Reject cross-site state-changing requests: Origin (or Referer) host must match the Host header."""
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        src = request.headers.get("origin") or request.headers.get("referer")
        if src and urlparse(src).netloc != request.headers.get("host"):
            return Response('{"detail": "Cross-site request rejected"}', status_code=403, media_type="application/json")
    return await call_next(request)


_attempts: dict[str, deque] = defaultdict(deque)
LOGIN_WINDOW_S, LOGIN_MAX = 15 * 60, int(os.environ.get("LOGIN_MAX_ATTEMPTS", "8"))


def throttle(key: str) -> None:
    """In-memory login rate limit (per process; adequate for a single instance)."""
    now, q = time.monotonic(), _attempts[key]
    while q and now - q[0] > LOGIN_WINDOW_S:
        q.popleft()
    if len(q) >= LOGIN_MAX:
        raise HTTPException(429, "Too many attempts, try again later")
    q.append(now)

PLAN_QUOTAS = {"trial": 10, "agent": 40, "agency": 200}
ALLOWED_EXT = supported_extensions()


def audit(db: Session, user: User, action: str, case_id: int | None = None, detail: str = "") -> None:
    db.add(AuditLog(org_id=user.org_id, case_id=case_id, user_id=user.id, action=action, detail=detail))


def get_case(db: Session, user: User, case_id: int) -> Case:
    case = db.get(Case, case_id)
    if not case or case.org_id != user.org_id:  # strict tenant separation
        raise HTTPException(404, "Case not found")
    return case


@app.exception_handler(HTTPException)
async def http_exc(request: Request, exc: HTTPException):
    if exc.status_code == 401 and "text/html" in request.headers.get("accept", ""):
        return RedirectResponse("/login", status_code=303)
    return Response(content=f'{{"detail": "{exc.detail}"}}', status_code=exc.status_code, media_type="application/json")


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "ruleset": RULESET_VERSION}


# --- auth -----------------------------------------------------------------------------------

@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None, "invite": bool(config.INVITE_CODE)})


@app.post("/register")
def register(request: Request, org_name: str = Form(...), email: str = Form(...), password: str = Form(...),
             invite_code: str = Form(""), db: Session = Depends(get_db)):
    email = email.strip().lower()
    throttle(f"reg:{request.client.host if request.client else '?'}")
    if config.INVITE_CODE and not hmac.compare_digest(invite_code.encode(), config.INVITE_CODE.encode()):
        return templates.TemplateResponse(request, "login.html", {"error": "Ongeldige uitnodigingscode.", "invite": True}, status_code=403)
    if len(password) < 10 or db.scalar(select(User).where(User.email == email)):
        return templates.TemplateResponse(request, "login.html", {"error": "Wachtwoord < 10 tekens of e-mail bestaat al.", "invite": bool(config.INVITE_CODE)}, status_code=400)
    org = Org(name=org_name.strip(), case_quota=PLAN_QUOTAS["trial"])
    db.add(org)
    db.flush()
    user = User(org_id=org.id, email=email, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    request.session["uid"] = user.id
    return RedirectResponse("/", status_code=303)


@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    throttle(f"login:{request.client.host if request.client else '?'}:{email.strip().lower()}")
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(request, "login.html", {"error": "Ongeldige gegevens.", "invite": bool(config.INVITE_CODE)}, status_code=400)
    request.session["uid"] = user.id
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# --- cases ----------------------------------------------------------------------------------

@app.get("/")
def dashboard(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    cases = db.scalars(select(Case).where(Case.org_id == user.org_id).order_by(Case.id.desc())).all()
    org = db.get(Org, user.org_id)
    return templates.TemplateResponse(request, "dashboard.html", {"cases": cases, "org": org, "user": user, "used": _month_usage(db, org.id)})


def _month_usage(db: Session, org_id: int) -> int:
    start = dt.datetime.now(dt.timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return db.scalar(select(func.count(Case.id)).where(Case.org_id == org_id, Case.created_at >= start)) or 0


@app.post("/cases")
def create_case(title: str = Form(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    org = db.get(Org, user.org_id)
    if _month_usage(db, org.id) >= org.case_quota:
        raise HTTPException(402, "Monthly case quota reached – upgrade your plan")
    case = Case(org_id=org.id, created_by=user.id, title=title.strip()[:300])
    db.add(case)
    db.flush()
    audit(db, user, "case.create", case.id)
    db.commit()
    return RedirectResponse(f"/cases/{case.id}", status_code=303)


@app.get("/cases/{case_id}")
def case_page(request: Request, case_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = get_case(db, user, case_id)
    return templates.TemplateResponse(request, "case.html", {"case": case, "user": user, "version": RULESET_VERSION})


@app.post("/cases/{case_id}/documents")
async def upload(case_id: int, files: list[UploadFile] = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = get_case(db, user, case_id)
    for up in files:
        ext = Path(up.filename or "").suffix.lower()
        if ext not in ALLOWED_EXT:
            raise HTTPException(400, f"Unsupported file type {ext}: PDF, TXT or image (PNG/JPG/TIFF) only")
        data = await up.read()
        if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(413, "File too large")
        path = storage.save(case.org_id, case.id, up.filename, data)
        safe = path.name.split("_", 1)[1]
        doc = Document(case_id=case.id, filename=safe, stored_path=str(path))
        try:
            process_document(doc)
        except Exception as e:
            path.unlink(missing_ok=True)
            raise HTTPException(400, f"Could not read {safe}: {e}")
        case.documents.append(doc)
        audit(db, user, "document.upload", case.id, safe)
    db.commit()
    return RedirectResponse(f"/cases/{case.id}", status_code=303)


@app.post("/cases/{case_id}/analyze")
def analyze(case_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = get_case(db, user, case_id)
    if not case.documents:
        raise HTTPException(400, "Upload documents first")
    analyze_case(db, case)
    audit(db, user, "case.analyze", case.id, RULESET_VERSION)
    db.commit()
    return RedirectResponse(f"/cases/{case.id}", status_code=303)


@app.post("/cases/{case_id}/documents/{doc_id}/type")
def retype(case_id: int, doc_id: int, doc_type: str = Form(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    from . import extract
    from .classify import DOC_TYPES
    case = get_case(db, user, case_id)
    doc = next((d for d in case.documents if d.id == doc_id), None)
    if not doc or doc_type not in DOC_TYPES:
        raise HTTPException(404, "Document or type not found")
    doc.doc_type, doc.classification_confidence = doc_type, 1.0
    doc.fields = extract.extract(doc_type, doc.pages)
    audit(db, user, "document.retype", case.id, f"{doc.filename}->{doc_type}")
    db.commit()
    return RedirectResponse(f"/cases/{case.id}", status_code=303)


@app.post("/cases/{case_id}/findings/{finding_id}/review")
def review(case_id: int, finding_id: int, status: str = Form(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = get_case(db, user, case_id)
    f = next((x for x in case.findings if x.id == finding_id), None)
    if not f or status not in {"confirmed", "dismissed", "pending"}:
        raise HTTPException(404, "Finding not found")
    f.review_status, f.reviewed_by = status, user.id
    audit(db, user, "finding.review", case.id, f"{f.rule_id}:{status}")
    db.commit()
    return RedirectResponse(f"/cases/{case.id}#f{f.id}", status_code=303)


@app.post("/cases/{case_id}/findings/{finding_id}/comments")
def comment(case_id: int, finding_id: int, body: str = Form(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = get_case(db, user, case_id)
    f = next((x for x in case.findings if x.id == finding_id), None)
    if not f or not body.strip():
        raise HTTPException(404, "Finding not found")
    f.comments.append(Comment(finding_id=f.id, user_id=user.id, body=body.strip()[:2000]))
    audit(db, user, "finding.comment", case.id, f.rule_id)
    db.commit()
    return RedirectResponse(f"/cases/{case.id}#f{f.id}", status_code=303)


@app.post("/cases/{case_id}/delete")
def delete_case(case_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Erase a case and its stored files (GDPR). The audit trail keeps the fact of deletion, not the content."""
    case = get_case(db, user, case_id)
    folder = config.UPLOAD_DIR / str(case.org_id) / str(case.id)
    audit(db, user, "case.delete", case.id, case.title)
    db.delete(case)
    db.commit()
    shutil.rmtree(folder, ignore_errors=True)
    return RedirectResponse("/", status_code=303)


@app.get("/cases/{case_id}/report.pdf")
def report(case_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = get_case(db, user, case_id)
    if case.status != "analyzed":
        raise HTTPException(400, "Analyze the case first")
    audit(db, user, "report.export", case.id)
    db.commit()
    return Response(build_pdf(case), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="due-diligence-{case.id}.pdf"'})


@app.get("/api/cases/{case_id}")
def api_case(case_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = get_case(db, user, case_id)
    return {
        "id": case.id, "title": case.title, "address": case.address, "status": case.status, "scores": case.scores,
        "ruleset": RULESET_VERSION,
        "documents": [{"id": d.id, "filename": d.filename, "type": d.doc_type, "confidence": d.classification_confidence, "fields": d.fields} for d in case.documents],
        "findings": [{"id": f.id, "rule": f.rule_id, "domain": f.domain, "severity": f.severity, "kind": f.kind, "title": f.title,
                      "detail": f.detail, "recommendation": f.recommendation, "sources": f.sources, "review_status": f.review_status} for f in case.findings],
    }
