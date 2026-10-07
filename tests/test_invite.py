import re
import time

import pytest
from fastapi.testclient import TestClient

from app import config, invite
from app.main import app

CODE = "K6ZW-VQ8P-VYN5-FH2D"  # what the generator prints (no I, L, O, U)


def register(code, email):
    return TestClient(app).post("/register", data={"org_name": "O", "email": email, "password": "supersecret12", "invite_code": code, "accept_terms": "1"}, follow_redirects=False)


@pytest.fixture(autouse=True)
def invite_mode(monkeypatch):
    monkeypatch.setattr(config, "INVITE_CODE", CODE)


@pytest.mark.parametrize("typed", [
    CODE,                                   # exactly as generated
    CODE.lower(),                           # lower case
    CODE.replace("-", ""),                  # hyphens dropped
    CODE.replace("-", " "),                 # spaces instead of hyphens
    "  " + CODE + "  \n",                   # stray whitespace / newline from copy-paste
    f'"{CODE}"', f"'{CODE}'",               # pasted with quotes
    "k6zw-vq8p-vyn5-fh2d",                  # phone keyboard / all lower
    "K6ZW​-VQ8P-VYN5-FH2D",            # zero-width space picked up when copying from a web page
    "﻿" + CODE,                        # byte-order mark
    " " + CODE + " ",             # non-breaking spaces
    "Ｋ６ＺＷ－ＶＱ８Ｐ－ＶＹＮ５－ＦＨ２Ｄ",       # full-width characters (some IMEs)
    "INVITE_CODE=" + CODE,                  # the whole pasted line
    "invite_code = " + CODE.lower(),
])
def test_realistic_typing_and_paste_variants_are_accepted(typed):
    assert invite.matches(typed, CODE), repr(typed)


@pytest.mark.parametrize("typed", [
    "", "   ", None, "INVITE_CODE=", "INVITE_CODE", "K6ZW-VQ8P-VYN5-FH2E",   # last char differs
    "K6ZW-VQ8P-VYN5-FH2", "K6ZW-VQ8P-VYN5-FH2D-X", "XXXX-XXXX-XXXX-XXXX", "K6ZW",
    CODE[:-1], "x" + CODE, CODE + "9",
])
def test_wrong_incomplete_or_extended_codes_are_rejected(typed):
    assert not invite.matches(typed, CODE), repr(typed)


def test_an_empty_configured_code_never_matches_anything():
    for typed in ("", "anything", "INVITE_CODE="):
        assert not invite.matches(typed, "") and not invite.matches(typed, None) and not invite.matches(typed, "  -  ")


def test_look_alike_characters_are_treated_as_the_same_symbol():
    assert invite.matches("O0O0-1111-iiii-LLLL", "0000-1111-1111-1111")
    assert invite.normalize("a-b_c d") == "ABCD"


def test_operator_chosen_codes_work_the_same_way(monkeypatch):
    monkeypatch.setattr(config, "INVITE_CODE", "gent-test-2026")
    assert invite.matches("GENT TEST 2026", config.INVITE_CODE) and invite.matches("Gent-Test-2026", config.INVITE_CODE)
    assert not invite.matches("gent-test-2027", config.INVITE_CODE)


def test_generated_codes_are_unique_unambiguous_and_well_formed():
    codes = {invite.generate() for _ in range(500)}
    assert len(codes) == 500
    for c in codes:
        assert re.fullmatch(r"([0-9A-HJKMNP-TV-Z]{4}-){3}[0-9A-HJKMNP-TV-Z]{4}", c)
        assert not set(c) & set("ILOU")
        assert invite.matches(c, c)


def test_generated_code_survives_every_realistic_mangling():
    c = invite.generate()
    for typed in (c.lower(), c.replace("-", ""), c.replace("-", " ").lower(), f"INVITE_CODE={c}", f"  {c}\n"):
        assert invite.matches(typed, c)


@pytest.mark.parametrize("typed", [CODE.lower(), CODE.replace("-", " "), "INVITE_CODE=" + CODE, "﻿ " + CODE + " \n"])
def test_registration_accepts_the_variants(typed):
    assert register(typed, f"inv-ok-{abs(hash(typed))}@x.be").status_code == 303


def test_registration_still_refuses_a_wrong_code_and_says_so_in_the_logs(caplog):
    import logging
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        r = register("K6ZW-VQ8P-VYN5-FH2E", "inv-no@x.be")
    assert r.status_code == 403
    log = " ".join(x.getMessage() for x in caplog.records)
    assert "invite code mismatch" in log and "submitted 16 chars, configured 16 chars" in log
    assert "FH2E" not in log and CODE not in log and "K6ZW" not in log  # the code is never logged


def test_the_invite_field_is_not_autofilled_or_auto_capitalised_wrongly():
    field = re.search(r'<input name="invite_code"[^>]*>', TestClient(app).get("/login").text).group(0)
    for attr in ('autocomplete="off"', 'autocorrect="off"', 'spellcheck="false"', "autocapitalize="):
        assert attr in field


def test_comparison_time_does_not_depend_on_how_much_of_the_code_matches():
    """Constant-time comparison: a code matching the first 15 of 16 symbols must not be measurably slower to reject than a wrong one."""
    def best(typed, n=3000):
        t = time.perf_counter()
        for _ in range(n):
            invite.matches(typed, CODE)
        return time.perf_counter() - t
    near, far = best("K6ZWVQ8PVYN5FH2E"), best("AAAAAAAAAAAAAAAA")
    assert near < far * 1.5 + 0.05 and far < near * 1.5 + 0.05


def test_health_reports_build_and_whether_an_invite_code_is_required(monkeypatch):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "abcdef1234567")
    monkeypatch.setattr(config, "INVITE_CODE", "x-y-z")
    body = TestClient(app).get("/health").json()
    assert body["build"] == "abcdef1" and body["invite_required"] is True and "x-y-z" not in str(body)
