from __future__ import annotations

import hmac
import os
import re
import time
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import urlparse

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from . import billing, config, mail
from .api_v1 import router as api_v1_router
from .auth import (ApiKey, current_user, get_db, hash_password, make_token, new_api_key, open_session, pw_fingerprint,
                   read_token, verify_password)
from .classify import DOC_TYPES
from .models import AuditLog, Case, Comment, Org, User, init_db
from .report import build_pdf
from .rules import RULESET_VERSION
from .services import add_document, audit, case_payload, delete_case_data, get_case, require_verified, run_analysis

app = FastAPI(title="Belgian Property Due Diligence")
app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY, same_site="lax", https_only=config.COOKIE_SECURE, max_age=60 * 60 * 12)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app.include_router(billing.router)
app.include_router(api_v1_router)
init_db()

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}
VERIFY_MAX_AGE = 2 * 86400
RESET_MAX_AGE = 3600
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


# --- cross-cutting: CSRF, security headers, rate limiting, errors -----------------------------------

@app.middleware("http")
async def csrf_and_headers(request: Request, call_next):
    """Reject cross-site state-changing requests (Origin/Referer host must match Host) and add security headers.

    Server-to-server calls (Stripe webhook, API clients with X-API-Key) send no Origin and pass through.
    """
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        src = request.headers.get("origin") or request.headers.get("referer")
        if src and urlparse(src).netloc != request.headers.get("host"):
            return JSONResponse({"detail": "Cross-site request rejected"}, status_code=403)
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    if config.COOKIE_SECURE:
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return resp


_attempts: dict[str, deque] = defaultdict(deque)
LOGIN_WINDOW_S, LOGIN_MAX = 15 * 60, int(os.environ.get("LOGIN_MAX_ATTEMPTS", "8"))


def throttle(key: str, limit: int | None = None, window: int = LOGIN_WINDOW_S) -> None:
    """In-memory rate limit (per process; adequate for a single instance, use Redis for several)."""
    now, q = time.monotonic(), _attempts[key]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= (limit or LOGIN_MAX):
        raise HTTPException(429, "Trop de tentatives, réessayez plus tard")
    q.append(now)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


@app.exception_handler(HTTPException)
async def http_exc(request: Request, exc: HTTPException):
    if "text/html" in request.headers.get("accept", ""):
        if exc.status_code == 401:
            return RedirectResponse("/login", status_code=303)
        titles = {402: "Crédits insuffisants", 403: "Action non autorisée", 404: "Introuvable", 413: "Fichier trop volumineux", 429: "Trop de tentatives"}
        return templates.TemplateResponse(request, "error.html", {"status": exc.status_code, "detail": exc.detail,
                                          "title": titles.get(exc.status_code, "Une erreur est survenue")}, status_code=exc.status_code)
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "ruleset": RULESET_VERSION}


# --- e-mails ----------------------------------------------------------------------------------------

def send_verification(bg: BackgroundTasks, user: User) -> None:
    token = make_token("verify", user.id, user.email)
    bg.add_task(mail.send, user.email, "Confirmez votre adresse e-mail",
                f"Bonjour,\n\nConfirmez votre adresse en ouvrant ce lien (valable 48 h) :\n{config.BASE_URL}/verify?token={token}\n\n"
                "Si vous n'êtes pas à l'origine de cette inscription, ignorez ce message.")


def login_context(error: str | None = None, info: str | None = None) -> dict:
    return {"error": error, "info": info, "invite": bool(config.INVITE_CODE)}


# --- auth -------------------------------------------------------------------------------------------

@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", login_context(info=request.query_params.get("msg")))


