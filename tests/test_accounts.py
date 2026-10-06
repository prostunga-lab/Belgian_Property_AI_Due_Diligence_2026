import pytest

from app import config, mail
from tests.helpers import link_in, new_client


@pytest.fixture
def outbox(monkeypatch):
    box = []
    monkeypatch.setattr(mail, "send", lambda to, subject, body: box.append((to, subject, body)))
    return box


def test_verification_email_and_enforcement(monkeypatch, outbox):
    monkeypatch.setattr(config, "REQUIRE_EMAIL_VERIFICATION", True)
    c = new_client("v1@x.be")
    assert len(outbox) == 1 and outbox[0][0] == "v1@x.be"
    # unverified accounts cannot analyse, cannot create API keys
    from tests.helpers import new_case
    from tests.fixtures import DEED, pdf
    cid = new_case(c)
    c.post(f"/cases/{cid}/documents", files=[("files", ("akte.pdf", pdf(DEED), "application/pdf"))])
    assert c.post(f"/cases/{cid}/analyze", follow_redirects=False).status_code == 403
    assert c.post("/account/keys").status_code == 403
    assert "non confirmé" in c.get("/account").text
    # the link confirms the address
    r = c.get(link_in(outbox[0][2], "/verify").replace("http://testserver", ""), follow_redirects=False)
    assert r.status_code == 303
    assert c.post(f"/cases/{cid}/analyze", follow_redirects=False).status_code == 303


def test_verification_token_is_bound_and_tamper_proof(outbox):
    c = new_client("v2@x.be")
    tok = link_in(outbox[0][2], "/verify").split("token=")[1]
    assert c.get("/verify?token=" + tok[:-3] + "xxx").status_code == 400
    assert c.get("/verify?token=garbage").status_code == 400


def test_resend_is_throttled(monkeypatch, outbox):
    monkeypatch.setattr(config, "REQUIRE_EMAIL_VERIFICATION", True)
    c = new_client("v3@x.be")
    codes = [c.post("/verify/resend", follow_redirects=False).status_code for _ in range(4)]
    assert codes == [303, 303, 303, 429]


def test_forgot_and_reset_flow_single_use(outbox):
    c = new_client("r1@x.be")
    outbox.clear()
    # same answer for unknown and known accounts (no enumeration)
    a = c.post("/forgot", data={"email": "nobody@x.be"})
    b = c.post("/forgot", data={"email": "r1@x.be"})
    assert a.status_code == b.status_code == 200 and a.text == b.text
    assert [m[0] for m in outbox] == ["r1@x.be"]
    link = link_in(outbox[0][2], "/reset")
    token = link.split("token=")[1]
    assert c.get("/reset?token=" + token).status_code == 200
    assert c.post("/reset", data={"token": token, "password": "short"}).status_code == 400
    assert c.post("/reset", data={"token": token, "password": "brand-new-password"}, follow_redirects=False).status_code == 303
    # link is single-use: replay fails
    assert c.post("/reset", data={"token": token, "password": "another-password-1"}).status_code == 400
    # old password dead, new one works
    other = new_client("r1@x.be", register=False)
    assert other.post("/login", data={"email": "r1@x.be", "password": "supersecret12"}).status_code == 400
    assert other.post("/login", data={"email": "r1@x.be", "password": "brand-new-password"}, follow_redirects=False).status_code == 303


def test_password_reset_logs_out_existing_sessions(outbox):
    victim = new_client("r2@x.be")
    assert victim.get("/api/cases/1").status_code in (404,)  # authenticated (case does not exist)
    other = new_client("r2@x.be", register=False)
    other.post("/forgot", data={"email": "r2@x.be"})
    token = link_in(outbox[-1][2], "/reset").split("token=")[1]
    other.post("/reset", data={"token": token, "password": "brand-new-password"})
    assert victim.get("/api/cases/1").status_code == 401  # stolen/old session is dead


def test_reset_token_cannot_be_used_as_verify_token(outbox):
    c = new_client("r3@x.be")
    c.post("/forgot", data={"email": "r3@x.be"})
    token = link_in(outbox[-1][2], "/reset").split("token=")[1]
    assert c.get("/verify?token=" + token).status_code == 400


def test_registration_validation():
    c = new_client("x", register=False)
    bad_mail = c.post("/register", data={"org_name": "O", "email": "not-an-email", "password": "supersecret12"})
    assert bad_mail.status_code == 400
    assert c.post("/register", data={"org_name": "O", "email": "dup@x.be", "password": "supersecret12"}, follow_redirects=False).status_code == 303
    assert c.post("/register", data={"org_name": "O", "email": "DUP@x.be", "password": "supersecret12"}).status_code == 409


def test_account_deletion_erases_everything():
    from app import config as cfg
    from tests.fixtures import DEED, pdf
    from tests.helpers import new_case
    c = new_client("gone@x.be")
    cid = new_case(c)
    c.post(f"/cases/{cid}/documents", files=[("files", ("akte.pdf", pdf(DEED), "application/pdf"))])
    folder = next(cfg.UPLOAD_DIR.glob(f"*/{cid}"))
    assert c.post("/account/delete", data={"password": "wrong-password"}).status_code == 403
    assert c.post("/account/delete", data={"password": "supersecret12"}, follow_redirects=False).status_code == 303
    assert not folder.exists()
    assert c.get(f"/api/cases/{cid}").status_code == 401
    assert new_client("gone@x.be", register=False).post("/login", data={"email": "gone@x.be", "password": "supersecret12"}).status_code == 400
