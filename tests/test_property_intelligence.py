"""Summary, timeline, region detection and the new document types (plans, invoices, planning info, co-ownership, photos)."""
import datetime as dt
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import regions, summary
from app.classify import classify
from app.extract import extract
from app.i18n import LANGS
from app.main import app
from app.rules import DocView, run_rules
from tests.fixtures import ASB, DEED, ELEC, EPC, pdf
from tests.helpers import new_case, new_client, page_text

INVOICE_ROOF = """Factuur nr 2026-044
Factuurdatum: 12/06/2026
Vervanging van het dak en isolatie
Totaal incl. btw: € 18.450,00
"""
INVOICE_ELEC = """Factuur nr 7
Factuurdatum: 01/02/2026
Vernieuwing elektrische installatie
Totaal incl. btw: € 4.200,00
"""
INVOICE_OLD = """Facture n° 1
Date de facture: 03/03/1960
Travaux de toiture
Total TTC: € 900,00
"""
PLAN = """Grondplan gelijkvloers schaal 1/100
Adres: Kerkstraat 12, 9000 Gent
Totale oppervlakte: 240 m²
Datum: 05/05/2020
"""
URBANISM = """Stedenbouwkundig uittreksel
Datum: 01/03/2026
Kerkstraat 12, 9000 Gent
Het perceel ligt in woongebied. Er is een proces-verbaal opgesteld in 2015. Het goed is overstromingsgevoelig.
"""
COPRO = """Mede-eigendom Residentie Zeezicht
Reservefonds: 12.500,00 EUR
Algemene vergadering van 15/03/2023
Er loopt een geschil met de aannemer. Achterstallige kosten van de eigenaar: 450 EUR.
"""
BRUSSELS_DEED = DEED.replace("Kerkstraat 12, 9000 Gent", "Rue Neuve 12, 1000 Bruxelles")


def docs(*items, ):
    out = []
    for i, (name, text) in enumerate(items, 1):
        t, _ = classify([text], name)
        out.append(DocView(i, name, t, [text], extract(t, [text])))
    return out


def ids(views, ctx=None):
    return {f.rule_id for f in run_rules(views, ctx)}


# --- regions --------------------------------------------------------------------------------

@pytest.mark.parametrize("pc,region", [(1000, "brussels"), (1210, "brussels"), (1348, "wallonia"), (1500, "flanders"), (2000, "flanders"),
                                       (3500, "flanders"), (4000, "wallonia"), (5000, "wallonia"), (6000, "wallonia"), (7000, "wallonia"),
                                       (8000, "flanders"), (9000, "flanders")])
def test_postcode_ranges(pc, region):
    assert regions.from_postcode(pc) == region


def test_postcode_is_the_last_four_digit_group_of_the_address():
    assert regions.postcode_of("Kerkstraat 1234, 9000 Gent") == 9000
    assert regions.postcode_of("Kerkstraat 12") is None


def test_region_is_detected_from_the_address_with_its_source():
    info = regions.detect(docs(("akte.pdf", DEED)))
    assert info["code"] == "flanders" and info["postcode"] == 9000 and info["source"]["filename"] == "akte.pdf" and not info["conflict"]


def test_flanders_keeps_the_flemish_rules_and_no_preliminary_notice():
    found = ids(docs(("akte.pdf", DEED), ("epc.pdf", EPC)))
    assert "DOC-ASBESTOS" in found and "REG-PRELIM" not in found and "REG-UNKNOWN" not in found


def test_brussels_does_not_require_an_asbestos_attest_but_warns_the_rules_are_preliminary():
    found = ids(docs(("akte.pdf", BRUSSELS_DEED), ("epc.pdf", EPC.replace("Kerkstraat 12, 9000 Gent", "Rue Neuve 12, 1000 Bruxelles"))))
    assert "DOC-ASBESTOS" not in found and "DOC-ELECTRICAL" in found and "DOC-SOIL" in found and "REG-PRELIM" in found
    f = next(f for f in run_rules(docs(("akte.pdf", BRUSSELS_DEED))) if f.rule_id == "REG-PRELIM")
    assert f.params["variant"] == "brussels" and f.sources


