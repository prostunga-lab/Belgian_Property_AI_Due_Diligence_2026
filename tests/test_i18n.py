import io
import re
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app import config, i18n, llm, mail, render
from app.i18n import CATALOGS, LANGS
from app.main import app
from app.rules import RULE_IDS
from tests.fixtures import ASB, DEED, ELEC, EPC, pdf
from tests.helpers import link_in, new_case, new_client, page_text

PLACEHOLDER = re.compile(r"\{(\w+)\}")
FIXTURES = [("akte.pdf", DEED), ("epc.pdf", EPC), ("asbest.pdf", ASB), ("keuring.pdf", ELEC)]


# --- catalogs ---------------------------------------------------------------------------------------

def test_all_languages_have_exactly_the_same_keys_and_placeholders():
    en = CATALOGS["en"]
    for lang in LANGS:
        assert set(CATALOGS[lang]) == set(en), f"{lang}: keys differ from en"
        for key, msg in en.items():
            assert set(PLACEHOLDER.findall(CATALOGS[lang][key])) == set(PLACEHOLDER.findall(msg)), f"{lang}:{key} placeholders"
            assert CATALOGS[lang][key].strip(), f"{lang}:{key} is empty"


def test_translations_are_actually_translated():
    """Guards against a language file that is a copy of another one (identical text only allowed for brand/neutral terms)."""
    neutral = {"contact.title", "contact.h1", "nav.contact", "footer.copyright", "ui.page_abbr", "case.score", "pdf.score", "severity.info", "pdf.rule", "pdf.title", "case.ocr_pages", "doctype.epc"}
    for a, b in (("fr", "en"), ("nl", "en"), ("fr", "nl")):
        same = [k for k in CATALOGS[a] if CATALOGS[a][k] == CATALOGS[b][k] and k not in neutral and len(CATALOGS[a][k]) > 25]
        assert same == [], f"{a} and {b} share identical long texts: {same[:5]}"


def test_every_rule_has_text_in_every_language():
    for lang in LANGS:
        for rid in RULE_IDS:
            for part in ("title", "detail"):
                assert f"rule.{rid}.{part}" in CATALOGS[lang], f"{lang}: rule.{rid}.{part}"


def test_rule_ids_list_matches_the_rules_source():
    src = Path("app/rules.py").read_text()
    used = set(re.findall(r'F\(\s*"([A-Z][A-Z\-]+)"', src)) | {f"DOC-{t}" for t in ("EPC", "ASBESTOS", "ELECTRICAL", "SOIL", "DEED")}
    assert used <= set(RULE_IDS), f"rules emit ids missing from RULE_IDS: {used - set(RULE_IDS)}"


def test_dynamic_label_keys_exist():
    for prefix, values in {"doctype": ["epc", "deed", "asbestos", "electrical", "cadastre", "soil", "unknown"],
                           "domain": ["legal", "urbanistic", "energy", "technical", "environmental", "documentation"],
                           "kind": ["fact", "inference", "risk", "action"], "level": ["low", "medium", "high"],
                           "severity": ["high", "medium", "low", "info"], "review": ["pending", "confirmed", "dismissed"],
                           "party": ["seller", "notary", "syndic"], "region": ["flanders", "brussels", "wallonia"]}.items():
        for lang in LANGS:
            for v in values:
                assert f"{prefix}.{v}" in CATALOGS[lang], f"{lang}: {prefix}.{v}"


def test_plurals_and_fallbacks():
    assert i18n.t("ui.credits", "en", n=1) == "1 credit" and i18n.t("ui.credits", "en", n=3) == "3 credits"
    assert i18n.t("ui.credits", "fr", n=0) == "0 crédits" and i18n.t("ui.credits", "nl", n=1) == "1 tegoed"
    assert i18n.t("does.not.exist", "nl") == "does.not.exist"  # visible, never a crash
    assert i18n.t("rule.X-DATES.detail", "xx", attest="a", deed="b").startswith("Attest")  # unknown language -> English
    assert "{" not in i18n.t("rule.X-SURFACE.detail", "fr", a=1, fa="x", pa=1, b=2, fb="y", pb=1, diff=3)


