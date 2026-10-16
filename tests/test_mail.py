"""Outgoing e-mail: HTTPS API (Resend), SMTP or log-only, with visible failures (the access-request e-mail that never arrived)."""
import io
import json
import logging
import urllib.error

import pytest
from fastapi.testclient import TestClient

from app import config, mail
from app.main import app


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ("RESEND_API_KEY", "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "MAIL_FROM"):
        monkeypatch.delenv(k, raising=False)


def test_transport_follows_the_configuration(monkeypatch):
    assert mail.transport() == "log"
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    assert mail.transport() == "smtp"
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    assert mail.transport() == "resend"  # the HTTPS API wins: SMTP is blocked on some hosting plans


def test_without_any_transport_the_message_is_logged_as_not_sent(caplog):
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        mail.send("a@x.be", "Subject", "Body with a link")
    assert "NOT SENT" in caplog.text and "RESEND_API_KEY" in caplog.text


def test_resend_receives_a_correct_https_request(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_secret_key")
    monkeypatch.setenv("MAIL_FROM", "Service <no-reply@example.be>")
    seen = {}

    class Resp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout=None):
        seen.update(url=req.full_url, method=req.get_method(), headers={k.lower(): v for k, v in req.header_items()}, body=json.loads(req.data), timeout=timeout)
        return Resp()

    monkeypatch.setattr(mail.urllib.request, "urlopen", fake_urlopen)
    mail.send("owner@example.be", "New request", "Hello")
    assert seen["url"] == "https://api.resend.com/emails" and seen["method"] == "POST" and seen["timeout"]
    assert seen["headers"]["authorization"] == "Bearer re_secret_key" and "belgian-property" in seen["headers"]["user-agent"]  # a UA is required by the API
    assert seen["body"] == {"from": "Service <no-reply@example.be>", "to": ["owner@example.be"], "subject": "New request", "text": "Hello"}


def test_a_refusal_by_the_api_is_logged_with_its_reason_and_never_raises(monkeypatch, caplog):
    monkeypatch.setenv("RESEND_API_KEY", "re_secret_key")

    def refuse(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, io.BytesIO(b'{"message":"You can only send testing emails to your own email address"}'))

    monkeypatch.setattr(mail.urllib.request, "urlopen", refuse)
    with caplog.at_level(logging.ERROR, logger="uvicorn.error"):
        mail.send("someone@x.be", "s", "b")
    assert "HTTP 403" in caplog.text and "testing emails" in caplog.text and "re_secret_key" not in caplog.text


def test_a_network_failure_is_logged_without_leaking_the_key(monkeypatch, caplog):
    monkeypatch.setenv("RESEND_API_KEY", "re_secret_key")
    monkeypatch.setattr(mail.urllib.request, "urlopen", lambda req, timeout=None: (_ for _ in ()).throw(TimeoutError("boom re_secret_key")))
    with caplog.at_level(logging.ERROR, logger="uvicorn.error"):
        mail.send("someone@x.be", "s", "b")
    assert "unreachable" in caplog.text and "TimeoutError" in caplog.text and "re_secret_key" not in caplog.text


def test_an_smtp_timeout_explains_the_probable_cause(monkeypatch, caplog):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "super-secret-password")

    class Broken:
        def __init__(self, *a, **k): raise TimeoutError("timed out")

    monkeypatch.setattr(mail.smtplib, "SMTP", Broken)
    with caplog.at_level(logging.ERROR, logger="uvicorn.error"):
        mail.send("someone@x.be", "s", "b")
    assert "TimeoutError" in caplog.text and "RESEND_API_KEY" in caplog.text and "super-secret-password" not in caplog.text


def test_health_reports_the_mail_transport_and_whether_access_requests_are_notified(monkeypatch):
    monkeypatch.setattr(config, "CONTACT_EMAIL", "")
    body = TestClient(app).get("/health").json()
    assert body["mail"] == "log" and body["access_notifications"] is False
    monkeypatch.setenv("RESEND_API_KEY", "k")
    monkeypatch.setattr(config, "CONTACT_EMAIL", "owner@example.be")
    body = TestClient(app).get("/health").json()
    assert body["mail"] == "resend" and body["access_notifications"] is True


def test_a_stored_request_without_any_mail_setup_says_so_in_the_log(monkeypatch, caplog):
    monkeypatch.setattr(config, "CONTACT_EMAIL", "owner@example.be")
    from app.main import _attempts
    _attempts.clear()
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        r = TestClient(app).post("/request-access", data={"name": "N", "email": "logmail@x.be", "account_type": "professional", "consent": "1"}, follow_redirects=False)
    assert r.status_code == 303 and "stored but NOT e-mailed" in caplog.text and "/admin/requests" in caplog.text


def test_verification_is_enforced_once_any_mail_transport_exists(monkeypatch):
    import importlib
    monkeypatch.delenv("REQUIRE_EMAIL_VERIFICATION", raising=False)
    monkeypatch.setenv("RESEND_API_KEY", "k")
    try:
        assert importlib.reload(config).REQUIRE_EMAIL_VERIFICATION is True
    finally:
        monkeypatch.delenv("RESEND_API_KEY")
        monkeypatch.setenv("REQUIRE_EMAIL_VERIFICATION", "0")
        importlib.reload(config)
