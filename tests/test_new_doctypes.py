from app.classify import classify
from app.extract import extract, parse_number
from app.rules import DocView, run_rules
from tests.fixtures import DEED, EPC

CAD = """Kadastraal uittreksel
Perceel: Kerkstraat 12, 9000 Gent
Sectie A nummer 123/B
Oppervlakte 512 m²
Kadastraal inkomen 1.250 €
Bouwjaar 1975
Datum: 01/03/2026"""
SOIL_OK = """Bodemattest
Perceel Kerkstraat 12, 9000 Gent, sectie A nummer 123/B
Datum: 02/03/2026
Voor dit perceel is geen bodemverontreiniging gekend."""
SOIL_BAD = """Bodemattest
Kerkstraat 12, 9000 Gent
Op het perceel werd bodemverontreiniging vastgesteld. Een bodemsanering is vereist."""


def view(i, name, text):
    t, _ = classify([text], name)
    return DocView(i, name, t, [text], extract(t, [text]))


def test_classification_and_fields():
    cad, ok, bad = view(1, "kadaster.pdf", CAD), view(2, "bodem.pdf", SOIL_OK), view(3, "bodem2.pdf", SOIL_BAD)
    assert [cad.doc_type, ok.doc_type, bad.doc_type] == ["cadastre", "soil", "soil"]
    assert cad.fields["cadastral_ref"]["value"] == "A 123/B"
    assert cad.fields["plot_m2"]["value"] == 512 and cad.fields["cadastral_income"]["value"] == 1250
    assert ok.fields["soil_pollution_mentioned"]["value"] is False
    assert bad.fields["soil_pollution_mentioned"]["value"] is True


def test_belgian_number_formats():
    assert parse_number("1.250") == 1250 and parse_number("1.250,5") == 1250.5 and parse_number("185,5") == 185.5
    assert parse_number("1 250") == 1250 and parse_number("240") == 240


def test_deed_is_not_mistaken_for_cadastre():
    t, _ = classify([DEED + "\nKadastraal inkomen 1.250 €"], "akte.pdf")
    assert t == "deed"


def test_soil_pollution_is_high_risk_and_clear_is_info():
    ids = {f.rule_id: f for f in run_rules([view(1, "b.pdf", SOIL_BAD)])}
    assert ids["SOIL-POLLUTION"].severity == "high" and ids["SOIL-POLLUTION"].sources[0]["excerpt"]
    assert "SOIL-CLEAR" in {f.rule_id for f in run_rules([view(1, "b.pdf", SOIL_OK)])}


def test_missing_soil_attest_is_flagged():
    assert "DOC-SOIL" in {f.rule_id for f in run_rules([view(1, "akte.pdf", DEED)])}


def test_plot_area_never_compared_with_dwelling_surface():
    ids = {f.rule_id for f in run_rules([view(1, "akte.pdf", DEED), view(2, "epc.pdf", EPC), view(3, "kad.pdf", CAD)])}
    assert "X-SURFACE" in ids  # 185 vs 240 from deed/EPC only
    surf = [f for f in run_rules([view(1, "akte.pdf", DEED), view(3, "kad.pdf", CAD)]) if f.rule_id == "X-SURFACE"]
    assert surf == []  # 185 m² dwelling vs 512 m² plot must NOT be flagged


def test_cadastre_reference_mismatch_with_deed():
    other = CAD.replace("123/B", "999/Z")
    ids = {f.rule_id for f in run_rules([view(1, "akte.pdf", DEED), view(2, "kad.pdf", other)])}
    assert "X-CADASTRE" in ids
    assert "X-CADASTRE" not in {f.rule_id for f in run_rules([view(1, "akte.pdf", DEED), view(2, "kad.pdf", CAD)])}


def test_unbuilt_plot_vs_building():
    unbuilt = CAD.replace("Bouwjaar 1975", "Het perceel is onbebouwd.")
    ids = {f.rule_id for f in run_rules([view(1, "epc.pdf", EPC), view(2, "kad.pdf", unbuilt)])}
    assert "CAD-UNBUILT" in ids
