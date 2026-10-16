"""Generates docs/REGLES.md: the register of every rule, to be completed and signed off by the professional who validates the rule set.

Run:  python -m app.rules_doc   (rewrites docs/REGLES.md; a test fails if the file misses a rule id)
"""
from __future__ import annotations

import re
from pathlib import Path

from . import i18n
from .rules import RULE_IDS, RULESET_VERSION

ROOT = Path(__file__).resolve().parent.parent


def _static_facts() -> dict[str, tuple[str, str, str]]:
    """rule id -> (domain, default severity, kind), read from the first F(...) in rules.py (severity may vary by situation)."""
    out: dict[str, tuple[str, str, str]] = {}
    for m in re.finditer(r'F\(\s*f?"([A-Z][A-Z\-{}a-z_.()]+)"\s*,\s*"(\w+)"\s*,\s*"?(\w+)"?\s*,\s*"(\w+)"', (ROOT / "app" / "rules.py").read_text()):
        out.setdefault(m[1], (m[2], m[3], m[4]))
    return out


def _tests_mentioning(rule_id: str) -> int:
    return sum(1 for p in (ROOT / "tests").glob("test_*.py") if rule_id in p.read_text())


def render() -> str:
    facts = _static_facts()
    lines = [
        "# Registre des règles",
        "",
        f"Jeu de règles **{RULESET_VERSION}** (périmètre : Flandre ; Bruxelles et Wallonie : préliminaires). Ce fichier est généré par `python -m app.rules_doc`.",
        "",
        "Chaque règle doit être validée par le professionnel compétent avant l'ouverture commerciale : compléter les colonnes **Base juridique**, **Date d'effet**, "
        "**Exceptions**, puis **Validée par / le**. Tant qu'une ligne n'est pas validée, la règle reste « en cours de validation » (variable `RULES_VALIDATED`).",
        "",
        "| Règle | Domaine | Gravité par défaut | Nature | Description (FR) | Cas de test | Base juridique | Date d'effet | Exceptions | Validée par / le |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for rid in RULE_IDS:
        if rid in ("DOC-EPC", "DOC-ASBESTOS", "DOC-ELECTRICAL", "DOC-SOIL", "DOC-DEED", "DOC-URBANISM"):
            domain, severity, kind = "documentation", "selon le document", "action"  # severity set per missing document in r_missing_docs
        else:
            domain, severity, kind = facts.get(rid, ("?", "?", "?"))
        title = i18n.t(f"rule.{rid}.title", "fr", **{k: "…" for k in ("filename", "pages", "threshold", "a", "b", "fa", "fb", "pa", "pb", "diff", "year", "until", "issue",
                                                                  "date", "attest", "deed", "extract", "list", "label", "score", "expected", "n", "file", "epc",
                                                                  "inspection", "postcode", "warning", "warnings")}).replace("|", "/")
        lines.append(f"| `{rid}` | {domain} | {severity} | {kind} | {title} | {_tests_mentioning(rid)} fichier(s) | à compléter | à compléter | à compléter | |")
    lines += ["", "La gravité réelle peut varier selon la situation (voir `app/rules.py`). La nature (fait, inférence, risque, action) est affichée dans chaque rapport.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    (ROOT / "docs" / "REGLES.md").write_text(render(), encoding="utf-8")
    print("docs/REGLES.md written")
