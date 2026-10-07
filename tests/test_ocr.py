import re

import pytest
from fastapi.testclient import TestClient

from app import ocr
from app.ingest import extract_pages
from app.main import app
from tests.fixtures import ASB, DEED, ELEC, EPC
from tests.scan import png, scanned_pdf

needs_ocr = pytest.mark.skipif(not (ocr.available() and ocr.pdf_renderer_available()), reason="tesseract/pdftoppm not installed")


@needs_ocr
@pytest.mark.parametrize("kw", [{}, {"noise": 0.01, "rotate": 1.2}])
def test_scanned_pdf_is_read(tmp_path, kw):
    p = tmp_path / "epc.pdf"
    p.write_bytes(scanned_pdf([EPC], **kw))
    res = extract_pages(p)
    assert res.ocr_pages and res.ocr_pages[0]["confidence"] > 75
    assert "kWh/m²" in res.pages[0] and "20240101-0001234" in res.pages[0]


@needs_ocr
def test_image_upload_is_read(tmp_path):
    p = tmp_path / "scan.png"
    p.write_bytes(png(ASB))
    assert "asbest" in extract_pages(p).pages[0].lower()


@needs_ocr
def test_mixed_text_and_scanned_pages(tmp_path):
    from tests.fixtures import pdf
    from pypdf import PdfReader, PdfWriter
    a, b = tmp_path / "a.pdf", tmp_path / "b.pdf"
    a.write_bytes(pdf(DEED)); b.write_bytes(scanned_pdf([EPC]))
    w = PdfWriter()
    for f in (a, b):
        for pg in PdfReader(str(f)).pages:
            w.add_page(pg)
    out = tmp_path / "mix.pdf"
    w.write(str(out))
    res = extract_pages(out)
    assert [o["page"] for o in res.ocr_pages] == [2]
    assert "VERKOOPAKTE" in res.pages[0] and "Energieprestatiecertificaat" in res.pages[1]


@needs_ocr
def test_scanned_dossier_end_to_end():
    c = TestClient(app)
    c.post("/register", data={"org_name": "Scan", "email": "scan@x.be", "password": "supersecret12", "accept_terms": "1"})
    cid = int(re.search(r"/cases/(\d+)", c.post("/cases", data={"title": "Scan"}, follow_redirects=False).headers["location"]).group(1))
    files = [("files", (n, scanned_pdf([t], noise=0.01, rotate=1.0), "application/pdf")) for n, t in
             [("akte.pdf", DEED), ("epc.pdf", EPC), ("asbest.pdf", ASB)]]
    files.append(("files", ("keuring.png", png(ELEC), "image/png")))
    assert c.post(f"/cases/{cid}/documents", files=files, follow_redirects=False).status_code == 303
    c.post(f"/cases/{cid}/analyze")
    data = c.get(f"/api/cases/{cid}").json()
    ids = {f["rule"] for f in data["findings"]}
    assert {"X-SURFACE", "ASB-PRESENT", "ELEC-NONCONFORM", "DOC-OCR-USED"} <= ids
    assert {d["type"] for d in data["documents"]} == {"deed", "epc", "asbestos", "electrical"}


def test_scan_without_ocr_is_flagged(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, "available", lambda: False)
    p = tmp_path / "s.pdf"
    p.write_bytes(scanned_pdf([EPC]))
    res = extract_pages(p)
    assert not res.ocr_pages and res.warnings
    from app.rules import DocView, run_rules
    ids = [f.rule_id for f in run_rules([DocView(1, "s.pdf", "unknown", res.pages, {}, res.ocr_pages, res.warnings)])]
    assert "DOC-OCR" in ids
