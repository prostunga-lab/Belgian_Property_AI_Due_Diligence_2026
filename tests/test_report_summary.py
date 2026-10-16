"""The PDF opens with an executive summary (page 1) that carries the action-plan table and the professional-advice reserve."""
import io

import pytest
from pypdf import PdfReader

from tests.fixtures import ASB, DEED, ELEC, EPC
from tests.helpers import new_client
from tests.test_property_intelligence import upload_and_analyze

RESERVE = {"fr": "Réserve importante", "nl": "Belangrijk voorbehoud", "en": "Important reservation"}
TITLE = {"fr": "Synthèse (executive summary)", "nl": "Samenvatting (executive summary)", "en": "Executive summary"}
DETAIL = {"fr": "Rapport détaillé", "nl": "Gedetailleerd rapport", "en": "Detailed report"}
TABLE = {"fr": ("Travaux", "Priorité", "Estimation"), "nl": ("Werken", "Prioriteit", "Raming"), "en": ("Works", "Priority", "Estimate")}


def pages(c, cid, lang):
    c.cookies.set("lang", lang)
    r = c.get(f"/cases/{cid}/report.pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    return [" ".join(p.extract_text().split()) for p in PdfReader(io.BytesIO(r.content)).pages]


@pytest.fixture(scope="module")
def case():
    c = new_client("exec-summary@x.be")
    return c, upload_and_analyze(c, [("akte.txt", DEED), ("epc.txt", EPC), ("asbest.txt", ASB), ("keuring.txt", ELEC)])


@pytest.mark.parametrize("lang", ["fr", "nl", "en"])
def test_first_page_is_an_executive_summary_with_the_action_plan_and_the_reserve(case, lang):
    p = pages(*case, lang)
    first = p[0]
    assert TITLE[lang] in first and RESERVE[lang] in first
    assert all(word in first for word in TABLE[lang])  # the action-plan table is on page 1
    assert "k" in first and "/100" in first  # score and compact estimates
    assert len(p) >= 2 and DETAIL[lang] in p[1] and DETAIL[lang] not in first  # the summary fits one page, details start on the next


def test_reserve_comes_before_any_finding_and_repeats_at_the_end(case):
    p = pages(*case, "en")
    first = p[0]
    assert first.index("Important reservation") < first.index("Key points") < first.index("Action plan")
    assert "does not constitute" in p[-1] or "not legal" in p[-1] or "qualified professional" in p[-1]


def test_key_findings_and_questions_are_summarised_on_page_one(case):
    first = pages(*case, "en")[0]
    assert "[HIGH]" in first and "To ask or check before signing" in first
    assert "Asbestos" in first or "asbestos" in first


def test_a_clean_dossier_still_gets_a_summary_without_an_action_plan():
    c = new_client("exec-clean@x.be")
    clean_epc = "Energieprestatiecertificaat (EPC)\nAdres: Kerkstraat 12, 9000 Gent\nEnergielabel: B\nEnergiescore 150 kWh/m²\nGeldig tot 01/01/2034\nBouwjaar 1975\n"
    cid = upload_and_analyze(c, [("akte.txt", DEED), ("epc.txt", clean_epc)])
    first = pages(c, cid, "en")[0]
    assert "Executive summary" in first and "Important reservation" in first and "Action plan" not in first


@pytest.mark.parametrize("lang,label", [("fr", "Note de risque du bien"), ("nl", "Risicoscore van het pand"), ("en", "Property Risk Score")])
def test_the_score_label_is_translated_on_the_page_and_in_the_pdf(case, lang, label):
    c, cid = case
    assert label in pages(c, cid, lang)[0]
    from tests.helpers import page_text
    c.cookies.set("lang", lang)
    assert label in page_text(c.get(f"/cases/{cid}"))