@app.post("/register")
def register(request: Request, bg: BackgroundTasks, org_name: str = Form(...), email: str = Form(...), password: str = Form(...),
             invite_code: str = Form(""), db: Session = Depends(get_db)):
    email = email.strip().lower()
    throttle(f"reg:{client_ip(request)}")
    if config.INVITE_CODE and not hmac.compare_digest(invite_code.encode(), config.INVITE_CODE.encode()):
        return templates.TemplateResponse(request, "login.html", login_context("Code d'invitation invalide."), status_code=403)
    if not EMAIL_RE.fullmatch(email) or len(email) > 254:
        return templates.TemplateResponse(request, "login.html", login_context("Adresse e-mail invalide."), status_code=400)
    if len(password) < 10:
        return templates.TemplateResponse(request, "login.html", login_context("Mot de passe : 10 caractères minimum."), status_code=400)
    if db.scalar(select(User).where(User.email == email)):
        return templates.TemplateResponse(request, "login.html", login_context("Un compte existe déjà avec cet e-mail."), status_code=409)
    org = Org(name=org_name.strip()[:200], credits=config.FREE_CREDITS)
    db.add(org)
    db.flush()
    user = User(org_id=org.id, email=email, password_hash=hash_password(password))
    db.add(user)
    db.flush()
    audit(db, user, "account.register")
    db.commit()
    send_verification(bg, user)
    open_session(request, user)
    return RedirectResponse("/", status_code=303)


@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    email = email.strip().lower()
    throttle(f"login:{client_ip(request)}:{email}")
    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(request, "login.html", login_context("Identifiants incorrects."), status_code=400)
    open_session(request, user)
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/verify")
def verify_email(request: Request, token: str, db: Session = Depends(get_db)):
    parsed = read_token("verify", token, VERIFY_MAX_AGE)
    user = db.get(User, parsed[0]) if parsed else None
    if not user or user.email != parsed[1]:
        return templates.TemplateResponse(request, "login.html", login_context("Lien invalide ou expiré."), status_code=400)
    user.email_verified = True
    db.commit()
    return RedirectResponse("/login?msg=Adresse+confirm%C3%A9e,+vous+pouvez+vous+connecter", status_code=303)


@app.post("/verify/resend")
def resend_verification(request: Request, bg: BackgroundTasks, user: User = Depends(current_user)):
    if not user.email_verified:
        throttle(f"resend:{user.id}", 3, 3600)
        send_verification(bg, user)
    return RedirectResponse("/?msg=E-mail+de+confirmation+envoy%C3%A9", status_code=303)


@app.get("/forgot")
def forgot_page(request: Request):
    return templates.TemplateResponse(request, "forgot.html", {"sent": False})


@app.post("/forgot")
def forgot(request: Request, bg: BackgroundTasks, email: str = Form(...), db: Session = Depends(get_db)):
    throttle(f"forgot:{client_ip(request)}", 5, 3600)
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user:  # identical answer whether or not the account exists (no enumeration)
        token = make_token("reset", user.id, pw_fingerprint(user))
        bg.add_task(mail.send, user.email, "Réinitialisation de votre mot de passe",
                    f"Bonjour,\n\nPour choisir un nouveau mot de passe (lien valable 1 h, usage unique) :\n{config.BASE_URL}/reset?token={token}\n\n"
                    "Si vous n'avez rien demandé, ignorez ce message : votre mot de passe reste inchangé.")
    return templates.TemplateResponse(request, "forgot.html", {"sent": True})


@app.get("/reset")
def reset_page(request: Request, token: str):
    return templates.TemplateResponse(request, "reset.html", {"token": token, "error": None})


