"""Indicative renovation plan: derived from findings, honest about what cannot be priced, configurable, in three languages."""
import json

import pytest
from fastapi.testclient import TestClient

from app import renovation
from app.i18n import LANGS
from app.main import app
from app.rules import run_rules
from tests.fixtures import ASB, DEED, ELEC, EPC
from tests.helpers import new_client, page_text
from tests.test_property_intelligence import PLAN, URBANISM, docs, upload_and_analyze


def plan(*items, lang="en"):
    views = docs(*items)
    return renovation.build(run_rules(views), views, lang), views


def ids(p):
    return {i["id"]: i for ph in p["phases"] for i in ph["items"]}


def test_a_full_dossier_yields_a_phased_plan_with_a_cumulative_budget():
    p, _ = plan(("akte.pdf", DEED), ("epc.pdf", EPC), ("asbest.pdf", ASB), ("keuring.pdf", ELEC))
    items = ids(p)
    assert {"asbestos_inventory", "asbestos_removal", "electrical_compliance", "energy_roof", "energy_glazing", "energy_heating"} <= set(items)
    assert [ph["id"] for ph in p["phases"]] == ["before_signature", "safety_compliance", "energy"]  # chronological
    assert p["total_low"] == sum(i["low"] for i in items.values() if i["low"] is not None)
    assert p["total_high"] > p["total_low"] > 0 and "–" in p["total"]


def test_flat_ranges_and_per_m2_scaling_use_the_documents_floor_area():
    p, _ = plan(("akte.pdf", DEED), ("epc.pdf", EPC), ("keuring.pdf", ELEC))
    assert (ids(p)["electrical_compliance"]["low"], ids(p)["electrical_compliance"]["high"]) == (1000, 7000)
    roof = ids(p)["energy_roof"]  # the EPC says 240 m² (it wins over the deed's 185 m²); label E: 20-50 EUR/m²
    assert (roof["low"], roof["high"]) == (4800, 12000) and "240" in roof["basis"] and roof["confidence"] == "assumption"
    heating = ids(p)["energy_heating"]
    assert (heating["low"], heating["high"]) == (3000, 8000)  # a flat range: not scaled by the area


def test_without_a_surface_a_flat_range_is_used():
    epc = "\n".join(l for l in EPC.splitlines() if "oppervlakte" not in l)
    roof = ids(plan(("epc.pdf", epc))[0])["energy_roof"]
    assert (roof["low"], roof["high"]) == (3000, 8000)


def test_items_without_an_honest_estimate_are_listed_without_a_number():
    p, _ = plan(("akte.pdf", DEED), ("epc.pdf", EPC), ("uittreksel.pdf", URBANISM))
    reg = ids(p)["permit_regularisation"]
    assert reg["low"] is None and reg["high"] is None and reg["confidence"] == "none" and p["unestimated"] >= 1
    assert p["total_low"] == sum(i["low"] for i in ids(p).values() if i["low"] is not None)  # never counts the unpriced items
    assert reg["cost"] == "to be priced" and "professional" in reg["cost_full"]


def test_nothing_to_renovate_gives_an_empty_plan():
    clean = DEED, "Energieprestatiecertificaat (EPC)\nAdres: Kerkstraat 12, 9000 Gent\nEnergielabel: B\nEnergiescore 150 kWh/m²\nGeldig tot 01/01/2034\nBouwjaar 1975\n"
    p, _ = plan(("akte.pdf", clean[0]), ("epc.pdf", clean[1]))
    assert not any(i in ids(p) for i in ("energy_roof", "energy_glazing", "energy_heating", "asbestos_removal", "electrical_compliance"))


def test_dismissed_findings_are_not_budgeted(tmp_path):
    c = new_client("reno-dismiss@x.be")
    cid = upload_and_analyze(c, [("akte.txt", DEED), ("keuring.txt", ELEC)])
    from app.models import Case, SessionLocal
    from app.services import case_payload
    with SessionLocal() as db:
        case = db.get(Case, cid)
        assert any(i["id"] == "electrical_compliance" for ph in case_payload(case, "en")["renovation"]["phases"] for i in ph["items"])
        for f in case.findings:
            f.review_status = "dismissed"
        db.flush()
        assert case_payload(case, "en")["renovation"]["rows"] == []
        db.rollback()


