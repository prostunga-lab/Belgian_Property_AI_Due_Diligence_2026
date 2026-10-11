"""Security headers on every response, a strict CSP without inline scripts, readable error pages (pre-launch review F07, F08, F09)."""
import re

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from tests.helpers import new_client

PUBLIC = ["/", "/about", "/pricing", "/contact", "/legal", "/privacy", "/terms", "/login", "/forgot"]
PROTECTIONS = ("x-content-type-options", "x-frame-options", "referrer-policy", "content-security-policy", "content-language")


def anon(**kw):
    return TestClient(app, raise_server_exceptions=False, **kw)


def assert_protected(r, secure=True):
    missing = [h for h in PROTECTIONS if h not in r.headers]
    assert not missing, f"{r.request.method} {r.url.path} {r.status_code}: missing {missing}"
    if secure:
        assert "strict-transport-security" in r.headers


@pytest.fixture(autouse=True)
def https_mode(monkeypatch):
    monkeypatch.setattr(config, "COOKIE_SECURE", True)


@pytest.mark.parametrize("path", PUBLIC)
def test_every_public_page_carries_the_protections(path):
    assert_protected(anon().get(path))


def test_every_kind_of_response_carries_the_protections():
    c = anon()
    assert_protected(c.get("/lang/fr?next=/", follow_redirects=False))  # 303
    assert_protected(c.get("/no-such-page"))  # 404 (browser page)
    assert_protected(c.get("/v1/no-such", headers={"accept": "application/json"}))  # 404 JSON
    assert_protected(c.post("/login", data={"email": "a@x.be", "password": "x"}, headers={"origin": "https://example.invalid"}))  # early 403
    assert_protected(c.get("/cases/1", follow_redirects=False))  # 401/303 for anonymous
    assert_protected(c.put("/about"))  # 405
    assert_protected(c.get("/static/app.js"))  # static file


def test_the_csp_forbids_inline_scripts_and_framing_and_allows_the_payment_redirect():
    csp = anon().get("/about").headers["content-security-policy"]
    script_src = re.search(r"script-src ([^;]*)", csp).group(1)
    assert script_src == "'self'" and "unsafe-inline" not in script_src and "unsafe-eval" not in script_src
    for needed in ("default-src 'self'", "object-src 'none'", "base-uri 'none'", "frame-ancestors 'none'", "https://checkout.stripe.com", "https://billing.stripe.com"):
        assert needed in csp


def test_csp_can_be_switched_to_report_only_or_off(monkeypatch):
    monkeypatch.setattr(config, "CSP_MODE", "report-only")
    r = anon().get("/about")
    assert "content-security-policy-report-only" in r.headers and "content-security-policy" not in r.headers
    monkeypatch.setattr(config, "CSP_MODE", "off")
    r = anon().get("/about")
    assert "content-security-policy" not in r.headers and "content-security-policy-report-only" not in r.headers


def all_pages_html():
    c = new_client("csp-pages@x.be")
    from tests.fixtures import DEED, EPC
    from tests.test_property_intelligence import upload_and_analyze
    cid = upload_and_analyze(c, [("akte.txt", DEED), ("epc.txt", EPC)])
    pages = [c.get(p).text for p in PUBLIC + ["/account", "/pricing", f"/cases/{cid}", "/no-such-page"]]
    return pages + [anon().get("/login").text, anon().get("/no-such-page", headers={"accept": "text/html"}).text]


def test_no_inline_script_handler_or_javascript_url_in_any_rendered_page():
    for html in all_pages_html():
        assert not re.search(r"<script(?![^>]*\bsrc=)", html, re.I), "inline <script> found"
        assert not re.search(r"\son(?:click|change|submit|load|error|focus|input|mouse\w+)\s*=", html, re.I), "inline event handler found"
        assert not re.search(r"""(?:href|src|action|formaction)\s*=\s*["']\s*javascript:""", html, re.I)


def test_behaviour_script_is_served_and_destructive_forms_declare_their_confirmation():
    js = anon().get("/static/app.js")
    assert js.status_code == 200 and "javascript" in js.headers["content-type"] and "data-confirm" in js.text and "pwtoggle" in js.text
    c = new_client("csp-confirm@x.be")
    assert 'data-confirm="' in c.get("/account").text
    from tests.helpers import new_case
    assert 'data-confirm="' in c.get(f"/cases/{new_case(c)}").text


def test_unknown_page_is_a_readable_html_page_for_browsers_and_for_clients_without_accept():
    for headers in ({"accept": "text/html"}, {}):
        r = anon().get("/audit-nonexistent", headers={**headers, "accept": headers.get("accept", "")} if headers else {"accept": ""})
        assert r.status_code == 404 and r.headers["content-type"].startswith("text/html") and 'href="/"' in r.text
    r = anon().get("/audit-nonexistent", headers={"accept": "application/json"})
    assert r.status_code == 404 and r.json()["detail"]  # API-style clients keep JSON
    r = anon().get("/v1/unknown")
    assert r.status_code == 404 and r.headers["content-type"].startswith("application/json")  # API paths keep JSON


def test_unexpected_errors_return_a_generic_answer_with_the_same_protections(monkeypatch):
    @app.get("/__boom")
    def boom():
        raise RuntimeError("secret internal detail")
    r = anon().get("/__boom")
    assert r.status_code == 500 and "secret internal detail" not in r.text and "Traceback" not in r.text
    assert_protected(r)
    app.router.routes[:] = [x for x in app.router.routes if getattr(x, "path", "") != "/__boom"]
