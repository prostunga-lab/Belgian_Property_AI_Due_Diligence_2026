"""Outgoing e-mail: an HTTPS e-mail API (Resend) or SMTP, or a log line when neither is configured.

Railway blocks outbound SMTP on the Free, Trial and Hobby plans, so an HTTPS API is the way to send mail from there:
set RESEND_API_KEY (and MAIL_FROM). SMTP (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD) keeps working elsewhere.
Failures are logged with their reason (never a password or key) and never break the request that triggered the e-mail.
"""
import json
import logging
import os
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage

log = logging.getLogger("uvicorn.error")
RESEND_URL = "https://api.resend.com/emails"


def transport() -> str:
    """'resend' | 'smtp' | 'log' (nothing configured: messages are only written to the server log)."""
    if os.getenv("RESEND_API_KEY"):
        return "resend"
    return "smtp" if os.getenv("SMTP_HOST") else "log"


def _send_resend(to: str, subject: str, body: str) -> None:
    payload = json.dumps({"from": os.getenv("MAIL_FROM", "onboarding@resend.dev"), "to": [to], "subject": subject, "text": body}).encode()
    req = urllib.request.Request(RESEND_URL, data=payload, method="POST", headers={
        "Authorization": f"Bearer {os.environ['RESEND_API_KEY']}", "Content-Type": "application/json", "User-Agent": "belgian-property-dd/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            log.info("[MAIL] sent via Resend (HTTP %s)", resp.status)
    except urllib.error.HTTPError as e:  # the API explains refusals (unverified domain, test sender restricted to the account owner...)
        log.error("[MAIL] Resend refused the message: HTTP %s %s", e.code, e.read()[:300].decode("utf-8", "replace"))
    except Exception as e:
        log.error("[MAIL] Resend unreachable: %s", type(e).__name__)


def _send_smtp(to: str, subject: str, body: str) -> None:
    m = EmailMessage()
    m["From"] = os.getenv("MAIL_FROM", "no-reply@localhost")
    m["To"], m["Subject"] = to, subject
    m.set_content(body)
    host, port = os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT", "587"))
    ctx = ssl.create_default_context()
    try:
        s = smtplib.SMTP_SSL(host, port, timeout=15, context=ctx) if port == 465 else smtplib.SMTP(host, port, timeout=15)
        with s:
            if port != 465:
                s.starttls(context=ctx)
            if os.getenv("SMTP_USER"):
                s.login(os.environ["SMTP_USER"], os.getenv("SMTP_PASSWORD", ""))
            s.send_message(m)
        log.info("[MAIL] sent via SMTP")
    except Exception as e:
        log.error("[MAIL] SMTP send failure: %s (timeouts usually mean the host blocks outbound SMTP: use RESEND_API_KEY instead)", type(e).__name__)


def send(to: str, subject: str, body: str) -> None:
    kind = transport()
    if kind == "resend":
        _send_resend(to, subject, body)
    elif kind == "smtp":
        _send_smtp(to, subject, body)
    else:  # dev mode: the message (links included) is only written to the server log
        log.warning("[MAIL dev] NOT SENT (no RESEND_API_KEY or SMTP_HOST configured) to=%s subject=%s\n%s", to, subject, body)