def test_cost_overrides_come_from_a_json_file_and_a_broken_file_is_ignored(tmp_path, monkeypatch):
    f = tmp_path / "costs.json"
    f.write_text(json.dumps({"electrical_compliance": {"low": 2000, "high": 9000, "evil": 1}, "unknown_item": {"low": 1}}))
    monkeypatch.setenv("RENOVATION_COST_FILE", str(f))
    c = renovation.costs()["electrical_compliance"]
    assert (c["low"], c["high"]) == (2000, 9000) and "evil" not in c and "unknown_item" not in renovation.costs()
    f.write_text("not json")
    assert renovation.costs()["electrical_compliance"]["low"] == 1000
    monkeypatch.setenv("RENOVATION_COST_FILE", str(tmp_path / "missing.json"))
    assert renovation.costs()["electrical_compliance"]["low"] == 1000


def test_every_item_has_text_in_every_language():
    views = docs(("akte.pdf", DEED), ("epc.pdf", EPC.replace("Energielabel: E", "Energielabel: F")), ("asbest.pdf", ASB), ("keuring.pdf", ELEC), ("u.pdf", URBANISM))
    findings = run_rules(views)
    for lang in LANGS:
        p = renovation.build(findings, views, lang)
        texts = [v for ph in p["phases"] for it in ph["items"] for k, v in it.items() if k in ("title", "what", "note", "cost", "basis", "confidence_label")]
        texts += [p["total"], p["unestimated_text"]] + [ph["label"] for ph in p["phases"]]
        assert all("reno." not in x and "{" not in x for x in texts), lang
        assert p["phases"] and all(i["title"] and i["what"] for ph in p["phases"] for i in ph["items"])
    for key in renovation.COSTS:
        for lang in LANGS:
            from app import i18n
            assert i18n.has(f"reno.item.{key}.title", lang) and i18n.has(f"reno.item.{key}.what", lang)


def test_case_page_and_pdf_show_the_plan_with_its_disclaimer():
    c = new_client("reno-page@x.be")
    cid = upload_and_analyze(c, [("akte.txt", DEED), ("epc.txt", EPC), ("asbest.txt", ASB), ("keuring.txt", ELEC)])
    for lang, title, warn in (("fr", "Plan de rénovation", "pas un devis"), ("nl", "Renovatieplan", "geen offerte"), ("en", "Renovation plan", "not a quote")):
        c.cookies.set("lang", lang)
        body = page_text(c.get(f"/cases/{cid}"))
        assert title in body and warn in body
    assert c.get(f"/cases/{cid}/report.pdf").content.startswith(b"%PDF")


def test_table_rows_are_sorted_by_priority_with_compact_estimates():
    p, _ = plan(("akte.pdf", DEED), ("epc.pdf", EPC), ("asbest.pdf", ASB), ("keuring.pdf", ELEC), lang="fr")
    order = [r["priority"] for r in p["rows"]]
    assert order == sorted(order, key=["high", "medium", "low"].index) and order[0] == "high"
    by = {r["id"]: r for r in p["rows"]}
    assert by["asbestos_removal"]["priority"] == "high" and by["electrical_compliance"]["cost"] == "1–7 k€"  # compact, French style
    assert by["asbestos_inventory"]["cost"] == "150 – 600 €"  # below a thousand: full numbers
    assert p["total"].endswith("k€")


@pytest.mark.parametrize("lang,expected", [("fr", "1–7 k€"), ("nl", "1–7 k€"), ("en", "€1–7k")])
def test_compact_ranges_follow_each_languages_style(lang, expected):
    assert renovation.compact(1000, 7000, lang) == expected
    assert renovation.compact(12000, 31200, "fr") == "12–31,2 k€" and renovation.compact(12000, 31200, "en") == "€12–31.2k"
    assert renovation.compact(None, None, "en") == "to be priced"


def test_case_page_shows_the_table_with_priority_dots_and_text():
    c = new_client("reno-table@x.be")
    cid = upload_and_analyze(c, [("akte.txt", DEED), ("epc.txt", EPC), ("asbest.txt", ASB), ("keuring.txt", ELEC)])
    html = c.get(f"/cases/{cid}").text.split('id="renovation"')[1].split("</table>")[0]
    assert "Travaux" in html and "Priorité" in html and "Estimation" in html and 'class="dot high"' in html and "Élevée" in html  # text, not colour only
    assert "Isolation de la toiture" in html and "Chauffage" in html and "Vitrage" in html
