import re

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from tests.fixtures import ASB, DEED, ELEC, EPC, pdf
from tests.helpers import new_client
from tests.org_helpers import force_credits, org_credits, org_of


def key_for(c) -> str:
    html = c.post("/account/keys").text
    return re.search(r"(sk_live_[\w\-]+)", html).group(1)


def files(*docs):
    return [("files", (n, pdf(t), "application/pdf")) for n, t in docs]


def api(key=None) -> TestClient:
    return TestClient(app, headers={"x-api-key": key} if key else {})


def test_api_key_lifecycle_and_dossier():
    c = new_client("api1@x.be")
    key = key_for(c)
    assert key not in c.get("/account").text and key[:12] in c.get("/account").text  # full key shown once; later only the prefix
    r = api(key).post("/v1/dossier", files=files(("akte.pdf", DEED), ("epc.pdf", EPC), ("asbest.pdf", ASB), ("keuring.pdf", ELEC)), data={"title": "Via API"})
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "Via API" and data["scores"]["level"] == "high"
    assert {"X-SURFACE", "ASB-PRESENT"} <= {f["rule"] for f in data["findings"]}
    cid = data["id"]
    assert api(key).get(f"/v1/cases/{cid}").json()["id"] == cid
    pdf_resp = api(key).get(f"/v1/cases/{cid}/report.pdf")
    assert pdf_resp.status_code == 200 and pdf_resp.content.startswith(b"%PDF")
    # the case is also visible in the web UI of the same organisation
    assert c.get(f"/api/cases/{cid}").status_code == 200
    # revoke -> key dies
    kid = int(re.search(r"/account/keys/(\d+)/revoke", c.get("/account").text).group(1))
    assert c.post(f"/account/keys/{kid}/revoke", follow_redirects=False).status_code == 303
    assert api(key).get(f"/v1/cases/{cid}").status_code == 401


def test_api_rejects_missing_or_invalid_key():
    assert api().post("/v1/dossier", files=files(("a.pdf", DEED))).status_code == 401
    assert api("sk_live_nope").post("/v1/dossier", files=files(("a.pdf", DEED))).status_code == 401


def test_api_charges_credits_and_cleans_up_on_402():
    c = new_client("api2@x.be")
    oid = org_of("api2@x.be")
    key = key_for(c)
    force_credits(oid, 0)
    before = set(config.UPLOAD_DIR.glob(f"{oid}/*"))
    r = api(key).post("/v1/dossier", files=files(("akte.pdf", DEED), ("epc.pdf", EPC)))
    assert r.status_code == 402
    assert org_credits(oid) == 0  # nothing charged
    assert set(config.UPLOAD_DIR.glob(f"{oid}/*")) == before  # no orphan files left on disk
    force_credits(oid, 1)
    assert api(key).post("/v1/dossier", files=files(("akte.pdf", DEED), ("epc.pdf", EPC))).status_code == 200  # 2 files, 1 dossier
    assert org_credits(oid) == 0


def test_api_limits_and_bad_files():
    c = new_client("api3@x.be")
    key = key_for(c)
    too_many = [("files", (f"f{i}.pdf", pdf(DEED), "application/pdf")) for i in range(config.MAX_FILES_PER_REQUEST + 1)]
    assert api(key).post("/v1/dossier", files=too_many).status_code == 400
    assert api(key).post("/v1/dossier", files=[("files", ("evil.exe", b"MZ", "application/octet-stream"))]).status_code == 400


def test_api_tenant_isolation():
    a, b = new_client("api4a@x.be"), new_client("api4b@x.be")
    ka, kb = key_for(a), key_for(b)
    cid = api(ka).post("/v1/dossier", files=files(("akte.pdf", DEED))).json()["id"]
    assert api(kb).get(f"/v1/cases/{cid}").status_code == 404
    assert api(kb).get(f"/v1/cases/{cid}/report.pdf").status_code == 404


def test_api_requires_verified_email_when_enforced(monkeypatch):
    c = new_client("api5@x.be")
    key = key_for(c)
    monkeypatch.setattr(config, "REQUIRE_EMAIL_VERIFICATION", True)
    assert api(key).post("/v1/dossier", files=files(("akte.pdf", DEED))).status_code == 403