def test_unknown_region_defaults_to_flanders_with_an_info_note():
    views = docs(("akte.pdf", DEED.replace("Kerkstraat 12, 9000 Gent", "Kerkstraat 12")))
    found = {f.rule_id: f for f in run_rules(views)}
    assert found["REG-UNKNOWN"].severity == "info" and "DOC-ASBESTOS" in found


def test_documents_in_different_regions_are_reported():
    views = docs(("akte.pdf", DEED), ("epc.pdf", EPC.replace("Kerkstraat 12, 9000 Gent", "Rue Neuve 12, 1000 Bruxelles")))
    assert "REG-CONFLICT" in ids(views)


# --- new document types ---------------------------------------------------------------------

@pytest.mark.parametrize("text,name,expected", [(INVOICE_ROOF, "f.pdf", "invoice"), (PLAN, "p.pdf", "plan"), (URBANISM, "u.pdf", "urbanism"), (COPRO, "c.pdf", "copro")])
def test_new_types_are_recognised(text, name, expected):
    assert classify([text], name)[0] == expected


def test_money_needs_a_currency_sign_and_negations_are_respected():
    f = extract("copro", ["Er is geen geschil. Reservefonds: 12.500,00 EUR. Vergadering 2023."])
    assert f["reserve_eur"]["value"] == 12500 and f["dispute"]["value"] is False
    assert "amount_eur" not in extract("invoice", ["Factuur 2026\nFactuurdatum: 01/01/2026\nTotaal 2026"])


def test_user_example_three_different_surfaces_across_deed_epc_and_plan():
    views = docs(("akte.pdf", DEED.replace("185", "210")), ("epc.pdf", EPC.replace("240", "173")), ("plan.pdf", PLAN))
    surfaces = [f for f in run_rules(views) if f.rule_id == "X-SURFACE"]
    assert len(surfaces) == 3  # every pair differs: 210/173, 210/240, 173/240


def test_energy_works_after_the_epc_and_electrical_works_after_the_inspection():
    epc = EPC.replace("Geldig tot 01/01/2034", "Datum van opmaak 01/01/2024\nGeldig tot 01/01/2034")
    found = ids(docs(("epc.pdf", epc), ("dak.pdf", INVOICE_ROOF), ("keuring.pdf", ELEC), ("elek.pdf", INVOICE_ELEC)))
    assert {"WORK-EPC-STALE", "WORK-ELEC-STALE"} <= found


def test_works_before_the_building_existed():
    assert "X-WORKS-BEFORE-BUILD" in ids(docs(("akte.pdf", DEED), ("oud.pdf", INVOICE_OLD)))


def test_planning_information_flags_infringement_and_flood_risk_and_replaces_missing_info():
    found = ids(docs(("akte.pdf", DEED), ("uittreksel.pdf", URBANISM)))
    assert {"URB-INFRACTION", "URB-FLOOD"} <= found and "URB-NO-INFO" not in found
    assert "URB-NO-INFO" in ids(docs(("akte.pdf", DEED)))
    assert "URB-EXT-NOPERMIT" not in ids(docs(("akte.pdf", DEED), ("epc.pdf", EPC), ("uittreksel.pdf", URBANISM)))


def test_coownership_findings():
    assert {"COPRO-DISPUTE", "COPRO-ARREARS", "COPRO-OLD-AG"} <= ids(docs(("copro.pdf", COPRO)))


# --- summary and timeline -------------------------------------------------------------------

def test_summary_headline_and_items_come_from_extracted_fields():
    s = summary.build(docs(("akte.pdf", DEED), ("epc.pdf", EPC), ("asbest.pdf", ASB), ("keuring.pdf", ELEC)), "fr")
    keys = {i["key"] for i in s["items"]}
    assert {"address", "region", "built", "surface", "epc", "electrical", "asbestos", "extension"} <= keys
    assert "construit en 1975" in s["headline"] and "PEB E" in s["headline"] and "non conforme" in s["headline"] and "amiante signalé" in s["headline"]
    surface = next(i for i in s["items"] if i["key"] == "surface")
    assert "185 m²" in surface["value"] and "240 m²" in surface["value"] and surface["flag"] == "warn" and len(surface["sources"]) == 2
    assert all(i["sources"] for i in s["items"] if i["key"] != "region")


