"""Pre-launch review follow-ups: demo report (F11), severity/nature explanations (F11), visible region scope (F10), rule register and banner (F04)."""
import io

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app import config, demo, rules_doc
from app.i18n import CATALOGS, LANGS
from app.main import app
from app.rules import RULE_IDS
from tests.helpers import new_client, page_text
from tests.test_property_intelligence import upload_and_analyze
from tests.fixtures import ASB, DEED, ELEC, EPC


def anon(lang="fr"):
    return TestClient(app, cookies={"lang": lang})


# --- demonstration report ---------------------------------------------------------------------

def test_the_demo_is_built_by_the_real_engine_from_synthetic_documents_without_any_stored_data():
    case = demo.build()
    assert case.id == 0 and case.region == "flanders" and {d.doc_type for d in case.documents} == {"deed", "epc", "asbestos", "electrical"}
    ids = {f.rule_id for f in case.findings}
    assert {"X-SURFACE", "ASB-PRESENT", "ELEC-NONCONFORM", "URB-EXT-NOPERMIT", "EPC-POOR"} <= ids
    assert all(s["filename"].endswith("-demo.pdf") for f in case.findings for s in f.sources)
    from sqlalchemy import select
    from app.models import Case, SessionLocal
    with SessionLocal() as db:
        assert db.scalars(select(Case).where(Case.title == case.title)).all() == []  # never persisted


@pytest.mark.parametrize("lang", LANGS)
def test_the_demo_page_is_public_translated_and_complete(lang):
    r = anon(lang).get("/demo")
    assert r.status_code == 200 and "content-security-policy" in r.headers
    body = page_text(r)
    for key in ("demo.title", "demo.intro", "demo.findings", "demo.limits", "summary.title", "reno.title"):
        assert CATALOGS[lang][key] in body, (lang, key)
    import re
    visible = re.sub(r"<style.*?</style>|<script.*?</script>", "", r.text, flags=re.S)
    assert "{" not in visible
    shown_keys = [k for k in CATALOGS[lang] if k.startswith(("demo.", "summary.", "reno.", "kind.", "rules.", "severity.")) and f">{k}<" in visible or f" {k} " in visible]
    assert shown_keys == []  # no missing translation key leaked into the page
    assert 'href="/demo/report.pdf"' in r.text and CATALOGS[lang]["kind.explain.inference"] in body


def test_the_demo_pdf_opens_with_the_executive_summary_and_the_reserve():
    r = anon("en").get("/demo/report.pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    first = " ".join(PdfReader(io.BytesIO(r.content)).pages[0].extract_text().split())
    assert "Executive summary" in first and "Important reservation" in first and "Action plan" in first


def test_the_demo_is_linked_from_landing_and_pricing():
    for page in ("/", "/pricing"):
        assert 'href="/demo"' in anon().get(page).text


# --- severity and nature are explained ----------------------------------------------------------

def test_every_nature_has_an_explanation_in_every_language_and_it_is_shown_on_findings():
    for lang in LANGS:
        for kind in ("fact", "inference", "risk", "action"):
            assert CATALOGS[lang][f"kind.explain.{kind}"]
    c = new_client("explain@x.be")
    cid = upload_and_analyze(c, [("akte.txt", DEED), ("epc.txt", EPC)])
    body = page_text(c.get(f"/cases/{cid}"))
    assert CATALOGS["fr"]["kind.explain.inference"] in body and CATALOGS["fr"]["severity.explain"] in __import__("html").unescape(c.get(f"/cases/{cid}").text)


def test_the_landing_example_states_it_is_an_inference_not_a_proof():
    body = page_text(anon("en").get("/"))
    assert CATALOGS["en"]["kind.explain.inference"] in body and CATALOGS["en"]["severity.explain"] in body


# --- region scope is visible --------------------------------------------------------------------

@pytest.mark.parametrize("lang", LANGS)
def test_the_flanders_scope_is_stated_near_the_first_button_and_on_pricing(lang):
    assert CATALOGS[lang]["landing.region_note"] in page_text(anon(lang).get("/"))
    assert CATALOGS[lang]["landing.region_note"] in page_text(anon(lang).get("/pricing"))


# --- unvalidated rules are flagged until a professional validates them ------------------------------

def test_rules_are_flagged_as_being_validated_until_the_flag_is_set(monkeypatch):
    c = new_client("validated@x.be")
    cid = upload_and_analyze(c, [("akte.txt", DEED), ("asbest.txt", ASB), ("keuring.txt", ELEC)])
    assert CATALOGS["fr"]["rules.unvalidated"] in page_text(c.get(f"/cases/{cid}"))
    assert CATALOGS["fr"]["rules.unvalidated"] in page_text(anon("fr").get("/demo"))
    pdf_first = lambda: " ".join(PdfReader(io.BytesIO(c.get(f"/cases/{cid}/report.pdf").content)).pages[0].extract_text().split())
    assert "en cours de validation" in pdf_first()
    monkeypatch.setattr(config, "RULES_VALIDATED", True)
    assert CATALOGS["fr"]["rules.unvalidated"] not in page_text(c.get(f"/cases/{cid}"))
    assert "en cours de validation" not in pdf_first()


def test_the_rule_register_lists_every_rule_and_is_up_to_date():
    from pathlib import Path
    doc = Path("docs/REGLES.md").read_text(encoding="utf-8")
    missing = [r for r in RULE_IDS if f"`{r}`" not in doc]
    assert not missing, f"docs/REGLES.md is stale, run: python -m app.rules_doc ({missing})"
