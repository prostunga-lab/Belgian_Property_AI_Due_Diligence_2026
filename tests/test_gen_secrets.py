import importlib
import re
import subprocess
import sys

import pytest

from app import config, gen_secrets


def test_generated_values_are_random_and_long_enough():
    a, b = gen_secrets.generate(), gen_secrets.generate()
    assert a["SECRET_KEY"] != b["SECRET_KEY"] and a["FILE_ENCRYPTION_KEY"] != b["FILE_ENCRYPTION_KEY"] and a["INVITE_CODE"] != b["INVITE_CODE"]
    assert re.fullmatch(r"[0-9a-f]{64}", a["SECRET_KEY"]) and re.fullmatch(r"[0-9a-f]{64}", a["FILE_ENCRYPTION_KEY"])
    assert a["SECRET_KEY"] != a["FILE_ENCRYPTION_KEY"]  # never the same value for two purposes
    assert len(a["INVITE_CODE"]) >= 16 and a["APP_ENV"] == "production" and a["COOKIE_SECURE"] == "1"


def test_generated_values_satisfy_the_production_guard(monkeypatch):
    for k, v in gen_secrets.generate().items():
        monkeypatch.setenv(k, v)
    importlib.reload(config)  # would raise RuntimeError if anything required were missing
    assert config.APP_ENV == "production" and config.COOKIE_SECURE
    monkeypatch.undo()
    importlib.reload(config)


def test_cli_prints_paste_ready_lines():
    out = subprocess.run([sys.executable, "-m", "app.gen_secrets"], capture_output=True, text=True, check=True)
    lines = out.stdout.strip().splitlines()
    assert [l.split("=")[0] for l in lines] == ["APP_ENV", "COOKIE_SECURE", "SECRET_KEY", "FILE_ENCRYPTION_KEY", "INVITE_CODE"]
    assert "FILE_ENCRYPTION_KEY" in out.stderr  # the backup warning goes to stderr, not into the pasted lines
