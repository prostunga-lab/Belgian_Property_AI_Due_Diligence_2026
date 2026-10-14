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
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from . import billing, captcha, config, i18n, invite, legal, mail, pricing
from . import demo, renovation
from . import summary as property_summary
from .api_v1 import router as api_v1_router
from .auth import (ApiKey, current_user, get_db, hash_password, make_token, new_api_key, open_session, optional_user,
                   pw_fingerprint, read_token, verify_password)
from .classify import DOC_TYPES
from .errors import AppError
from .models import AccessRequest, AuditLog, Case, Comment, Org, User, init_db
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


app = FastAPI(title="Belgian Immo Due Diligence")
app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY, same_site="lax", https_only=config.COOKIE_SECURE, max_age=60 * 60 * 12)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"), context_processors=[template_context])
app.include_router(billing.router)
app.include_router(api_v1_router)
init_db()
logging.getLogger("uvicorn.error").info(
    "startup: build=%s mail=%s registration=%s invite_code=%s", (os.environ.get("RAILWAY_GIT_COMMIT_SHA") or "unknown")[:7], mail.transport(),
    "open" if config.OPEN_REGISTRATION else "invitation-only" if config.INVITE_CODE else "open (no invite code, dev)",
    f"configured ({len(invite.normalize(config.INVITE_CODE))} chars after normalisation)" if config.INVITE_CODE else "not set (registration open)")

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}
VERIFY_MAX_AGE = 2 * 86400
RESET_MAX_AGE = 3600
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
# Messages passed in redirect URLs are KEYS from these allow-lists, never free text (no reflected-text injection).
LOGIN_MESSAGES = {"verified": "auth.info.verified", "password_changed": "auth.info.password_changed", "account_deleted": "auth.info.account_deleted"}
DASHBOARD_MESSAGES = {"verification_sent": "msg.verification_sent"}


# --- cross-cutting: language, CSRF, security headers, rate limiting, errors -----------------------------

# No inline scripts anywhere (behaviour lives in /static/app.js), so scripts are limited to this origin. Inline *styles* are still
# used by the templates, hence 'unsafe-inline' for style-src only. form-action lists the payment provider's hosts because the
# checkout/portal buttons are forms answered by a redirect to Stripe.
def csp() -> str:
    cf = f" {captcha.HOST}" if captcha.enabled() else ""  # the Turnstile widget: its script and its iframe
    return (f"default-src 'self'; script-src 'self'{cf}; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; "
            f"frame-src 'self'{cf}; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self' https://checkout.stripe.com https://billing.stripe.com")


def secure_headers(resp: Response, lang: str | None = None) -> Response:
    """The same protections on EVERY response: pages, redirects, 4xx/5xx errors, early refusals and static files."""
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    if lang:
        resp.headers.setdefault("Content-Language", lang)
    if config.COOKIE_SECURE:
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if config.CSP_MODE != "off":
        resp.headers.setdefault("Content-Security-Policy-Report-Only" if config.CSP_MODE == "report-only" else "Content-Security-Policy", csp())
    return resp


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
            refusal = JSONResponse({"detail": i18n.t("err.cross_site", request.state.lang), "code": "err.cross_site"}, status_code=403)
            return secure_headers(refusal, request.state.lang)
    return secure_headers(await call_next(request), request.state.lang)


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


API_PREFIXES = ("/v1", "/billing/webhook", "/docs", "/openapi.json", "/redoc", "/static")


def _wants_html(request: Request, exc: StarletteHTTPException) -> bool:
    """Browsers always get a readable page. Clients that send no Accept header (curl, checkers) get one too for an unknown page
    or method, but never on API paths, which keep their JSON errors."""
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return True
    path = request.url.path
    return (exc.status_code in (404, 405) and not isinstance(exc, AppError) and not path.startswith(API_PREFIXES)
            and "application/json" not in accept and "x-api-key" not in request.headers)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    """Last resort: a generic answer (never a stack trace), with the same security headers as every other response."""
    logging.getLogger("uvicorn.error").exception("Unhandled error on %s %s", request.method, request.url.path)
    lang = getattr(request.state, "lang", None) or "en"
    if "text/html" in request.headers.get("accept", ""):
        resp = templates.TemplateResponse(request, "error.html", {"status": 500, "detail": i18n.t("err.title.500", lang) if i18n.has("err.title.500") else "Error", "title": i18n.t("err.title.default", lang)}, status_code=500)
    else:
        resp = JSONResponse({"detail": "Internal error"}, status_code=500)
    return secure_headers(resp, lang)


