"""Keyword-based document classification (NL/FR/EN). Cheap, deterministic, explainable."""
from __future__ import annotations

import re

DOC_TYPES = {
    "epc": "EPC / PEB",
    "deed": "Acte / Akte",
    "asbestos": "Asbestattest",
    "electrical": "Contrôle électrique / Keuring",
    "unknown": "Non reconnu",
}

KEYWORDS: dict[str, list[tuple[str, int]]] = {
    "epc": [
        (r"energieprestatiecertificaat", 5), (r"\bepc\b", 3), (r"\bpeb\b", 3),
        (r"certificat de performance énergétique", 5), (r"energielabel", 3),
        (r"kwh/m²", 2), (r"energy performance certificate", 5),
    ],
    "deed": [
        (r"\bakte\b", 3), (r"verkoopakte|authentieke akte", 5), (r"\bnotaris\b", 2),
        (r"\bacte (authentique|de vente)\b", 5), (r"\bnotaire\b", 2), (r"\bcompromis\b", 3),
        (r"verkoper", 1), (r"koper", 1), (r"vendeur", 1), (r"acquéreur", 1),
        (r"kadastraal|cadastr", 2),
    ],
    "asbestos": [
        (r"asbestattest", 6), (r"asbest", 3), (r"amiante", 3), (r"ovam", 2),
        (r"asbestinventaris", 5),
    ],
    "electrical": [
        (r"elektrische installatie", 4), (r"keuringsverslag", 4), (r"\barei\b", 3),
        (r"\brgie\b", 3), (r"installation électrique", 4), (r"elektriciteit", 2),
        (r"conform", 1), (r"erkend organisme|organisme agréé", 3),
    ],
}


def classify(pages: list[str], filename: str = "") -> tuple[str, float]:
    text = (filename + "\n" + "\n".join(pages)).lower()
    scores = {
        t: sum(w * min(len(re.findall(p, text)), 3) for p, w in kws) for t, kws in KEYWORDS.items()
    }
    best = max(scores, key=scores.get)
    total = sum(scores.values())
    if scores[best] < 4 or total == 0:
        return "unknown", 0.0
    return best, round(scores[best] / total, 2)
