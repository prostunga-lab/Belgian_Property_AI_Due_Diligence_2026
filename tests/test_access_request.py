"""Access requests (pre-launch review F01) and individual/professional registration with a consistent trial (F06)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import config, mail
from app.i18n import CATALOGS, LANGS
from app.main import app, _attempts
from app.models import AccessRequest, Org, SessionLocal, User
from tests.helpers import new_client, page_text

GOOD = {"name": "Camille Dupont", "email": "camille@agence.be", "account_type": "professional", "organisation": "Agence Dupont", "message": "Je voudrais tester.", "consent": "1"}


def anon(lang="fr", **kw):
    return TestClient(app, cookies={"lang": lang}, **kw)


def requests_of(email):
    with SessionLocal() as db:
        return db.scalars(select(AccessRequest).where(AccessRequest.email == email)).all()


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    _attempts.clear()
    monkeypatch.setattr(config, "CONTACT_EMAIL", "")


def test_a_request_is_stored_and_acknowledged_in_every_language():
    for i, lang in enumerate(LANGS):
        email = f"ack{i}@x.be"
        c = anon(lang)
        r = c.post("/request-access", data={**GOOD, "email": email}, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/contact?sent=1#access"
        assert CATALOGS[lang]["access.sent"] in page_text(c.get("/contact?sent=1"))
        row, = requests_of(email)
        assert row.name == "Camille Dupont" and row.account_type == "professional" and row.lang == lang and row.status == "new"


@pytest.mark.parametrize("change,key", [({"name": " "}, "access.err.name"), ({"email": "not-an-email"}, "auth.err.email"), ({"consent": ""}, "access.err.consent"),
                                         ({"message": "x" * 1001}, "access.err.too_long"), ({"name": "n" * 121}, "access.err.name")])
def test_invalid_requests_are_refused_with_a_message_and_keep_the_typed_values(change, key):
    c = anon("en")
    r = c.post("/request-access", data={**GOOD, "email": "bad@x.be", **change})
    assert r.status_code == 400 and CATALOGS["en"][key] in page_text(r)
    assert requests_of("bad@x.be") == [] or "email" in change
    if "name" not in change:
        assert "Camille Dupont" in r.text  # the form is shown again with what was typed


def test_the_hidden_honeypot_field_makes_bots_look_successful_but_stores_nothing():
    r = anon().post("/request-access", data={**GOOD, "email": "bot@x.be", "hp_check": "http://spam.example"}, follow_redirects=False)
    assert r.status_code == 303 and requests_of("bot@x.be") == []


def test_the_same_person_asking_twice_in_a_day_creates_one_request():
    for _ in range(2):
        assert anon().post("/request-access", data={**GOOD, "email": "twice@x.be"}, follow_redirects=False).status_code == 303
    assert len(requests_of("twice@x.be")) == 1


def test_requests_are_rate_limited_per_address():
    codes = [anon().post("/request-access", data={**GOOD, "email": f"rate{i}@x.be"}, follow_redirects=False).status_code for i in range(5)]
    assert codes[:3] == [303, 303, 303] and codes[3] == 429


def test_the_owner_is_notified_by_e_mail_when_a_contact_address_is_configured(monkeypatch):
    sent = []
    monkeypatch.setattr(mail, "send", lambda to, subject, body: sent.append((to, subject, body)))
    anon().post("/request-access", data={**GOOD, "email": "nomail@x.be"})
    assert sent == []  # nothing configured: the request is still stored, no address is guessed
    monkeypatch.setattr(config, "CONTACT_EMAIL", "owner@example.be")
    anon().post("/request-access", data={**GOOD, "email": "notify@x.be"})
    to, subject, body = sent[0]
    assert to == "owner@example.be" and "Camille Dupont" in subject and "notify@x.be" in body and "/admin/requests" in body


def test_contact_form_shows_on_the_page_and_is_linked_from_landing_and_login_when_invitation_only(monkeypatch):
    monkeypatch.setattr(config, "INVITE_CODE", "abcd-efgh")
    for lang in LANGS:
        assert CATALOGS[lang]["access.title"] in page_text(anon(lang).get("/contact"))
    monkeypatch.setattr(config, "INVITE_CODE", None)
    for lang in LANGS:  # open registration: the same form is just a way to write to the owner
        assert CATALOGS[lang]["access.title.open"] in page_text(anon(lang).get("/contact"))
    monkeypatch.setattr(config, "INVITE_CODE", None)
    assert 'href="/contact#access"' not in anon().get("/").text and 'href="/contact#access"' not in anon().get("/login").text
    monkeypatch.setattr(config, "INVITE_CODE", "abcd-efgh")
    assert 'href="/contact#access"' in anon().get("/").text and 'href="/contact#access"' in anon().get("/login").text


# --- admin view ------------------------------------------------------------------------------------

def test_only_administrators_can_read_the_requests_and_content_is_escaped(monkeypatch):
    anon().post("/request-access", data={**GOOD, "email": "xss@x.be", "message": "<script>alert(1)</script><b>bold</b>"})
    c = new_client("admin1@x.be")
    assert c.get("/admin/requests").status_code == 404  # signed in, not an administrator
    assert anon().get("/admin/requests", follow_redirects=False).status_code in (303, 401)
    monkeypatch.setattr(config, "ADMIN_EMAILS", {"admin1@x.be"})
    r = c.get("/admin/requests")
    assert r.status_code == 200 and "xss@x.be" in r.text and "<script>alert(1)</script>" not in r.text and "&lt;script&gt;" in r.text


def test_an_administrator_can_mark_a_request_as_handled_and_others_cannot(monkeypatch):
    anon().post("/request-access", data={**GOOD, "email": "handled@x.be"})
    rid = requests_of("handled@x.be")[0].id
    other = new_client("notadmin@x.be")
    assert other.post(f"/admin/requests/{rid}/done").status_code == 404 and requests_of("handled@x.be")[0].status == "new"
    monkeypatch.setattr(config, "ADMIN_EMAILS", {"admin2@x.be"})
    admin = new_client("admin2@x.be")
    assert admin.post(f"/admin/requests/{rid}/done", follow_redirects=False).status_code == 303
    assert requests_of("handled@x.be")[0].status == "done"


# --- registration: individual or professional, one trial rule ------------------------------------

def org_of(email):
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.email == email))
        return db.get(Org, u.org_id)


def test_an_individual_can_register_without_an_organisation_name():
    c = anon()
    r = c.post("/register", data={"email": "indiv@x.be", "password": "supersecret12", "account_type": "individual", "accept_terms": "1"}, follow_redirects=False)
    assert r.status_code == 303
    o = org_of("indiv@x.be")
    assert o.account_type == "individual" and o.name == "indiv"


def test_a_professional_must_name_the_organisation():
    r = anon("en").post("/register", data={"email": "pro@x.be", "password": "supersecret12", "account_type": "professional", "accept_terms": "1"})
    assert r.status_code == 400 and CATALOGS["en"]["auth.err.org_name"] in page_text(r)
    ok = anon().post("/register", data={"email": "pro2@x.be", "password": "supersecret12", "org_name": "Agence X", "account_type": "professional", "accept_terms": "1"}, follow_redirects=False)
    assert ok.status_code == 303 and org_of("pro2@x.be").name == "Agence X" and org_of("pro2@x.be").account_type == "professional"


def test_an_unknown_account_type_falls_back_to_professional_rules():
    r = anon().post("/register", data={"email": "weird@x.be", "password": "supersecret12", "account_type": "admin", "accept_terms": "1"})
    assert r.status_code == 400  # treated as professional, so the organisation name is required


@pytest.mark.parametrize("n", [0, 1, 3])
def test_the_trial_promised_everywhere_is_exactly_the_credit_granted(monkeypatch, n):
    monkeypatch.setattr(config, "FREE_CREDITS", n)
    promise = {"fr": {0: None, 1: "1 dossier complet offert", 3: "3 dossiers complets offerts"}[n]}
    for page in ("/login", "/pricing", "/"):
        text = page_text(anon("fr").get(page))
        if n:
            assert promise["fr"] in text, page
        else:
            assert "offert" not in text.replace("offerts", "offert") or "pour essayer" not in text, page
    anon().post("/register", data={"email": f"trial{n}@x.be", "password": "supersecret12", "account_type": "individual", "accept_terms": "1"})
    assert org_of(f"trial{n}@x.be").credits == n
