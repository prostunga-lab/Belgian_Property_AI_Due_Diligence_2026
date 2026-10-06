from __future__ import annotations

DOMAINS = ["legal", "urbanistic", "energy", "technical", "environmental", "documentation"]
PENALTY = {"high": 40, "medium": 20, "low": 8, "info": 0}
WEIGHTS = {"legal": 1.0, "urbanistic": 1.2, "energy": 0.8, "technical": 1.0, "environmental": 1.2, "documentation": 0.6}


def score(findings) -> dict:
    """Risk score 0-100 per domain (higher = riskier) and weighted global score (never below the worst domain / 1.5)."""
    per = {d: 0 for d in DOMAINS}
    for f in findings:
        if f.kind in ("risk", "inference", "action") or f.severity != "info":
            per[f.domain] = min(100, per[f.domain] + PENALTY.get(f.severity, 0))
    wsum = sum(WEIGHTS.values())
    avg = sum(per[d] * WEIGHTS[d] for d in DOMAINS) / wsum
    overall = round(max(avg, max(per.values()) / 1.5))
    level = "high" if overall >= 50 else "medium" if overall >= 25 else "low"
    return {"domains": per, "overall": min(100, overall), "level": level}
