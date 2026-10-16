"""The public promise: a first report in under PROCESSING_PROMISE_MINUTES minutes for a standard complete dossier."""
import re
import time

import pytest

from app import config, ocr
from app.models import Case, SessionLocal
from sqlalchemy import select
from fastapi.testclient import TestClient
from app.main import app
from tests.fixtures import ASB, DEED, ELEC, EPC, pdf
from tests.helpers import new_client, page_text
from tests.scan import scanned_pdf

needs_ocr = pytest.mark.skipif(not (ocr.available() and ocr.pdf_renderer_available()), reason="tesseract/pdftoppm not installed")


def complete_dossier(c, scanned: bool):
    cid = int(c.post("/cases", data={"title": "Promesse"}, follow_redirects=False).headers["location"].rsplit("/", 1)[1])
    files = [("files", ("deed.pdf", pdf(DEED), "application/pdf")), ("files", ("asb.pdf", pdf(ASB), "application/pdf")),
             ("files", ("elec.pdf", pdf(ELEC), "application/pdf"))]
    files.append(("files", ("epc.pdf", scanned_pdf([EPC]) if scanned else pdf(EPC), "application/pdf")))
    assert c.post(f"/cases/{cid}/documents", files=files).status_code in (200, 303)
    return cid


def timed_analysis(email, scanned):
    c = new_client(email)
    cid = complete_dossier(c, scanned)
    t0 = time.perf_counter()
    r = c.post(f"/cases/{cid}/analyze", follow_redirects=False)
    wall = time.perf_counter() - t0
    assert r.status_code == 303
    return c, cid, wall


def test_a_complete_text_dossier_is_analysed_within_the_promise():
    c, cid, wall = timed_analysis("promise-text@x.be", scanned=False)
    assert wall < config.PROCESSING_PROMISE_MINUTES * 60
    with SessionLocal() as db:
        recorded = db.get(Case, cid).analysis_seconds
    assert recorded is not None and 0 < recorded <= wall + 0.5  # measured by the app itself and stored per dossier


@needs_ocr
def test_a_complete_dossier_with_a_scanned_document_is_analysed_within_the_promise():
    c, cid, wall = timed_analysis("promise-scan@x.be", scanned=True)
    assert wall < config.PROCESSING_PROMISE_MINUTES * 60


def test_the_duration_is_shown_on_the_case_page_and_the_promise_on_public_pages():
    c, cid, _ = timed_analysis("promise-show@x.be", scanned=False)
    assert re.search(r"Analyse réalisée en [\d.,]+ s", page_text(c.get(f"/cases/{cid}")))
    for lang, word in (("fr", "2 minutes"), ("nl", "2 minuten"), ("en", "2 minutes")):
        for path in ("/", "/pricing"):
            assert word in page_text(TestClient(app, cookies={"lang": lang}).get(path)), (lang, path)


def test_the_promise_follows_the_configuration(monkeypatch):
    monkeypatch.setattr(config, "PROCESSING_PROMISE_MINUTES", 5)
    assert "5 minutes" in page_text(TestClient(app, cookies={"lang": "en"}).get("/pricing"))