@app.post("/reset")
def reset(request: Request, token: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    parsed = read_token("reset", token, RESET_MAX_AGE)
    user = db.get(User, parsed[0]) if parsed else None
    if not user or parsed[1] != pw_fingerprint(user):  # fingerprint changes after use: single-use link
        return templates.TemplateResponse(request, "reset.html", {"token": token, "error": "Lien invalide ou expiré."}, status_code=400)
    if len(password) < 10:
        return templates.TemplateResponse(request, "reset.html", {"token": token, "error": "Mot de passe : 10 caractères minimum."}, status_code=400)
    user.password_hash = hash_password(password)
    user.email_verified = True  # access to the mailbox is proven
    audit(db, user, "account.password_reset")
    db.commit()
    request.session.clear()
    return RedirectResponse("/login?msg=Mot+de+passe+modifi%C3%A9", status_code=303)


# --- account: credits, API keys, erasure --------------------------------------------------------------

@app.get("/account")
def account(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    keys = db.scalars(select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.revoked == False).order_by(ApiKey.id)).all()  # noqa: E712
    return templates.TemplateResponse(request, "account.html", {
        "user": user, "org": db.get(Org, user.org_id), "keys": keys, "new_key": None, "pack": config.PACK_CREDITS,
        "stripe_ready": billing.configured(), "paid": request.query_params.get("paid"), "base_url": config.BASE_URL,
        "verification_on": config.REQUIRE_EMAIL_VERIFICATION})


@app.post("/account/keys")
def create_key(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_verified(user)
    throttle(f"keys:{user.id}", 10, 3600)
    key, prefix, key_hash = new_api_key()
    db.add(ApiKey(user_id=user.id, prefix=prefix, key_hash=key_hash))
    audit(db, user, "apikey.create", detail=prefix)
    db.commit()
    keys = db.scalars(select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.revoked == False).order_by(ApiKey.id)).all()  # noqa: E712
    return templates.TemplateResponse(request, "account.html", {
        "user": user, "org": db.get(Org, user.org_id), "keys": keys, "new_key": key, "pack": config.PACK_CREDITS,
        "stripe_ready": billing.configured(), "paid": None, "base_url": config.BASE_URL,
        "verification_on": config.REQUIRE_EMAIL_VERIFICATION})


@app.post("/account/keys/{key_id}/revoke")
def revoke_key(key_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    k = db.get(ApiKey, key_id)
    if not k or k.user_id != user.id:
        raise HTTPException(404, "Clé introuvable")
    k.revoked = True
    audit(db, user, "apikey.revoke", detail=k.prefix)
    db.commit()
    return RedirectResponse("/account", status_code=303)


@app.post("/account/delete")
def delete_account(request: Request, password: str = Form(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """GDPR erasure: removes the organisation, its cases/files/keys and users. Payments are kept for accounting."""
    if not verify_password(password, user.password_hash):
        raise HTTPException(403, "Mot de passe incorrect")
    if db.scalar(select(User.id).where(User.org_id == user.org_id, User.id != user.id)):
        raise HTTPException(409, "L'organisation compte d'autres utilisateurs : contactez le support")
    org_id, uid = user.org_id, user.id
    for case in db.scalars(select(Case).where(Case.org_id == org_id)).all():
        delete_case_data(db, case)
    db.execute(delete(ApiKey).where(ApiKey.user_id == uid))
    db.execute(delete(AuditLog).where(AuditLog.org_id == org_id))
    db.execute(delete(User).where(User.id == uid))
    db.execute(delete(Org).where(Org.id == org_id))
    db.commit()
    request.session.clear()
    return RedirectResponse("/login?msg=Compte+et+donn%C3%A9es+supprim%C3%A9s", status_code=303)


# --- cases ------------------------------------------------------------------------------------------

@app.get("/")
def dashboard(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    cases = db.scalars(select(Case).where(Case.org_id == user.org_id).order_by(Case.id.desc())).all()
    return templates.TemplateResponse(request, "dashboard.html", {
        "cases": cases, "org": db.get(Org, user.org_id), "user": user, "msg": request.query_params.get("msg"),
        "needs_verification": config.REQUIRE_EMAIL_VERIFICATION and not user.email_verified})


@app.post("/cases")
def create_case(title: str = Form(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = Case(org_id=user.org_id, created_by=user.id, title=title.strip()[:300] or "Dossier")
    db.add(case)
    db.flush()
    audit(db, user, "case.create", case.id)
    db.commit()
    return RedirectResponse(f"/cases/{case.id}", status_code=303)


@app.get("/cases/{case_id}")
def case_page(request: Request, case_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = get_case(db, user, case_id)
    return templates.TemplateResponse(request, "case.html", {
        "case": case, "user": user, "org": db.get(Org, user.org_id), "version": RULESET_VERSION, "doc_types": DOC_TYPES,
        "findings": sorted(case.findings, key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.id)),
        "to_charge": sum(1 for d in case.documents if not d.billed), "needs_verification": config.REQUIRE_EMAIL_VERIFICATION and not user.email_verified})


@app.post("/cases/{case_id}/documents")
def upload(case_id: int, files: list[UploadFile] = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = get_case(db, user, case_id)
    if len(files) > config.MAX_FILES_PER_REQUEST:
        raise HTTPException(400, f"Maximum {config.MAX_FILES_PER_REQUEST} fichiers par envoi")
    try:
        for up in files:
            doc = add_document(db, case, up.filename or "document", up.file.read(config.MAX_UPLOAD_MB * 1024 * 1024 + 1))
            audit(db, user, "document.upload", case.id, doc.filename)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return RedirectResponse(f"/cases/{case.id}", status_code=303)


@app.post("/cases/{case_id}/analyze")
def analyze(case_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = get_case(db, user, case_id)
    try:
        run_analysis(db, user, case)  # debits credits in the same transaction
        db.commit()
    except Exception:
        db.rollback()
        raise
    return RedirectResponse(f"/cases/{case.id}", status_code=303)


@app.post("/cases/{case_id}/documents/{doc_id}/type")
def retype(case_id: int, doc_id: int, doc_type: str = Form(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    from . import extract
    case = get_case(db, user, case_id)
    doc = next((d for d in case.documents if d.id == doc_id), None)
    if not doc or doc_type not in DOC_TYPES:
        raise HTTPException(404, "Document ou type introuvable")
    doc.doc_type, doc.classification_confidence = doc_type, 1.0
    doc.fields = extract.extract(doc_type, doc.pages)
    doc.ai_analysis = None  # the AI reading depends on the type
    audit(db, user, "document.retype", case.id, f"{doc.filename}->{doc_type}")
    db.commit()
    return RedirectResponse(f"/cases/{case.id}", status_code=303)


@app.post("/cases/{case_id}/findings/{finding_id}/review")
def review(case_id: int, finding_id: int, status: str = Form(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = get_case(db, user, case_id)
    f = next((x for x in case.findings if x.id == finding_id), None)
    if not f or status not in {"confirmed", "dismissed", "pending"}:
        raise HTTPException(404, "Finding introuvable")
    f.review_status, f.reviewed_by = status, user.id
    audit(db, user, "finding.review", case.id, f"{f.rule_id}:{status}")
    db.commit()
    return RedirectResponse(f"/cases/{case.id}#f{f.id}", status_code=303)


@app.post("/cases/{case_id}/findings/{finding_id}/comments")
def comment(case_id: int, finding_id: int, body: str = Form(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = get_case(db, user, case_id)
    f = next((x for x in case.findings if x.id == finding_id), None)
    if not f or not body.strip():
        raise HTTPException(404, "Finding introuvable")
    f.comments.append(Comment(finding_id=f.id, user_id=user.id, body=body.strip()[:2000]))
    audit(db, user, "finding.comment", case.id, f.rule_id)
    db.commit()
    return RedirectResponse(f"/cases/{case.id}#f{f.id}", status_code=303)


@app.post("/cases/{case_id}/delete")
def delete_case(case_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Erase a case and its stored files (GDPR). The audit trail keeps the fact of deletion, not the content."""
    case = get_case(db, user, case_id)
    audit(db, user, "case.delete", case.id)
    delete_case_data(db, case)
    db.commit()
    return RedirectResponse("/", status_code=303)


@app.get("/cases/{case_id}/report.pdf")
def report(case_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = get_case(db, user, case_id)
    if case.status != "analyzed":
        raise HTTPException(400, "Analysez d'abord le dossier")
    audit(db, user, "report.export", case.id)
    db.commit()
    return Response(build_pdf(case), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="due-diligence-{case.id}.pdf"'})


@app.get("/api/cases/{case_id}")
def api_case(case_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return case_payload(get_case(db, user, case_id))
