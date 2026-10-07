import re
from fastapi.testclient import TestClient
from app.main import app
from tests.fixtures import ASB, DEED, ELEC, EPC, pdf

HDR = {"accept": "text/html"}


def register(c, email):
    r = c.post("/register", data={"org_name": "Agence", "email": email, "password": "supersecret12"}, follow_redirects=False)
    assert r.status_code == 303


def test_full_flow_and_tenant_isolation():
    c = TestClient(app)
    register(c, "a@x.be")
    r = c.post("/cases", data={"title": "Kerkstraat 12"}, follow_redirects=False)
    cid = int(re.search(r"/cases/(\d+)", r.headers["location"]).group(1))
    files = [("files", (n, pdf(t), "application/pdf")) for n, t in [("akte.pdf", DEED), ("epc.pdf", EPC), ("asbest.pdf", ASB), ("keuring.pdf", ELEC)]]
    assert c.post(f"/cases/{cid}/documents", files=files, follow_redirects=False).status_code == 303
    assert c.post(f"/cases/{cid}/analyze", follow_redirects=False).status_code == 303
    data = c.get(f"/api/cases/{cid}").json()
    assert data["scores"]["level"] == "high" and data["address"].startswith("Kerkstraat")
    ids = {f["rule"] for f in data["findings"]}
    assert "X-SURFACE" in ids and all(f["sources"] for f in data["findings"] if not f["rule"].startswith("DOC-"))
    fid = data["findings"][0]["id"]
    assert c.post(f"/cases/{cid}/findings/{fid}/review", data={"status": "confirmed"}, follow_redirects=False).status_code == 303
    assert c.post(f"/cases/{cid}/findings/{fid}/comments", data={"body": "Gecheckt"}, follow_redirects=False).status_code == 303
    c.post(f"/cases/{cid}/analyze")  # re-analysis keeps validation
    again = c.get(f"/api/cases/{cid}").json()
    assert next(f for f in again["findings"] if f["id"] == fid)["review_status"] == "confirmed"
    pdf_resp = c.get(f"/cases/{cid}/report.pdf")
    assert pdf_resp.status_code == 200 and pdf_resp.content.startswith(b"%PDF")
    assert c.get(f"/cases/{cid}", headers=HDR).status_code == 200

    other = TestClient(app)
    register(other, "b@y.be")
    assert other.get(f"/api/cases/{cid}").status_code == 404
    assert other.get(f"/cases/{cid}/report.pdf").status_code == 404
    assert TestClient(app).get("/api/cases/1").status_code == 401


def test_rejects_bad_upload():
    c = TestClient(app)
    register(c, "c@z.be")
    cid = int(re.search(r"/cases/(\d+)", c.post("/cases", data={"title": "t"}, follow_redirects=False).headers["location"]).group(1))
    r = c.post(f"/cases/{cid}/documents", files=[("files", ("x.exe", b"MZ", "application/octet-stream"))])
    assert r.status_code == 400
