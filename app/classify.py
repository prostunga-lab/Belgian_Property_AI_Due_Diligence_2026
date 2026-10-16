"""Keyword-based document classification (NL/FR/EN). Cheap, deterministic, explainable."""
from __future__ import annotations

import re

DOC_TYPES = {
    "epc": "EPC / PEB",
    "deed": "Acte / Akte",
    "asbestos": "Asbestattest",
    "electrical": "Contrôle électrique / Keuring",
    "cadastre": "Extrait cadastral / Kadastraal uittreksel",
    "soil": "Attestation du sol / Bodemattest",
    "plan": "Plan / Plattegrond",
    "invoice": "Facture de travaux / Factuur werken",
    "urbanism": "Renseignements urbanistiques / Stedenbouwkundige inlichtingen",
    "copro": "Copropriété / Mede-eigendom",
    "photo": "Photo",
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
    "cadastre": [
        (r"kadastraal uittreksel|uittreksel uit (?:de )?kadastrale|kadastrale legger", 6),
        (r"extrait (?:de la matrice )?cadastral|fiche cadastrale|matrice cadastrale", 6),
        (r"kadastraal inkomen|revenu cadastral", 3), (r"capakey|perceelnummer|numéro de parcelle", 3),
        (r"\bperceel\b|\bparcelle\b", 1),
    ],
    "soil": [
        (r"bodemattest", 8), (r"attestation du sol|certificat de contrôle du sol|certificat de qualité du sol", 8),
        (r"bodemverontreiniging|verontreinigd|pollution du sol|sol pollué", 3),
        (r"bodemsanering|assainissement du sol|\bovam\b|bruxelles environnement|ibgebim", 1),
        (r"risicogrond|terrain à risque", 3),
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
    "plan": [
        (r"grondplan|plattegrond|bouwplan|as[- ]built|plan d'étage|plan de situation|plan de construction|plan van de", 5),
        (r"schaal\s*1\s*[/:]\s*\d+|échelle\s*1\s*[/:]\s*\d+", 4), (r"\bverdieping\b|\bétage\b|\brez-de-chaussée\b|gelijkvloers", 1),
    ],
    "invoice": [
        (r"\bfactuur\b|\bfacture\b|\binvoice\b", 5), (r"factuurnummer|numéro de facture|invoice number", 3),
        (r"totaal incl|total ttc|te betalen|montant à payer|btw\s*\d+\s*%|tva\s*\d+\s*%", 3), (r"btw[- ]nummer|n° tva|numéro de tva", 2),
    ],
    "urbanism": [
        (r"stedenbouwkundig uittreksel|stedenbouwkundige inlichtingen|uittreksel uit het vergunningenregister|vergunningenregister", 8),
        (r"renseignements urbanistiques|attestation urbanistique|certificat d'urbanisme", 8),
        (r"gewestplan|plan de secteur|woongebied|zone d'habitat|bestemming|voorkooprecht|droit de préemption", 2),
        (r"\bpras\b|\bppas\b|\bcobat\b|urban\.brussels|zone d'habitation|inventaire du patrimoine", 3),
    ],
    "copro": [
        (r"mede-?eigendom|medeëigendom|vereniging van mede-?eigenaars|copropriété|association des copropriétaires", 5),
        (r"\bsyndic\b|algemene vergadering|assemblée générale", 3), (r"reservefonds|fonds de réserve|gemeenschappelijke kosten|charges communes", 3),
        (r"basisakte|acte de base|quotités|breukdelen|règlement de copropriété|reglement van mede-?eigendom", 3),
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
