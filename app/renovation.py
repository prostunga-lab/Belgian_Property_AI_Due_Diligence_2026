"""Indicative renovation plan and budget, derived from the findings of an analysis.

IMPORTANT: this is an order of magnitude, NOT a quote. Unit costs are published market ranges (excl. VAT, 2026) kept in
COSTS below, adjustable without touching code through a JSON file (env RENOVATION_COST_FILE). Items for which no honest range
exists (permit regularisation, soil remediation, ...) are listed WITHOUT a number rather than guessed.
Basis, sources and assumptions: docs/RENOVATION.md.
"""
from __future__ import annotations

import json
import os

from . import i18n

PRICE_BASIS = "2026-10"
PHASES = ("before_signature", "safety_compliance", "energy")  # chronological order of the plan

# kind: flat (EUR) | per_m2 (EUR per m² of floor area, flat_fallback when the area is unknown) | none (no honest estimate)
# confidence: market (published range), assumption (working hypothesis built from published ranges), none
COSTS: dict[str, dict] = {
    "asbestos_inventory": {"phase": "before_signature", "rules": ["ASB-PRESENT", "ASB-UNCLEAR"], "kind": "flat", "low": 150, "high": 600, "confidence": "market"},
    "asbestos_removal": {"phase": "safety_compliance", "rules": ["ASB-PRESENT"], "kind": "flat", "low": 3000, "high": 15000, "confidence": "assumption"},
    "electrical_compliance": {"phase": "safety_compliance", "rules": ["ELEC-NONCONFORM"], "kind": "flat", "low": 1000, "high": 7000, "confidence": "market"},
    "electrical_recheck": {"phase": "safety_compliance", "rules": ["ELEC-OLD", "WORK-ELEC-STALE"], "kind": "flat", "low": 150, "high": 300, "confidence": "market"},
    "epc_refresh": {"phase": "before_signature", "rules": ["EPC-EXPIRED", "EPC-OLD", "WORK-EPC-STALE"], "kind": "flat", "low": 150, "high": 500, "confidence": "market"},
    "energy_upgrade_e": {"phase": "energy", "rules": ["EPC-POOR:E"], "kind": "per_m2", "low": 50, "high": 130, "flat_low": 2000, "flat_high": 15000, "confidence": "assumption"},
    "energy_upgrade_f": {"phase": "energy", "rules": ["EPC-POOR:F"], "kind": "per_m2", "low": 100, "high": 250, "flat_low": 8000, "flat_high": 25000, "confidence": "assumption"},
    "permit_regularisation": {"phase": "before_signature", "rules": ["URB-EXT-NOPERMIT", "URB-INFRACTION", "CAD-UNBUILT"], "kind": "none", "confidence": "none"},
    "soil_investigation": {"phase": "before_signature", "rules": ["SOIL-POLLUTION"], "kind": "none", "confidence": "none"},
}


def costs() -> dict[str, dict]:
    """Defaults, overridden item by item by the JSON file named in RENOVATION_COST_FILE (e.g. {"electrical_compliance": {"low": 1500}})."""
    merged = {k: dict(v) for k, v in COSTS.items()}
    path = os.environ.get("RENOVATION_COST_FILE", "").strip()
    if path:
        try:
            with open(path, encoding="utf-8") as fh:
                for key, over in json.load(fh).items():
                    if key in merged and isinstance(over, dict):
                        merged[key].update({k: v for k, v in over.items() if k in {"low", "high", "flat_low", "flat_high"} and isinstance(v, (int, float))})
        except (OSError, ValueError):
            pass  # a broken override file must never break an analysis: keep the defaults
    return merged


def _eur(x: float) -> str:
    return f"{x:,.0f}".replace(",", " ")


def _surface(docs):
    """(m², source doc, field) used to scale per-m² items: the energy certificate's floor area first, else any other document's."""
    order = sorted((d for d in docs if (d.fields or {}).get("surface_m2")), key=lambda d: d.doc_type != "epc")
    return (order[0].fields["surface_m2"]["value"], order[0]) if order else (None, None)


def build(findings, docs, lang: str) -> dict:
    t = lambda key, **p: i18n.t(key, lang, **p)  # noqa: E731
    present: dict[str, object] = {}
    for f in findings:
        present.setdefault(f.rule_id, f)
        if f.rule_id == "EPC-POOR":
            present.setdefault(f"EPC-POOR:{(f.params or {}).get('label', '')}", f)
    m2, m2_doc = _surface(docs)
    phases = {p: {"id": p, "label": t(f"reno.phase.{p}"), "items": [], "low": 0, "high": 0} for p in PHASES}
    unestimated = 0
    for item_id, spec in costs().items():
        hits = [present[r] for r in spec["rules"] if r in present]
        if not hits:
            continue
        low = high = None
        basis = ""
        if spec["kind"] == "flat":
            low, high, basis = spec["low"], spec["high"], t("reno.basis.flat")
        elif spec["kind"] == "per_m2":
            if m2:
                low, high = round(m2 * spec["low"], -2), round(m2 * spec["high"], -2)
                basis = t("reno.basis.per_m2", m2=_eur(m2), lo=spec["low"], hi=spec["high"], file=m2_doc.filename)
            else:
                low, high, basis = spec["flat_low"], spec["flat_high"], t("reno.basis.flat")
        sources = []
        for h in hits:
            for s in h.sources or []:
                if (s["filename"], s["page"]) not in {(x["filename"], x["page"]) for x in sources}:
                    sources.append(s)
        entry = {
            "id": item_id, "title": t(f"reno.item.{item_id}.title"), "what": t(f"reno.item.{item_id}.what"),
            "note": t(f"reno.item.{item_id}.note") if i18n.has(f"reno.item.{item_id}.note", lang) else "",
            "low": low, "high": high, "basis": basis, "confidence": spec["confidence"], "confidence_label": t(f"reno.conf.{spec['confidence']}"),
            "cost": t("reno.cost.range", low=_eur(low), high=_eur(high)) if low is not None else t("reno.cost.none"),
            "rules": [h.rule_id for h in hits], "sources": sources[:3],
        }
        ph = phases[spec["phase"]]
        ph["items"].append(entry)
        if low is None:
            unestimated += 1
        else:
            ph["low"] += low
            ph["high"] += high
    phase_list = [p for p in phases.values() if p["items"]]
    for p in phase_list:
        p["cost"] = t("reno.cost.range", low=_eur(p["low"]), high=_eur(p["high"])) if p["high"] else ""
    total_low, total_high = sum(p["low"] for p in phase_list), sum(p["high"] for p in phase_list)
    return {"phases": phase_list, "total_low": total_low, "total_high": total_high, "unestimated": unestimated, "price_basis": PRICE_BASIS,
            "total": t("reno.cost.range", low=_eur(total_low), high=_eur(total_high)) if total_high else "",
            "unestimated_text": t("reno.unestimated", n=unestimated) if unestimated else ""}
