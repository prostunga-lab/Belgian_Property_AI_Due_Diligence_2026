"""Billing is per complete dossier: monthly quota first (subscribers), then purchased credits; atomic and rolled back on failure."""
import pytest
from fastapi.testclient import TestClient

from app import config, plans, services
from app.main import app
from tests.fixtures import ASB, DEED, ELEC, EPC, pdf
from tests.helpers import new_case, new_client, page_text
from tests.org_helpers import force_credits, get_org, org_of, set_org, subscribe

DOCS = [("akte.pdf", DEED), ("epc.pdf", EPC), ("asbest.pdf", ASB), ("keuring.pdf", ELEC)]


def put(c, cid, *docs):
    r = c.post(f"/cases/{cid}/documents", files=[("files", (n, pdf(t), "application/pdf")) for n, t in docs], follow_redirects=False)
    assert r.status_code == 303, r.text


def analyze(c, cid):
    return c.post(f"/cases/{cid}/analyze", follow_redirects=False)


def case_with_docs(c, n=4, title="t"):
    cid = new_case(c, title)
    put(c, cid, *DOCS[:n])
    return cid


def billing_of(c, cid):
    return c.get(f"/api/cases/{cid}").json()["billing"]


# --- the unit is the dossier, not the document ----------------------------------------------------------

def test_one_credit_per_dossier_whatever_the_number_of_documents():
    c = new_client("bm1@x.be"); oid = org_of("bm1@x.be"); force_credits(oid, 3)
    cid = case_with_docs(c, 4)
    assert analyze(c, cid).status_code == 303
    assert get_org(oid)["credits"] == 2 and billing_of(c, cid) == {"billed": True, "source": "credit"}
    small = case_with_docs(c, 1)  # a one-document case costs the same: one dossier
    analyze(c, small)
    assert get_org(oid)["credits"] == 1


def test_reanalysis_and_extra_documents_on_a_paid_dossier_are_free():
    c = new_client("bm2@x.be"); oid = org_of("bm2@x.be"); force_credits(oid, 2)
    cid = case_with_docs(c, 2)
    analyze(c, cid)
    analyze(c, cid)
    put(c, cid, DOCS[2], DOCS[3])
    analyze(c, cid)
    assert get_org(oid)["credits"] == 1


def test_no_dossier_left_is_refused_and_nothing_changes():
    c = new_client("bm3@x.be"); oid = org_of("bm3@x.be"); force_credits(oid, 0)
    cid = case_with_docs(c, 2)
    r = analyze(c, cid)
    assert r.status_code == 402 and r.json()["code"] == "err.insufficient_credits"
    assert get_org(oid)["credits"] == 0 and billing_of(c, cid)["billed"] is False
    assert c.get(f"/api/cases/{cid}").json()["status"] == "draft"


