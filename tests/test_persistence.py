import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config, main, storage
from app.main import app
from tests.fixtures import DEED, EPC, pdf


def register(c, email, **extra):
    return c.post("/register", data={"org_name": "Org", "email": email, "password": "supersecret12", **extra}, follow_redirects=False)


def new_case(c, title="t"):
    r = c.post("/cases", data={"title": title}, follow_redirects=False)
    return int(re.search(r"/cases/(\d+)", r.headers["location"]).group(1))


def test_files_encrypted_at_rest_and_still_processed(monkeypatch):
    monkeypatch.setattr(config, "FILE_ENCRYPTION_KEY", "unit-test-key")
    c = TestClient(app)
    register(c, "enc@x.be")
    cid = new_case(c)
    c.post(f"/cases/{cid}/documents", files=[("files", ("epc.pdf", pdf(EPC), "application/pdf"))])
    files = list(next(config.UPLOAD_DIR.glob(f"*/{cid}")).iterdir())
    assert files and all(b"%PDF" not in f.read_bytes()[:20] and b"Energieprestatie" not in f.read_bytes() for f in files)
    assert c.get(f"/api/cases/{cid}").json()["documents"][0]["type"] == "epc"
    # reprocessing from the encrypted file works with the right key and fails loudly with the wrong one
    assert storage.read(files[-1]).startswith(b"%PDF")
    monkeypatch.setattr(config, "FILE_ENCRYPTION_KEY", "another-key")
    with pytest.raises(RuntimeError):
        storage.read(files[-1])


def test_invite_code_required(monkeypatch):
    monkeypatch.setattr(config, "INVITE_CODE", "s3cret-invite")
    c = TestClient(app)
    assert register(c, "i1@x.be").status_code == 403
    assert register(c, "i1@x.be", invite_code="wrong").status_code == 403
    assert register(c, "i1@x.be", invite_code="s3cret-invite").status_code == 303
    import html
    assert "Code d'invitation" in html.unescape(TestClient(app).get("/login").text)


def test_cross_site_post_rejected():
    c = TestClient(app)
    register(c, "csrf@x.be")
    bad = c.post("/cases", data={"title": "x"}, headers={"origin": "https://evil.example"}, follow_redirects=False)
    assert bad.status_code == 403
    ok = c.post("/cases", data={"title": "x"}, headers={"origin": "http://testserver"}, follow_redirects=False)
    assert ok.status_code == 303


def test_login_throttle(monkeypatch):
    monkeypatch.setattr(main, "LOGIN_MAX", 3)
    main._attempts.clear()
    c = TestClient(app)
    codes = [c.post("/login", data={"email": "nobody@x.be", "password": "wrong-password"}).status_code for _ in range(5)]
    assert codes == [400, 400, 400, 429, 429]


def test_delete_case_erases_data_and_files():
    c = TestClient(app)
    register(c, "del@x.be")
    cid = new_case(c, "te wissen")
    c.post(f"/cases/{cid}/documents", files=[("files", ("akte.pdf", pdf(DEED), "application/pdf"))])
    org_case_dir = next(p for p in config.UPLOAD_DIR.glob("*/*") if p.name == str(cid))
    assert any(org_case_dir.iterdir())
    other = TestClient(app)
    register(other, "other@x.be")
    assert other.post(f"/cases/{cid}/delete", follow_redirects=False).status_code == 404  # tenant isolation
    assert c.post(f"/cases/{cid}/delete", follow_redirects=False).status_code == 303
    assert not org_case_dir.exists()
    assert c.get(f"/api/cases/{cid}").status_code == 404


def test_health_checks_database():
    assert TestClient(app).get("/health").json()["status"] == "ok"


def test_production_refuses_insecure_config(monkeypatch):
    import importlib
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("FILE_ENCRYPTION_KEY", raising=False)
    with pytest.raises(RuntimeError, match="not configured"):
        importlib.reload(config)
    monkeypatch.delenv("APP_ENV")
    importlib.reload(config)


def test_database_url_normalisation(monkeypatch):
    import importlib
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@host:5432/db")
    importlib.reload(config)
    assert config.DB_URL == "postgresql+psycopg://u:p@host:5432/db"
    monkeypatch.undo()
    importlib.reload(config)


def test_public_url_detection(monkeypatch):
    import importlib
    for k in ("BASE_URL", "RAILWAY_PUBLIC_DOMAIN", "RENDER_EXTERNAL_URL"):
        monkeypatch.delenv(k, raising=False)
    importlib.reload(config)
    assert config.BASE_URL == "http://localhost:8000"
    monkeypatch.setenv("RAILWAY_PUBLIC_DOMAIN", "dd.up.railway.app")
    importlib.reload(config)
    assert config.BASE_URL == "https://dd.up.railway.app"
    monkeypatch.setenv("BASE_URL", "https://dd.example.be/")
    importlib.reload(config)
    assert config.BASE_URL == "https://dd.example.be"  # explicit wins, trailing slash dropped
    monkeypatch.undo()
    importlib.reload(config)


def test_invite_code_survives_copy_paste_whitespace_and_quotes(monkeypatch):
    # configured value pasted with a trailing newline + quotes, typed value with spaces: must still match
    for configured in ("  s3cret-invite\n", '"s3cret-invite"', "s3cret-invite "):
        monkeypatch.setenv("INVITE_CODE", configured)
        import importlib
        importlib.reload(config)
        assert config.INVITE_CODE == "s3cret-invite"
        monkeypatch.setattr(config, "INVITE_CODE", config.INVITE_CODE)
        c = TestClient(app)
        ok = register(c, f"inv-{abs(hash(configured))}@x.be", invite_code="  s3cret-invite ")
        assert ok.status_code == 303
    assert register(TestClient(app), "inv-bad@x.be", invite_code="s3cret-invitf").status_code == 403
    monkeypatch.undo()
    importlib.reload(config)


def test_invite_failure_is_diagnosable_without_leaking_the_code(monkeypatch, caplog):
    import logging
    monkeypatch.setattr(config, "INVITE_CODE", "topsecret-code-123")
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        assert register(TestClient(app), "inv-log@x.be", invite_code="wrong-one").status_code == 403
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "invite code mismatch" in text and "submitted 9 chars" in text and "configured 18 chars" in text
    assert "topsecret-code-123" not in text and "wrong-one" not in text


def test_app_env_and_flags_ignore_stray_whitespace(monkeypatch):
    import importlib
    monkeypatch.setenv("APP_ENV", "Production \n")
    monkeypatch.setenv("COOKIE_SECURE", " 1 ")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setenv("FILE_ENCRYPTION_KEY", "y" * 40)
    monkeypatch.setenv("INVITE_CODE", "abc")
    importlib.reload(config)
    assert config.APP_ENV == "production" and config.COOKIE_SECURE  # a stray space must not silently disable the guard
    monkeypatch.delenv("INVITE_CODE")
    with pytest.raises(RuntimeError, match="INVITE_CODE"):
        importlib.reload(config)  # and the guard really is on
    monkeypatch.undo()
    importlib.reload(config)
