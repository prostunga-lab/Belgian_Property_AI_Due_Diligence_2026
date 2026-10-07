from __future__ import annotations

import datetime as dt
import hmac
import logging
import os
import re
import time
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import urlparse

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from . import billing, config, i18n, invite, mail, pricing
from .api_v1 import router as api_v1_router
from .auth import (ApiKey, current_user, get_db, hash_password, make_token, new_api_key, open_session, optional_user,
                   pw_fingerprint, read_token, verify_password)
from .classify import DOC_TYPES
from .errors import AppError
from .models import AuditLog, Case, Comment, Org, User, init_db
from .report import build_pdf
from .rules import RULESET_VERSION
from .services import (add_document, audit, balance, billing_preview, case_payload, delete_case_data, finding_view, get_case,
                       require_verified, run_analysis)


def resolve_lang(request: Request) -> str:
    """?lang= (one request) > cookie (chosen with the switcher) > Accept-Language > default (API paths default to English)."""
    for candidate in (request.query_params.get("lang"), request.cookies.get(i18n.COOKIE)):
        if lang := i18n.normalize(candidate):
            return lang
    if lang := i18n.from_accept_language(request.headers.get("accept-language")):
        return lang
    return "en" if request.url.path.startswith(("/v1", "/api", "/billing")) else i18n.DEFAULT_LANG


def switch_target(request: Request) -> str:
    """Where the language switcher returns to: the current page when it can be fetched with GET (keeping e.g. ?token=),
    otherwise a safe page (a refused POST such as /register is rendered on a POST-only URL)."""
    if request.method == "GET":
        query = "&".join(f"{k}={v}" for k, v in request.query_params.multi_items() if k not in ("lang", "msg"))
        return request.url.path + (f"?{query}" if query else "")
    return "/login" if request.url.path in ("/register", "/login", "/forgot", "/reset") else "/"


def template_context(request: Request) -> dict:
    lang = getattr(request.state, "lang", None) or resolve_lang(request)
    return {"_": i18n.translator(lang), "lang": lang, "languages": i18n.LANGS, "lang_names": i18n.LANG_NAMES,
            "switch_next": switch_target(request), "year": dt.date.today().year, "company_name": config.COMPANY_NAME}


app = FastAPI(title="Belgian Property Due Diligence")
app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY, same_site="lax", https_only=config.COOKIE_SECURE, max_age=60 * 60 * 12)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"), context_processors=[template_context])
app.include_router(billing.router)
app.include_router(api_v1_router)
init_db()

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}
VERIFY_MAX_AGE = 2 * 86400
RESET_MAX_AGE = 3600
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
# Messages passed in redirect URLs are KEYS from these allow-lists, never free text (no reflected-text injection).
LOGIN_MESSAGES = {"verified": "auth.info.verified", "password_changed": "auth.info.password_changed", "account_deleted": "auth.info.account_deleted"}
DASHBOARD_MESSAGES = {"verification_sent": "msg.verification_sent"}


# --- cross-cutting: language, CSRF, security headers, rate limiting, errors -----------------------------

@app.middleware("http")
async def lang_csrf_headers(request: Request, call_next):
    """Resolve the language, reject cross-site state-changing requests, add security headers.

    Cross-site check: Origin (or Referer) host must match Host. Server-to-server calls (Stripe webhook, API clients
    with X-API-Key) send no Origin and pass through.
    """
    request.state.lang = resolve_lang(request)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        src = request.headers.get("origin") or request.headers.get("referer")
        if src and urlparse(src).netloc != request.headers.get("host"):
            return JSONResponse({"detail": i18n.t("err.cross_site", request.state.lang), "code": "err.cross_site"}, status_code=403)
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("Content-Language", request.state.lang)
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
        raise AppError(429, "err.throttle")
    q.append(now)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


@app.exception_handler(StarletteHTTPException)
async def http_exc(request: Request, exc: StarletteHTTPException):
    lang = getattr(request.state, "lang", None) or resolve_lang(request)
    if isinstance(exc, AppError):
        code, detail = exc.key, i18n.t(exc.key, lang, **exc.params)
    else:  # framework errors (unknown route, method not allowed…)
        code, detail = None, i18n.t(f"err.title.{exc.status_code}", lang) if i18n.has(f"err.title.{exc.status_code}") else str(exc.detail)
    if "text/html" in request.headers.get("accept", ""):
        if exc.status_code == 401:
            return RedirectResponse("/login", status_code=303)
        title = i18n.t(f"err.title.{exc.status_code}", lang) if i18n.has(f"err.title.{exc.status_code}") else i18n.t("err.title.default", lang)
        return templates.TemplateResponse(request, "error.html", {"status": exc.status_code, "detail": detail, "title": title}, status_code=exc.status_code)
    body = {"detail": detail} | ({"code": code} if code else {})
    return JSONResponse(body, status_code=exc.status_code)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "ruleset": RULESET_VERSION}