def test_failed_analysis_spends_nothing(monkeypatch):
    c = new_client("bm4@x.be"); oid = org_of("bm4@x.be"); force_credits(oid, 2)
    cid = case_with_docs(c, 2)
    monkeypatch.setattr(services, "analyze_case", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    boom = TestClient(app, raise_server_exceptions=False); boom.cookies = c.cookies
    assert boom.post(f"/cases/{cid}/analyze").status_code == 500
    assert get_org(oid)["credits"] == 2 and billing_of(c, cid)["billed"] is False
    subscribe(oid, used=3, credits=0)
    assert boom.post(f"/cases/{cid}/analyze").status_code == 500
    assert get_org(oid)["cycle_used"] == 3  # the quota is restored too


def test_last_credit_cannot_be_spent_twice():
    c = new_client("bm5@x.be"); oid = org_of("bm5@x.be"); force_credits(oid, 1)
    a, b = case_with_docs(c, 2, "a"), case_with_docs(c, 2, "b")
    assert analyze(c, a).status_code == 303
    assert analyze(c, b).status_code == 402
    assert get_org(oid)["credits"] == 0


# --- subscription quota ----------------------------------------------------------------------------------

def test_subscribers_consume_their_monthly_quota_before_credits():
    c = new_client("bm6@x.be"); oid = org_of("bm6@x.be"); subscribe(oid, used=0, credits=2)
    for i in range(2):
        analyze(c, case_with_docs(c, 2, f"c{i}"))
    org = get_org(oid)
    assert org["cycle_used"] == 2 and org["credits"] == 2  # credits untouched while quota remains
    cid = case_with_docs(c, 2, "x"); analyze(c, cid)
    assert billing_of(c, cid)["source"] == "quota"


def test_when_the_quota_is_used_up_purchased_credits_take_over_then_it_stops():
    quota = plans.get("agent").dossiers
    c = new_client("bm7@x.be"); oid = org_of("bm7@x.be"); subscribe(oid, used=quota, credits=1)
    cid = case_with_docs(c, 2, "a"); assert analyze(c, cid).status_code == 303
    assert billing_of(c, cid)["source"] == "credit" and get_org(oid) | {} and get_org(oid)["credits"] == 0 and get_org(oid)["cycle_used"] == quota
    r = analyze(c, case_with_docs(c, 2, "b"))
    assert r.status_code == 402 and r.json()["code"] == "err.quota_exhausted"


def test_the_quota_is_exactly_the_plan_size():
    quota = plans.get("agent").dossiers
    assert quota == 15  # strategy: "limité à 15 dossiers par mois"
    c = new_client("bm8@x.be"); oid = org_of("bm8@x.be"); subscribe(oid, used=quota - 1, credits=0)
    assert analyze(c, case_with_docs(c, 1, "last")).status_code == 303
    assert get_org(oid)["cycle_used"] == quota
    assert analyze(c, case_with_docs(c, 1, "over")).status_code == 402


@pytest.mark.parametrize("status", ["past_due", "unpaid", "canceled", "incomplete", "incomplete_expired", None])
def test_only_active_or_trialing_subscriptions_give_quota(status):
    email = f"bm9-{str(status).lower()}@x.be"  # e-mails are stored lower-case
    c = new_client(email); oid = org_of(email); subscribe(oid, status=status, used=0, credits=0)
    r = analyze(c, case_with_docs(c, 1))
    assert r.status_code == 402 and r.json()["code"] == "err.insufficient_credits"  # not "quota exhausted": there is no usable quota
    assert get_org(oid)["cycle_used"] == 0


def test_trialing_subscription_counts_as_active():
    c = new_client("bm10@x.be"); oid = org_of("bm10@x.be"); subscribe(oid, status="trialing")
    assert analyze(c, case_with_docs(c, 1)).status_code == 303 and get_org(oid)["cycle_used"] == 1


# --- dossier size cap ------------------------------------------------------------------------------------

def test_a_dossier_holds_a_bounded_number_of_documents(monkeypatch):
    monkeypatch.setattr(config, "DOSSIER_MAX_DOCUMENTS", 3)
    c = new_client("bm11@x.be")
    cid = case_with_docs(c, 3)
    r = c.post(f"/cases/{cid}/documents", files=[("files", ("extra.pdf", pdf(DEED), "application/pdf"))])
    assert r.status_code == 400 and r.json()["code"] == "err.dossier_full"
    assert len(c.get(f"/api/cases/{cid}").json()["documents"]) == 3


def test_analysis_refuses_an_oversized_dossier_even_if_the_limit_was_lowered_later(monkeypatch):
    c = new_client("bm12@x.be"); oid = org_of("bm12@x.be"); force_credits(oid, 2)
    cid = case_with_docs(c, 4)
    monkeypatch.setattr(config, "DOSSIER_MAX_DOCUMENTS", 2)
    r = analyze(c, cid)
    assert r.status_code == 400 and r.json()["code"] == "err.too_many_documents" and get_org(oid)["credits"] == 2


# --- what the user sees ------------------------------------------------------------------------------------

def test_new_organisations_receive_the_free_dossiers(monkeypatch):
    monkeypatch.setattr(config, "FREE_CREDITS", 1)
    c = new_client("bm13@x.be")
    assert get_org(org_of("bm13@x.be"))["credits"] == 1
    assert analyze(c, case_with_docs(c, 4)).status_code == 303
    assert analyze(c, case_with_docs(c, 4)).status_code == 402


@pytest.mark.parametrize("lang,expected", [("fr", "5 dossiers disponibles"), ("nl", "5 dossiers beschikbaar"), ("en", "5 cases available")])
def test_header_shows_everything_the_user_can_still_analyse(lang, expected):
    c = new_client(f"bm14-{lang}@x.be"); oid = org_of(f"bm14-{lang}@x.be"); subscribe(oid, used=13, credits=3)  # 2 left on quota + 3 credits
    c.get(f"/lang/{lang}")
    assert expected in page_text(c.get("/"))


def test_case_page_tells_where_the_dossier_will_come_from():
    c = new_client("bm15@x.be"); oid = org_of("bm15@x.be")
    cid = case_with_docs(c, 2)
    force_credits(oid, 0); set_org(oid, plan="trial", subscription_status=None)
    assert "Plus de dossier disponible" in page_text(c.get(f"/cases/{cid}")) and "disabled" in c.get(f"/cases/{cid}").text.split("Analyser")[0].rsplit("<button", 1)[1]
    force_credits(oid, 2)
    assert "1 crédit sera utilisé (solde : 2)" in page_text(c.get(f"/cases/{cid}"))
    subscribe(oid, used=4, credits=0)
    assert "1 dossier sera décompté de votre abonnement (11 restants ce mois-ci)" in page_text(c.get(f"/cases/{cid}"))
    analyze(c, cid)
    assert "déjà payé" in page_text(c.get(f"/cases/{cid}"))


def test_dashboard_and_account_show_the_balance_and_the_subscription():
    c = new_client("bm16@x.be"); oid = org_of("bm16@x.be"); subscribe(oid, used=4, credits=2)
    assert "13 dossiers disponibles" in page_text(c.get("/"))
    acct = page_text(c.get("/account"))
    assert "Abonnement Agent — 15 dossiers par mois" in acct and "4 dossiers sur 15 utilisés ce mois-ci" in acct and "actif" in acct and "2 crédits" in acct


def test_api_dossier_costs_one_credit_for_any_number_of_files():
    import re
    c = new_client("bm17@x.be"); oid = org_of("bm17@x.be"); force_credits(oid, 2)
    key = re.search(r"(sk_live_[\w\-]+)", c.post("/account/keys").text).group(1)
    api = TestClient(app, headers={"x-api-key": key})
    r = api.post("/v1/dossier", files=[("files", (n, pdf(t), "application/pdf")) for n, t in DOCS])
    assert r.status_code == 200 and r.json()["billing"] == {"billed": True, "source": "credit"} and get_org(oid)["credits"] == 1
    assert 0 <= r.json()["analysis_seconds"] < 60