def test_language_negotiation():
    assert i18n.normalize("nl-BE") == "nl" and i18n.normalize("FR_be") == "fr" and i18n.normalize("de") is None
    assert i18n.from_accept_language("de-DE,de;q=0.9,en;q=0.8") == "en"
    assert i18n.from_accept_language("nl-BE,nl;q=0.9,fr;q=0.5") == "nl"
    assert i18n.from_accept_language("fr;q=0.2, en;q=0.9") == "en"
    assert i18n.from_accept_language("xx, *") is None and i18n.from_accept_language(None) is None


# --- request language -------------------------------------------------------------------------------------

def html_lang(client, **kw):
    return re.search(r'<html lang="(\w+)"', client.get("/login", **kw).text).group(1)


def test_language_resolution_order():
    c = TestClient(app)
    assert html_lang(c) == "fr"  # default
    assert html_lang(c, headers={"accept-language": "nl-BE,nl;q=0.9"}) == "nl"
    assert html_lang(c, headers={"accept-language": "nl"}, params={"lang": "en"}) == "en"  # ?lang beats the header
    c.cookies.set("lang", "en")
    assert html_lang(c, headers={"accept-language": "nl"}) == "en"  # cookie beats the header
    assert html_lang(c, params={"lang": "nl"}) == "nl"  # ?lang beats the cookie (one request only)
    assert html_lang(c) == "en"
    assert html_lang(c, params={"lang": "zz"}) == "en"  # unsupported values are ignored