@app.exception_handler(StarletteHTTPException)
async def http_exc(request: Request, exc: StarletteHTTPException):
    lang = getattr(request.state, "lang", None) or resolve_lang(request)
    if isinstance(exc, AppError):
        code, detail = exc.key, i18n.t(exc.key, lang, **exc.params)
    else:  # framework errors (unknown route, method not allowed…)
        code, detail = None, i18n.t(f"err.title.{exc.status_code}", lang) if i18n.has(f"err.title.{exc.status_code}") else str(exc.detail)
    if _wants_html(request, exc):
        if exc.status_code == 401:
            return RedirectResponse("/login", status_code=303)
        title = i18n.t(f"err.title.{exc.status_code}", lang) if i18n.has(f"err.title.{exc.status_code}") else i18n.t("err.title.default", lang)
        return templates.TemplateResponse(request, "error.html", {"status": exc.status_code, "detail": detail, "title": title}, status_code=exc.status_code)
    body = {"detail": detail} | ({"code": code} if code else {})
    return JSONResponse(body, status_code=exc.status_code)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "ruleset": RULESET_VERSION, "build": (os.environ.get("RAILWAY_GIT_COMMIT_SHA") or "unknown")[:7],
            "invite_required": bool(config.INVITE_CODE), "terms_version": legal.VERSION, "mail": mail.transport(),
            "access_notifications": bool(config.CONTACT_EMAIL) and mail.transport() != "log",
            "registration": "invitation-only" if config.INVITE_CODE else "open", "trial_days": config.TRIAL_DAYS}


@app.get("/about")
def about(request: Request):
    return templates.TemplateResponse(request, "about.html", {"base_url": config.BASE_URL})


def _demo_case():
    case = demo.build()
    return case, sorted(case.findings, key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.id))


@app.get("/demo")
def demo_report(request: Request):
    """Public demonstration: the real engine on synthetic documents, with sources, limits and the action plan."""
    lang = request.state.lang
    case, findings = _demo_case()
    return templates.TemplateResponse(request, "demo.html", {
        "case": case, "base_url": config.BASE_URL, "prop": property_summary.build(case.documents, lang),
        "reno": renovation.build(findings, case.documents, lang), "rules_validated": config.RULES_VALIDATED,
        "findings": [finding_view(f, lang) for f in findings if f.severity != "info"][:6], "invite": bool(config.INVITE_CODE)})


@app.get("/demo/report.pdf")
def demo_pdf(request: Request):
    case, _ = _demo_case()
    return Response(build_pdf(case, request.state.lang), media_type="application/pdf", headers={"Content-Disposition": 'inline; filename="demo-report.pdf"'})


def contact_context(request: Request, error: str | None = None, **form) -> dict:
    lang = request.state.lang
    return {"base_url": config.BASE_URL, "contact_email": config.CONTACT_EMAIL, "invite": bool(config.INVITE_CODE),
            "company_address": config.COMPANY_ADDRESS, "enterprise_number": config.COMPANY_ENTERPRISE_NUMBER, "company_phone": config.COMPANY_PHONE,
            "error": i18n.t(error, lang) if error else None, "form": form, "sent": request.query_params.get("sent") == "1"}


@app.get("/contact")
def contact(request: Request):
    """Public contact page: published details, plus a working access-request form so that no visitor reaches a dead end."""
    return templates.TemplateResponse(request, "contact.html", contact_context(request))


ACCOUNT_TYPES = ("individual", "professional")


