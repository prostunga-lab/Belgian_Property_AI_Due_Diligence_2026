import html
import re

from fastapi.testclient import TestClient

from app.main import app


def new_client(email: str, password: str = "supersecret12", register: bool = True) -> TestClient:
    c = TestClient(app)
    if register:
        r = c.post("/register", data={"org_name": "Org", "email": email, "password": password, "accept_terms": "1"}, follow_redirects=False)
        assert r.status_code == 303, r.text
    return c


def new_case(c: TestClient, title: str = "t") -> int:
    r = c.post("/cases", data={"title": title}, follow_redirects=False)
    return int(re.search(r"/cases/(\d+)", r.headers["location"]).group(1))


def credits_of(c: TestClient) -> int:
    m = re.search(r"(\d+) crédit", c.get("/", headers={"accept": "text/html"}).text)
    return int(m.group(1))


def link_in(body: str, path: str) -> str:
    return re.search(rf"(http://testserver{path}\?token=[\w\-.:]+)", body).group(1)


def page_text(response) -> str:
    """Response body with HTML entities decoded (templates escape apostrophes: n&#39;est)."""
    return html.unescape(response.text)
