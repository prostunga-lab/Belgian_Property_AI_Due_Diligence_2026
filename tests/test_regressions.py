"""Defects found while testing with realistic documents; each test pins one."""
from app.classify import classify
from app.extract import extract
from app.ocr import normalize
from app.rules import DocView, run_rules
from tests.fixtures import DEED, EPC


def view(i, name, text):
    t, _ = classify([text], name)
    return DocView(i, name, t, [text], extract(t, [text]))


def test_buyer_not_confused_with_seller():
    f = extract("deed", [DEED])
    assert f["seller"]["value"] == "Jan Janssens" and f["buyer"]["value"] == "Els Maes"


def test_negated_asbestos_is_not_a_finding():
    for txt in ["Asbestattest\nEr werd geen asbest aangetroffen.", "Attestation amiante\nPas de matériaux contenant de l'amiante."]:
        assert extract("asbestos", [txt])["asbestos_present"]["value"] is False
    pos = extract("asbestos", ["Asbestattest\nEr werd asbest aangetroffen in de dakbedekking."])
    assert pos["asbestos_present"]["value"] is True


def test_asbestos_positive_wins_over_other_negative_sentence():
    txt = "Asbestattest\nGeen asbest in de kelder.\nAsbesthoudende materialen aanwezig op het dak."
    assert extract("asbestos", [txt])["asbestos_present"]["value"] is True


def test_french_address_and_class():
    f = extract("epc", ["Certificat PEB\nAdresse : Rue de la Loi 45, 1000 Bruxelles\nClasse : D\nConsommation 340 kWh/m²"])
    assert f["address"]["value"].startswith("Rue de la Loi 45") and f["epc_label"]["value"] == "D"


def test_address_mismatch_is_one_finding():
    docs = [view(1, "akte.pdf", "VERKOOPAKTE\nVerleden op 12/03/2026 notaris\nPand gelegen te Kerkstraat 12, 9000 Gent."),
            view(2, "epc.pdf", "Energieprestatiecertificaat\nAdres: Dorpsstraat 5, 2000 Antwerpen"),
            view(3, "asbest.pdf", "Asbestattest\nAdres: Molenweg 9, 3000 Leuven")]
    assert [f.rule_id for f in run_rules(docs)].count("X-ADDRESS") == 1


def test_ocr_unit_normalisation():
    assert normalize("oppervlakte van 185 m?.") == "oppervlakte van 185 m²."
    assert normalize("Energiescore 430 kWh/m?\nx") == "Energiescore 430 kWh/m²\nx"
    assert normalize("een m2 ding") == "een m2 ding"  # untouched when not clearly a mangled square
    assert normalize("kWh/m²") == "kWh/m²"


def test_clean_dossier_has_no_false_positives():
    docs = [
        view(1, "akte.pdf", "VERKOOPAKTE\nVerleden op 03/04/2026 notaris Dupont\nVerkoper: Marie Lambert\nKoper: Paul Martin\n"
                            "Pand gelegen te Kerkstraat 12, 9000 Gent\nBewoonbare oppervlakte van 120 m².\n"
                            "Stedenbouwkundige vergunning 1999. Vergunningenregister bijgevoegd.\nKadastraal: sectie B nummer 45/A\nBouwjaar 1985"),
        view(2, "epc.pdf", "Energieprestatiecertificaat\nAdres: Kerkstraat 12, 9000 Gent\nEnergielabel: B\nEnergiescore 180 kWh/m²\n"
                           "Bruikbare vloeroppervlakte 120 m²\nGeldig tot 15/06/2033\nBouwjaar 1985"),
        view(3, "asbest.pdf", "Asbestattest\nAdres: Kerkstraat 12, 9000 Gent\nDatum: 02/02/2026\nEr werd geen asbest aangetroffen."),
        view(4, "keuring.pdf", "Keuringsverslag elektrische installatie\nAdres: Kerkstraat 12, 9000 Gent\nDatum van keuring: 10/10/2024\nDe installatie is conform aan het AREI."),
    ]
    bad = [f.rule_id for f in run_rules(docs) if f.severity in ("medium", "high")]
    assert bad == []