@app.post("/request-access")
def request_access(request: Request, bg: BackgroundTasks, name: str = Form(""), email: str = Form(""), account_type: str = Form("professional"),
                   organisation: str = Form(""), message: str = Form(""), consent: str = Form(""), hp_check: str = Form(""),
                   db: Session = Depends(get_db)):
    """Store a request for access (invitation-only beta) and tell the owner. A hidden 'hp_check' field catches simple bots."""
    done = RedirectResponse("/contact?sent=1#access", status_code=303)
    if hp_check.strip():  # honeypot: looks like success, stores nothing
        return done
    throttle(f"access:{client_ip(request)}", 3, 3600)
    name, email, organisation, message = name.strip(), email.strip().lower(), organisation.strip(), message.strip()
    form = {"name": name, "email": email, "account_type": account_type, "organisation": organisation, "message": message}

    def refuse(key: str):
        return templates.TemplateResponse(request, "contact.html", contact_context(request, key, **form), status_code=400)

    if not name or len(name) > 120:
        return refuse("access.err.name")
    if not EMAIL_RE.fullmatch(email) or len(email) > 200:
        return refuse("auth.err.email")
    if consent != "1":
        return refuse("access.err.consent")
    if len(message) > 1000 or len(organisation) > 200:
        return refuse("access.err.too_long")
    if account_type not in ACCOUNT_TYPES:
        account_type = "professional"
    recent = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)
    if db.scalar(select(AccessRequest).where(AccessRequest.email == email, AccessRequest.created_at > recent)):
        return done  # the same person asking again within a day: one request is enough
    req = AccessRequest(name=name, email=email, account_type=account_type, organisation=organisation, message=message, lang=request.state.lang)
    db.add(req)
    db.commit()
    logging.getLogger("uvicorn.error").info("access request #%s received (%s, %s)", req.id, account_type, request.state.lang)
    if not config.CONTACT_EMAIL:
        logging.getLogger("uvicorn.error").warning("access request #%s stored but NOT e-mailed: CONTACT_EMAIL is not set (read it at /admin/requests)", req.id)
    elif mail.transport() == "log":
        logging.getLogger("uvicorn.error").warning("access request #%s stored but NOT e-mailed: no RESEND_API_KEY or SMTP_HOST configured (read it at /admin/requests)", req.id)
    if config.CONTACT_EMAIL:
        bg.add_task(mail.send, config.CONTACT_EMAIL, i18n.t("mail.access.subject", "fr", name=name),
                    i18n.t("mail.access.body", "fr", name=name, email=email, kind=i18n.t(f"access.type.{account_type}", "fr"),
                           organisation=organisation or "-", message=message or "-", language=request.state.lang, base=config.BASE_URL))
    return done


def require_admin(user: User) -> None:
    if user.email.lower() not in config.ADMIN_EMAILS:
        raise AppError(404, "err.not_found.case")  # same answer as an unknown page: the admin area is not advertised


@app.get("/admin/requests")
def admin_requests(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(user)
    rows = db.scalars(select(AccessRequest).order_by(AccessRequest.status.desc(), AccessRequest.id.desc()).limit(200)).all()
    return templates.TemplateResponse(request, "admin_requests.html", {"user": user, "rows": rows, "invite": bool(config.INVITE_CODE)})


@app.post("/admin/requests/{request_id}/done")
def admin_request_done(request_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(user)
    row = db.get(AccessRequest, request_id)
    if row:
        row.status = "done"
        db.commit()
    return RedirectResponse("/admin/requests", status_code=303)


def _legal_page(request: Request, doc: str):
    lang = request.state.lang
    return templates.TemplateResponse(request, "legal.html", {
        "doc": doc, "doc_title": legal.titles(lang)[doc], "sections": legal.render(doc, lang), "version": legal.VERSION,
        "reviewed": config.LEGAL_REVIEWED, "base_url": config.BASE_URL})


@app.get("/legal")
def legal_notice(request: Request):
    return _legal_page(request, "legal")


@app.get("/privacy")
def privacy_policy(request: Request):
    return _legal_page(request, "privacy")


@app.get("/terms")
def terms_page(request: Request):
    return _legal_page(request, "terms")


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


def after_auth(raw: str) -> str:
    """Where to go after signing in / registering: only the pricing page is allowed as a return target (no open redirect)."""
    return "/pricing" if raw == "/pricing" else "/"


def login_context(request: Request, error: str | None = None, info: str | None = None, next_url: str = "") -> dict:
    lang = request.state.lang
    return {"next_url": after_auth(next_url) if next_url == "/pricing" else "", "error": i18n.t(error, lang) if error else None, "info": i18n.t(info, lang) if info else None, "invite": bool(config.INVITE_CODE),
            "turnstile_site_key": config.TURNSTILE_SITE_KEY if captcha.enabled() else None, "free_credits": config.FREE_CREDITS}


# --- auth -------------------------------------------------------------------------------------------

@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", login_context(request, info=LOGIN_MESSAGES.get(request.query_params.get("msg", "")), next_url=request.query_params.get("next", "")))


@app.post("/register")
def register(request: Request, bg: BackgroundTasks, email: str = Form(...), password: str = Form(...), org_name: str = Form(""),
             account_type: str = Form("professional"), invite_code: str = Form(""), accept_terms: str = Form(""), next: str = Form(""), cf_turnstile_response: str = Form("", alias="cf-turnstile-response"), db: Session = Depends(get_db)):
    email = email.strip().lower()
    throttle(f"reg:{client_ip(request)}")

    def refuse(key: str, status: int):
        return templates.TemplateResponse(request, "login.html", login_context(request, error=key, next_url=next), status_code=status)

    if config.INVITE_CODE and not invite.matches(invite_code, config.INVITE_CODE):
        # Diagnostic for the operator (Railway logs). Lengths only (after normalisation): the code itself is never logged.
        logging.getLogger("uvicorn.error").warning(
            "Registration refused: invite code mismatch (submitted %d chars, configured %d chars, after ignoring case, spaces and hyphens). "
            "A difference usually means the dashboard value changed without a redeploy, or a different value was typed.",
            len(invite.normalize(invite_code)), len(invite.normalize(config.INVITE_CODE)))
        return refuse("auth.err.invite", 403)
    if not captcha.verify(cf_turnstile_response, client_ip(request)):
        return refuse("auth.err.captcha", 400)
    if not EMAIL_RE.fullmatch(email) or len(email) > 254:
        return refuse("auth.err.email", 400)
    if accept_terms != "1":
        return refuse("auth.err.terms", 400)
    account_type = account_type if account_type in ACCOUNT_TYPES else "professional"
    org_name = org_name.strip()
    if account_type == "professional" and not org_name:
        return refuse("auth.err.org_name", 400)  # a professional account is named after the agency / firm
    if len(password) < 10:
        return refuse("auth.err.password_short", 400)
    if db.scalar(select(User).where(User.email == email)):
        return refuse("auth.err.exists", 409)
    throttle(f"regday:{client_ip(request)}", config.REGISTRATIONS_PER_IP_PER_DAY, 86400)  # counts completed registrations only
    org = Org(name=(org_name or email.split("@")[0])[:200], account_type=account_type, credits=config.FREE_CREDITS)
    db.add(org)
    db.flush()
    user = User(org_id=org.id, email=email, password_hash=hash_password(password), lang=request.state.lang,
                terms_accepted_at=dt.datetime.now(dt.timezone.utc), terms_version=legal.VERSION)
    db.add(user)
    db.flush()
    audit(db, user, "account.register")
    db.commit()
    send_verification(bg, user, request.state.lang)
    open_session(request, user)
    return RedirectResponse(after_auth(next), status_code=303)


@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), next: str = Form(""), db: Session = Depends(get_db)):
    email = email.strip().lower()
    throttle(f"login:{client_ip(request)}:{email}")
    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(request, "login.html", login_context(request, error="auth.err.credentials", next_url=next), status_code=400)
    open_session(request, user)
    resp = RedirectResponse(after_auth(next), status_code=303)
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