@app.get("/about")
def about(request: Request):
    return templates.TemplateResponse(request, "about.html", {"base_url": config.BASE_URL})


@app.get("/contact")
def contact(request: Request):
    """Public contact page. Only configured details are shown; nothing is invented, and there is no form that could silently lose a message."""
    return templates.TemplateResponse(request, "contact.html", {
        "base_url": config.BASE_URL, "contact_email": config.CONTACT_EMAIL, "invite": bool(config.INVITE_CODE),
        "company_address": config.COMPANY_ADDRESS, "enterprise_number": config.COMPANY_ENTERPRISE_NUMBER, "company_phone": config.COMPANY_PHONE})


@app.get("/lang/{code}")
def set_language(code: str, request: Request, next: str = "/", user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    """Language switcher: remembers the choice in a cookie (and on the account when logged in), then goes back."""
    lang = i18n.normalize(code)
    if not lang:
        raise AppError(404, "err.not_found.case")
    target = next if next.startswith("/") and not next.startswith("//") and "\\" not in next else "/"  # same-site paths only
    resp = RedirectResponse(target, status_code=303)
    resp.set_cookie(i18n.COOKIE, lang, max_age=365 * 86400, samesite="lax", secure=config.COOKIE_SECURE, httponly=True)
    if user and user.lang != lang:
        user.lang = lang
        db.commit()
    return resp


# --- e-mails ----------------------------------------------------------------------------------------

def send_verification(bg: BackgroundTasks, user: User, lang: str) -> None:
    link = f"{config.BASE_URL}/verify?token={make_token('verify', user.id, user.email)}"
    bg.add_task(mail.send, user.email, i18n.t("mail.verify.subject", lang), i18n.t("mail.verify.body", lang, link=link))


def login_context(request: Request, error: str | None = None, info: str | None = None) -> dict:
    lang = request.state.lang
    return {"error": i18n.t(error, lang) if error else None, "info": i18n.t(info, lang) if info else None, "invite": bool(config.INVITE_CODE)}


# --- auth -------------------------------------------------------------------------------------------

@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", login_context(request, info=LOGIN_MESSAGES.get(request.query_params.get("msg", ""))))


@app.post("/register")
def register(request: Request, bg: BackgroundTasks, org_name: str = Form(...), email: str = Form(...), password: str = Form(...),
             invite_code: str = Form(""), db: Session = Depends(get_db)):
    email = email.strip().lower()
    throttle(f"reg:{client_ip(request)}")

    def refuse(key: str, status: int):
        return templates.TemplateResponse(request, "login.html", login_context(request, error=key), status_code=status)

    if config.INVITE_CODE and not invite.matches(invite_code, config.INVITE_CODE):
        # Diagnostic for the operator (Railway logs). Lengths only (after normalisation): the code itself is never logged.
        logging.getLogger("uvicorn.error").warning(
            "Registration refused: invite code mismatch (submitted %d chars, configured %d chars, after ignoring case, spaces and hyphens). "
            "A difference usually means the dashboard value changed without a redeploy, or a different value was typed.",
            len(invite.normalize(invite_code)), len(invite.normalize(config.INVITE_CODE)))
        return refuse("auth.err.invite", 403)
    if not EMAIL_RE.fullmatch(email) or len(email) > 254:
        return refuse("auth.err.email", 400)
    if len(password) < 10:
        return refuse("auth.err.password_short", 400)
    if db.scalar(select(User).where(User.email == email)):
        return refuse("auth.err.exists", 409)
    org = Org(name=org_name.strip()[:200], credits=config.FREE_CREDITS)
    db.add(org)
    db.flush()
    user = User(org_id=org.id, email=email, password_hash=hash_password(password), lang=request.state.lang)
    db.add(user)
    db.flush()
    audit(db, user, "account.register")
    db.commit()
    send_verification(bg, user, request.state.lang)
    open_session(request, user)
    return RedirectResponse("/", status_code=303)


@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    email = email.strip().lower()
    throttle(f"login:{client_ip(request)}:{email}")
    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(request, "login.html", login_context(request, error="auth.err.credentials"), status_code=400)
    open_session(request, user)
    resp = RedirectResponse("/", status_code=303)
    if user.lang:  # the account's preferred language follows the person across devices
        resp.set_cookie(i18n.COOKIE, user.lang, max_age=365 * 86400, samesite="lax", secure=config.COOKIE_SECURE, httponly=True)
    return resp


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/verify")
def verify_email(request: Request, token: str, db: Session = Depends(get_db)):
    parsed = read_token("verify", token, VERIFY_MAX_AGE)
    user = db.get(User, parsed[0]) if parsed else None
    if not user or user.email != parsed[1]:
        return templates.TemplateResponse(request, "login.html", login_context(request, error="auth.err.link_invalid"), status_code=400)
    user.email_verified = True
    db.commit()
    return RedirectResponse("/login?msg=verified", status_code=303)


@app.post("/verify/resend")
def resend_verification(request: Request, bg: BackgroundTasks, user: User = Depends(current_user)):
    if not user.email_verified:
        throttle(f"resend:{user.id}", 3, 3600)
        send_verification(bg, user, request.state.lang)
    return RedirectResponse("/?msg=verification_sent", status_code=303)


@app.get("/forgot")
def forgot_page(request: Request):
    return templates.TemplateResponse(request, "forgot.html", {"sent": False})


@app.post("/forgot")
def forgot(request: Request, bg: BackgroundTasks, email: str = Form(...), db: Session = Depends(get_db)):
    throttle(f"forgot:{client_ip(request)}", 5, 3600)
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user:  # identical answer whether or not the account exists (no enumeration)
        link = f"{config.BASE_URL}/reset?token={make_token('reset', user.id, pw_fingerprint(user))}"
        lang = request.state.lang
        bg.add_task(mail.send, user.email, i18n.t("mail.reset.subject", lang), i18n.t("mail.reset.body", lang, link=link))
    return templates.TemplateResponse(request, "forgot.html", {"sent": True})


@app.get("/reset")
def reset_page(request: Request, token: str):
    return templates.TemplateResponse(request, "reset.html", {"token": token, "error": None})


@app.post("/reset")
def reset(request: Request, token: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    lang = request.state.lang
    parsed = read_token("reset", token, RESET_MAX_AGE)
    user = db.get(User, parsed[0]) if parsed else None
    if not user or parsed[1] != pw_fingerprint(user):  # fingerprint changes after use: single-use link
        return templates.TemplateResponse(request, "reset.html", {"token": token, "error": i18n.t("auth.err.link_invalid", lang)}, status_code=400)
    if len(password) < 10:
        return templates.TemplateResponse(request, "reset.html", {"token": token, "error": i18n.t("auth.err.password_short", lang)}, status_code=400)
    user.password_hash = hash_password(password)
    user.email_verified = True  # access to the mailbox is proven
    audit(db, user, "account.password_reset")
    db.commit()
    request.session.clear()
    return RedirectResponse("/login?msg=password_changed", status_code=303)


# --- account: credits, API keys, erasure --------------------------------------------------------------

def account_context(request: Request, user: User, db: Session, new_key: str | None = None, paid: str | None = None) -> dict:
    org = db.get(Org, user.org_id)
    keys = db.scalars(select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.revoked == False).order_by(ApiKey.id)).all()  # noqa: E712
    bal = balance(org)
    return {"user": user, "org": org, "bal": bal, "keys": keys, "new_key": new_key, "paid": paid, "base_url": config.BASE_URL,
            "stripe_ready": billing.configured(), "verification_on": config.REQUIRE_EMAIL_VERIFICATION,
            "cards": pricing.cards(request.state.lang), "max_documents": config.DOSSIER_MAX_DOCUMENTS, "vat": config.PRICES_VAT,
            "sub_name": billing.plan_name(bal["plan"], request.state.lang) if bal["plan"] else None,
            "has_customer": bool(org.stripe_customer_id)}


@app.get("/account")
def account(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "account.html", account_context(request, user, db, paid=request.query_params.get("paid")))


@app.post("/account/keys")
def create_key(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_verified(user)
    throttle(f"keys:{user.id}", 10, 3600)
    key, prefix, key_hash = new_api_key()
    db.add(ApiKey(user_id=user.id, prefix=prefix, key_hash=key_hash))
    audit(db, user, "apikey.create", detail=prefix)
    db.commit()
    return templates.TemplateResponse(request, "account.html", account_context(request, user, db, new_key=key))


@app.get("/pricing")
def pricing_page(request: Request, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    """Public pricing: pay per complete dossier (investors) or monthly subscription with a quota (agents)."""
    ctx = {"cards": pricing.cards(request.state.lang), "stripe_ready": billing.configured(), "free_credits": config.FREE_CREDITS,
           "max_documents": config.DOSSIER_MAX_DOCUMENTS, "vat": config.PRICES_VAT, "base_url": config.BASE_URL, "signed_in": user is not None,
           "promise_minutes": config.PROCESSING_PROMISE_MINUTES}
    if user:
        org = db.get(Org, user.org_id)
        ctx |= {"user": user, "org": org, "bal": balance(org)}
    return templates.TemplateResponse(request, "pricing.html", ctx)


@app.post("/account/keys/{key_id}/revoke")
def revoke_key(key_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    k = db.get(ApiKey, key_id)
    if not k or k.user_id != user.id:
        raise AppError(404, "err.not_found.key")
    k.revoked = True
    audit(db, user, "apikey.revoke", detail=k.prefix)
    db.commit()
    return RedirectResponse("/account", status_code=303)


@app.post("/account/delete")
def delete_account(request: Request, password: str = Form(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """GDPR erasure: removes the organisation, its cases/files/keys and users. Payments are kept for accounting."""
    if not verify_password(password, user.password_hash):
        raise AppError(403, "err.wrong_password")
    if db.scalar(select(User.id).where(User.org_id == user.org_id, User.id != user.id)):
        raise AppError(409, "err.org_has_users")
    org_id, uid = user.org_id, user.id
    for case in db.scalars(select(Case).where(Case.org_id == org_id)).all():
        delete_case_data(db, case)
    db.execute(delete(ApiKey).where(ApiKey.user_id == uid))
    db.execute(delete(AuditLog).where(AuditLog.org_id == org_id))
    db.execute(delete(User).where(User.id == uid))
    db.execute(delete(Org).where(Org.id == org_id))
    db.commit()
    request.session.clear()
    return RedirectResponse("/login?msg=account_deleted", status_code=303)


# --- cases ------------------------------------------------------------------------------------------

@app.get("/")
def home(request: Request, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    """Public landing page for visitors; the case dashboard for signed-in users."""
    if user is None:
        return templates.TemplateResponse(request, "landing.html", {
            "invite": bool(config.INVITE_CODE), "free_credits": config.FREE_CREDITS, "max_files": config.MAX_FILES_PER_REQUEST,
            "max_mb": config.MAX_UPLOAD_MB, "base_url": config.BASE_URL})
    cases = db.scalars(select(Case).where(Case.org_id == user.org_id).order_by(Case.id.desc())).all()
    org = db.get(Org, user.org_id)
    return templates.TemplateResponse(request, "dashboard.html", {
        "cases": cases, "org": org, "bal": balance(org), "user": user,
        "msg": i18n.t(DASHBOARD_MESSAGES[m], request.state.lang) if (m := request.query_params.get("msg")) in DASHBOARD_MESSAGES else None,
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
        "findings": [finding_view(f, request.state.lang) | {"comments": f.comments}
                     for f in sorted(case.findings, key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.id))],
        "preview": billing_preview(db.get(Org, user.org_id), case), "bal": balance(db.get(Org, user.org_id)),
        "max_documents": config.DOSSIER_MAX_DOCUMENTS, "needs_verification": config.REQUIRE_EMAIL_VERIFICATION and not user.email_verified})


@app.post("/cases/{case_id}/documents")
def upload(case_id: int, files: list[UploadFile] = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = get_case(db, user, case_id)
    if len(files) > config.MAX_FILES_PER_REQUEST:
        raise AppError(400, "err.too_many_files", max=config.MAX_FILES_PER_REQUEST)
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
def analyze(case_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = get_case(db, user, case_id)
    try:
        run_analysis(db, user, case, request.state.lang)  # debits credits in the same transaction
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
        raise AppError(404, "err.not_found.doc_or_type")
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
        raise AppError(404, "err.not_found.finding")
    f.review_status, f.reviewed_by = status, user.id
    audit(db, user, "finding.review", case.id, f"{f.rule_id}:{status}")
    db.commit()
    return RedirectResponse(f"/cases/{case.id}#f{f.id}", status_code=303)


@app.post("/cases/{case_id}/findings/{finding_id}/comments")
def comment(case_id: int, finding_id: int, body: str = Form(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = get_case(db, user, case_id)
    f = next((x for x in case.findings if x.id == finding_id), None)
    if not f or not body.strip():
        raise AppError(404, "err.not_found.finding")
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
def report(case_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = get_case(db, user, case_id)
    if case.status != "analyzed":
        raise AppError(400, "err.not_analyzed")
    audit(db, user, "report.export", case.id)
    db.commit()
    return Response(build_pdf(case, request.state.lang), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="due-diligence-{case.id}.pdf"'})


@app.get("/api/cases/{case_id}")
def api_case(case_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return case_payload(get_case(db, user, case_id), request.state.lang)