def test_summary_never_invents_missing_facts():
    s = summary.build(docs(("akte.pdf", DEED)), "en")
    assert {i["key"] for i in s["items"]}.isdisjoint({"epc", "electrical", "asbestos", "soil", "works"})


def test_timeline_is_chronological_and_flags_oddities():
    views = docs(("akte.pdf", DEED), ("epc.pdf", EPC), ("keuring.pdf", ELEC), ("oud.pdf", INVOICE_OLD))
    ev = summary.timeline(views, "en", today=dt.date(2026, 6, 1))
    dates = [e["date"] for e in ev]
    assert dates == sorted(dates, key=lambda d: (d if len(d) > 4 else d + "-01-01")) and [e["kind"] for e in ev[:2]] == ["works", "construction"] and ev[1]["date"] == "1975"
    flagged = {e["kind"]: e["flags"] for e in ev}
    assert flagged["works"] == ["before_build"] and flagged["epc_expires"] == ["upcoming"]
    assert summary.timeline(views, "en", today=dt.date(2040, 1, 1))[-1]["flags"] == ["expired"]
    assert all(e["filename"] and e["page"] and e["excerpt"] for e in ev)


def test_timeline_and_summary_texts_exist_in_every_language():
    views = docs(("akte.pdf", DEED), ("epc.pdf", EPC), ("asbest.pdf", ASB), ("keuring.pdf", ELEC), ("dak.pdf", INVOICE_ROOF), ("u.pdf", URBANISM), ("c.pdf", COPRO))
    for lang in LANGS:
        blob = str(summary.build(views, lang)) + str(summary.timeline(views, lang))
        assert "summary." not in blob and "timeline." not in blob and "region." not in blob, lang


# --- end to end -----------------------------------------------------------------------------

def upload_and_analyze(c, items):
    cid = new_case(c)
    files = [("files", (name, text.encode() if isinstance(text, str) else text, "text/plain" if isinstance(text, str) else "image/png")) for name, text in items]
    assert c.post(f"/cases/{cid}/documents", files=files).status_code in (200, 303)
    assert c.post(f"/cases/{cid}/analyze", follow_redirects=False).status_code == 303
    return cid


def test_case_page_pdf_and_api_show_summary_timeline_and_region():
    c = new_client("intel1@x.be")
    cid = upload_and_analyze(c, [("akte.txt", DEED), ("epc.txt", EPC), ("asbest.txt", ASB), ("dak.txt", INVOICE_ROOF), ("plan.txt", PLAN)])
    for lang, title, tl in (("fr", "Résumé du bien", "Chronologie du bien"), ("nl", "Samenvatting van het pand", "Tijdlijn van het pand"), ("en", "Property summary", "Property timeline")):
        c.cookies.set("lang", lang)
        body = page_text(c.get(f"/cases/{cid}"))
        assert title in body and tl in body and "Kerkstraat 12" in body and "{" not in body.split(title)[1][:600]
    assert c.get(f"/cases/{cid}/report.pdf").content.startswith(b"%PDF")
    data = c.get(f"/cases/{cid}", headers={"accept": "application/json"})
    from app.main import app as _app  # noqa: F401  (payload shape checked via the service)
    from app.models import Case, SessionLocal
    from app.services import case_payload
    with SessionLocal() as db:
        case = db.get(Case, cid)
        payload = case_payload(case, "en")
        assert case.region == "flanders" and payload["summary"]["headline"] and payload["timeline"] and payload["documents"][0]["type"]


def test_photos_are_kept_and_reported_once_not_as_unreadable():
    buf = io.BytesIO()
    Image.new("RGB", (400, 300), (200, 200, 200)).save(buf, "PNG")
    c = new_client("intel2@x.be")
    cid = upload_and_analyze(c, [("akte.txt", DEED), ("voorgevel.png", buf.getvalue())])
    from app.models import Case, SessionLocal
    with SessionLocal() as db:
        case = db.get(Case, cid)
        types = {d.filename: d.doc_type for d in case.documents}
        rule_ids = {f.rule_id for f in case.findings}
    assert types["voorgevel.png"] == "photo" and "DOC-PHOTO" in rule_ids and "DOC-OCR" not in rule_ids and "DOC-UNK" not in rule_ids