def account_context(request: Request, user: User, db: Session, new_key: str | None = None, paid: str | None = None, changed: str | None = None) -> dict:
    org = db.get(Org, user.org_id)
    keys = db.scalars(select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.revoked == False).order_by(ApiKey.id)).all()  # noqa: E712
    bal = balance(org)
    return {"user": user, "org": org, "bal": bal, "keys": keys, "new_key": new_key, "paid": paid, "changed": changed, "base_url": config.BASE_URL,
            "stripe_ready": billing.configured(), "verification_on": config.REQUIRE_EMAIL_VERIFICATION,
            "cards": pricing.cards(request.state.lang), "max_documents": config.DOSSIER_MAX_DOCUMENTS, "vat": config.PRICES_VAT,
            "sub_name": billing.plan_name(bal["plan"], request.state.lang) if bal["plan"] else None,
            "has_customer": bool(org.stripe_customer_id)}


@app.get("/account")
def account(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "account.html", account_context(request, user, db, paid=request.query_params.get("paid"), changed=request.query_params.get("changed")))


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
           "promise_minutes": config.PROCESSING_PROMISE_MINUTES, "trial_days": config.TRIAL_DAYS if billing.trial_available(None) else 0,
           "trial_dossiers": config.TRIAL_DOSSIERS}
    if user:
        org = db.get(Org, user.org_id)
        ctx |= {"user": user, "org": org, "bal": balance(org), "trial_days": config.TRIAL_DAYS if billing.trial_available(org) else 0}
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
            "max_mb": config.MAX_UPLOAD_MB, "base_url": config.BASE_URL, "promise_minutes": config.PROCESSING_PROMISE_MINUTES,
            "trial_days": config.TRIAL_DAYS})
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
        "case": case, "user": user, "org": db.get(Org, user.org_id), "version": RULESET_VERSION, "promise_minutes": config.PROCESSING_PROMISE_MINUTES, "doc_types": DOC_TYPES, "rules_validated": config.RULES_VALIDATED,
        "prop": property_summary.build(case.documents, request.state.lang), "events": property_summary.timeline(case.documents, request.state.lang),
        "reno": renovation.build([f for f in case.findings if f.review_status != "dismissed"], case.documents, request.state.lang),
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