def test_switcher_sets_cookie_persists_on_account_and_is_safe():
    c = new_client("lang1@x.be")
    r = c.get("/lang/nl?next=/account", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/account" and "lang=nl" in r.headers["set-cookie"]
    assert html_lang(c) == "nl" and "Taal" in page_text(c.get("/account"))
    # stored on the account: a fresh browser logging in gets the same language
    other = TestClient(app)
    other.post("/login", data={"email": "lang1@x.be", "password": "supersecret12", "accept_terms": "1"}, follow_redirects=False)
    assert html_lang(other) == "nl"
    # open-redirect attempts fall back to "/"
    for evil in ("https://evil.example", "//evil.example", "/\\evil.example", "javascript:alert(1)"):
        assert c.get("/lang/en", params={"next": evil}, follow_redirects=False).headers["location"] == "/"
    assert c.get("/lang/xx", follow_redirects=False).status_code == 404


def test_switcher_is_visible_and_marks_current_language():
    page = TestClient(app).get("/login", params={"lang": "nl"}).text
    assert page.count('class="langbtn') == 3 and 'class="langbtn on" hreflang="nl"' in page
    for code in LANGS:
        assert f"/lang/{code}?next=" in page


def test_no_free_text_is_reflected_from_the_url():
    c = new_client("msg1@x.be")
    assert "alert(1)" not in c.get("/login", params={"msg": "<script>alert(1)</script>"}).text
    assert "pwned-text" not in c.get("/login", params={"msg": "pwned-text"}).text
    assert "pwned-text" not in c.get("/", params={"msg": "pwned-text"}).text


def pages_text(lang):
    c = new_client(f"pg-{lang}-{uuid.uuid4().hex[:8]}@x.be")
    c.get(f"/lang/{lang}")
    cid = new_case(c)
    c.post(f"/cases/{cid}/documents", files=[("files", (n, pdf(t), "application/pdf")) for n, t in FIXTURES])
    c.post(f"/cases/{cid}/analyze")
    return {"case": page_text(c.get(f"/cases/{cid}")), "dash": page_text(c.get("/")), "acct": page_text(c.get("/account")),
            "login": page_text(TestClient(app, cookies={"lang": lang}).get("/login")), "cid": cid, "client": c}


@pytest.mark.parametrize("lang,markers,foreign", [
    ("en", ["Analyse the case", "Potential risk", "Recommendation", "Delete the case", "Log out"], ["Analyser le dossier", "Aanbeveling", "Uitloggen", "Déconnexion"]),
    ("fr", ["Analyser le dossier", "Risque potentiel", "Recommandation", "Supprimer le dossier", "Déconnexion"], ["Analyse the case", "Aanbeveling", "Uitloggen", "Log out"]),
    ("nl", ["Dossier analyseren", "Mogelijk risico", "Aanbeveling", "Dossier verwijderen", "Uitloggen"], ["Analyse the case", "Analyser le dossier", "Déconnexion", "Log out"]),
])
def test_whole_ui_is_rendered_in_one_language(lang, markers, foreign):
    p = pages_text(lang)
    blob = p["case"] + p["dash"] + p["acct"] + p["login"]
    for m in markers:
        assert m in blob, f"{lang}: missing {m!r}"
    for f in foreign:
        assert f not in blob, f"{lang}: found foreign text {f!r}"


def test_same_analysis_is_read_in_each_language():
    p = pages_text("en")
    c, cid = p["client"], p["cid"]
    expect = {"en": ("Surface areas do not match", "Asbestos found or suspected", "Electrical installation not compliant"),
              "fr": ("Superficies différentes selon les documents", "Amiante constaté ou suspecté", "Installation électrique non conforme"),
              "nl": ("Oppervlaktes komen niet overeen", "Asbest aangetroffen of vermoed", "Elektrische installatie niet conform")}
    for lang, titles in expect.items():
        data = c.get(f"/api/cases/{cid}", params={"lang": lang}).json()
        got = {f["title"] for f in data["findings"]}
        assert set(titles) <= got, (lang, got)
        assert data["lang"] == lang
        surface = next(f for f in data["findings"] if f["rule"] == "X-SURFACE")
        assert "185" in surface["detail"] and "240" in surface["detail"] and "30" in surface["detail"]  # params survive translation
        assert all("rule." not in f["title"] and "{" not in f["detail"] for f in data["findings"])
    # stable, language-neutral identifiers for integrations
    assert next(f for f in data["findings"] if f["rule"] == "X-SURFACE")["params"]["diff"] == "30"


def test_validation_and_comments_survive_a_language_switch():
    p = pages_text("nl")
    c, cid = p["client"], p["cid"]
    fid = next(f for f in c.get(f"/api/cases/{cid}").json()["findings"] if f["rule"] == "ASB-PRESENT")["id"]
    c.post(f"/cases/{cid}/findings/{fid}/review", data={"status": "confirmed"})
    c.get("/lang/fr")
    c.post(f"/cases/{cid}/analyze")  # re-analysis in another language keeps human validation
    again = next(f for f in c.get(f"/api/cases/{cid}").json()["findings"] if f["id"] == fid)
    assert again["review_status"] == "confirmed"
    assert "confirmé" in page_text(c.get(f"/cases/{cid}"))


def test_pdf_report_in_each_language():
    p = pages_text("fr")
    c, cid = p["client"], p["cid"]
    expect = {"fr": ["Rapport de due diligence immobilière", "Constats", "Recommandation", "Source", "Amiante constaté ou suspecté", "Ce rapport est une aide"],
              "nl": ["Bevindingen", "Aanbeveling", "Bron", "Asbest aangetroffen of vermoed", "Dit rapport is een hulpmiddel"],
              "en": ["Findings", "Recommendation", "Source", "Asbestos found or suspected", "This report is an aid"]}
    for lang, words in expect.items():
        r = c.get(f"/cases/{cid}/report.pdf", params={"lang": lang})
        assert r.status_code == 200 and r.content.startswith(b"%PDF")
        text = " ".join(pg.extract_text() for pg in PdfReader(io.BytesIO(r.content)).pages)
        for w in words:
            assert w in text, f"{lang} PDF lacks {w!r}"
    # the UI language is the default for the download when no ?lang is given
    c.get("/lang/nl")
    default = " ".join(pg.extract_text() for pg in PdfReader(io.BytesIO(c.get(f"/cases/{cid}/report.pdf").content)).pages)
    assert "Bevindingen" in default and "Findings" not in default


# --- errors, API, e-mail, legacy ---------------------------------------------------------------------------

def test_errors_are_translated_for_browsers_and_api_clients():
    c = new_client("err1@x.be")
    for lang, title, word in (("fr", "Introuvable", "Dossier introuvable"), ("nl", "Niet gevonden", "Dossier niet gevonden"), ("en", "Not found", "Case not found")):
        r = c.get("/cases/99999", params={"lang": lang}, headers={"accept": "text/html"})
        body = page_text(r)
        assert r.status_code == 404 and title in body and word in body
        j = c.get("/api/cases/99999", params={"lang": lang})
        assert j.json()["detail"] == word + "." and j.json()["code"] == "err.not_found.case"
    assert TestClient(app).get("/api/cases/1", headers={"accept-language": "nl"}).json()["code"] == "err.not_authenticated"
    assert TestClient(app).get("/api/cases/1").json()["detail"] == "Not authenticated."  # API default is English


def test_api_language_follows_accept_language_and_defaults_to_english():
    c = new_client("api-l@x.be")
    key = re.search(r"(sk_live_[\w\-]+)", c.post("/account/keys").text).group(1)
    api = lambda **h: TestClient(app, headers={"x-api-key": key, **h})
    files = [("files", (n, pdf(t), "application/pdf")) for n, t in FIXTURES]
    data = api(**{"accept-language": "nl-BE,nl;q=0.9"}).post("/v1/dossier", files=files).json()
    assert data["lang"] == "nl" and any(f["title"] == "Asbest aangetroffen of vermoed" for f in data["findings"])
    assert api().get(f"/v1/cases/{data['id']}").json()["lang"] == "en"
    bad = api().post("/v1/dossier", files=[("files", ("x.exe", b"MZ", "application/octet-stream"))])
    assert bad.status_code == 400 and bad.json()["code"] == "err.unsupported_file" and ".exe" in bad.json()["detail"]


@pytest.mark.parametrize("lang,subject,greeting", [("fr", "Confirmez votre adresse e-mail", "Bonjour"), ("nl", "Bevestig uw e-mailadres", "Dag"),
                                                    ("en", "Confirm your e-mail address", "Hello")])
def test_emails_are_sent_in_the_users_language(monkeypatch, lang, subject, greeting):
    box = []
    monkeypatch.setattr(mail, "send", lambda to, subj, body: box.append((to, subj, body)))
    c = TestClient(app, cookies={"lang": lang})
    c.post("/register", data={"org_name": "O", "email": f"mail-{lang}@x.be", "password": "supersecret12", "accept_terms": "1"})
    assert box[0][1] == subject and box[0][2].startswith(greeting) and link_in(box[0][2], "/verify")
    box.clear()
    c.post("/forgot", data={"email": f"mail-{lang}@x.be"})
    assert box and "/reset?token=" in box[0][2] and box[0][2].startswith(greeting)


def test_ai_reading_is_requested_in_the_readers_language(monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-ant-test")
    seen = []
    monkeypatch.setattr(llm, "_ask", lambda system, user, max_tokens: seen.append(system) or '{"synthese": "ok"}')
    assert llm.analyze("epc", "x", "nl") == {"synthese": "ok", "_lang": "nl"}
    assert "néerlandais" in seen[-1] and "clés JSON" in seen[-1]
    llm.analyze("epc", "x", "en")
    assert "anglais" in seen[-1]
    llm.cross_check([{}, {}], "fr")
    assert "français" in seen[-1]


def test_legacy_findings_without_params_still_render():
    legacy = render.finding_text("OLD-RULE", None, "nl", {"title": "T", "detail": "D", "recommendation": "R"})
    assert legacy == {"title": "T", "detail": "D", "recommendation": "R"}
    assert render.warning_text("ocr_failed:3", "nl") == "OCR mislukt op pagina 3."
    assert render.warning_text("Ancien texte libre", "en") == "Ancien texte libre"


def test_ocr_warnings_are_rendered_per_language():
    from app.rules import DocView, run_rules
    d = DocView(1, "s.pdf", "unknown", [""], {}, [], ["ocr_unavailable_pdf"])
    f = next(x for x in run_rules([d]) if x.rule_id == "DOC-OCR")
    assert "OCR indisponible" in render.finding_text(f.rule_id, f.params, "fr")["detail"]
    assert "OCR niet beschikbaar" in render.finding_text(f.rule_id, f.params, "nl")["detail"]
    assert "OCR unavailable" in render.finding_text(f.rule_id, f.params, "en")["detail"]
