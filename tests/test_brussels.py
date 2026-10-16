"""Brussels-Capital: a coherent fictional dossier stays quiet, a problematic one raises the expected findings."""
from app import regions
from app.rules import run_rules
from tests.brussels_fixtures import COHERENT, PROBLEM, URBANISM_BAD
from tests.test_property_intelligence import docs


def _run(pack):
    views = docs(*pack.items())
    return views, {f.rule_id: f for f in run_rules(views)}


def test_all_documents_are_classified_and_region_is_brussels():
    views, found = _run(COHERENT)
    assert [v.doc_type for v in views] == ["deed", "epc", "electrical", "soil", "urbanism", "copro"]
    assert regions.detect(views)["code"] == "brussels" and found["REG-PRELIM"].params["variant"] == "brussels"


def test_coherent_dossier_has_no_missing_document_and_no_high_finding():
    _, found = _run(COHERENT)
    assert not [r for r in found if r.startswith("DOC-")]
    assert "DOC-ASBESTOS" not in found
    assert not [r for r, f in found.items() if f.severity == "high"]
    assert "X-SURFACE" not in found and "REG-CONFLICT" not in found


def test_french_values_are_extracted_correctly():
    views, _ = _run(COHERENT)
    epc = next(v for v in views if v.doc_type == "epc").fields
    assert epc["epc_label"]["value"] == "E" and epc["epc_score"]["value"] == 310 and epc["epc_valid_until"]["value"] == "2035-06-01"
    urb = next(v for v in views if v.doc_type == "urbanism").fields
    assert urb["planning_zone"]["value"] == "zone d'habitation" and urb["infraction"]["value"] is False
    copro = next(v for v in views if v.doc_type == "copro").fields
    assert copro["reserve_eur"]["value"] == 18500 and copro["monthly_charges_eur"]["value"] == 210


def test_problematic_dossier_raises_the_expected_findings():
    _, found = _run(PROBLEM)
    for rid in ("EPC-POOR", "ELEC-NONCONFORM", "X-SURFACE", "URB-INFRACTION", "URB-HERITAGE", "COPRO-DISPUTE", "COPRO-ARREARS"):
        assert rid in found, rid
    assert found["EPC-POOR"].severity == "high"
    assert "EPC-LABEL-MISMATCH" not in found  # the Flemish label/score check does not apply in Brussels


def test_missing_urbanism_document_is_reported_in_brussels():
    pack = {k: v for k, v in COHERENT.items() if "urbanistiques" not in k}
    _, found = _run(pack)
    assert "DOC-URBANISM" in found


def test_urbanism_is_not_required_in_flanders():
    from tests.fixtures import DEED, EPC
    from tests.test_property_intelligence import ids
    assert "DOC-URBANISM" not in ids(docs(("akte.pdf", DEED), ("epc.pdf", EPC)))


def test_end_to_end_problematic_dossier_through_the_app_and_pdf():
    from tests.helpers import new_client, page_text
    from tests.test_property_intelligence import upload_and_analyze
    c = new_client("brussels-e2e@example.com")
    cid = upload_and_analyze(c, [(n.replace(".pdf", ".txt"), t) for n, t in PROBLEM.items()])
    body = page_text(c.get(f"/cases/{cid}"))
    assert "Bruxelles" in body and "Infraction urbanistique" in body and "inventaire du patrimoine" in body
    r = c.get(f"/cases/{cid}/report.pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
