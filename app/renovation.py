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
    # energy items are only triggered by an E or F label; `by_label` holds the rates for each (working assumptions, see docs/RENOVATION.md)
    "energy_roof": {"phase": "energy", "rules": ["EPC-POOR:E", "EPC-POOR:F"], "kind": "per_m2", "confidence": "assumption",
                    "by_label": {"E": {"low": 20, "high": 50, "flat_low": 3000, "flat_high": 8000}, "F": {"low": 40, "high": 90, "flat_low": 5000, "flat_high": 15000}}},
    "energy_glazing": {"phase": "energy", "rules": ["EPC-POOR:E", "EPC-POOR:F"], "kind": "per_m2", "confidence": "assumption",
                       "by_label": {"E": {"low": 25, "high": 50, "flat_low": 3000, "flat_high": 9000}, "F": {"low": 40, "high": 80, "flat_low": 6000, "flat_high": 16000}}},
    "energy_heating": {"phase": "energy", "rules": ["EPC-POOR:E", "EPC-POOR:F"], "kind": "flat", "confidence": "assumption",
                       "by_label": {"E": {"low": 3000, "high": 8000}, "F": {"low": 5000, "high": 14000}}},
    "permit_regularisation": {"phase": "before_signature", "rules": ["URB-EXT-NOPERMIT", "URB-INFRACTION", "CAD-UNBUILT"], "kind": "none", "confidence": "none"},
    "soil_investigation": {"phase": "before_signature", "rules": ["SOIL-POLLUTION"], "kind": "none", "confidence": "none"},
}


def costs() -> dict[str, dict]:
    """Defaults, overridden item by item by the JSON file named in RENOVATION_COST_FILE (e.g. {"electrical_compliance": {"low": 1500}})."""
    merged = {k: {**v, **({"by_label": {lab: dict(r) for lab, r in v["by_label"].items()}} if "by_label" in v else {})} for k, v in COSTS.items()}
    path = os.environ.get("RENOVATION_COST_FILE", "").strip()
    if path:
        try:
            with open(path, encoding="utf-8") as fh:
                for key, over in json.load(fh).items():
                    if key in merged and isinstance(over, dict):
                        allowed = {"low", "high", "flat_low", "flat_high"}
                        merged[key].update({k: v for k, v in over.items() if k in allowed and isinstance(v, (int, float))})
                        for label, rates in (over.get("by_label") or {}).items():
                            if label in merged[key].get("by_label", {}) and isinstance(rates, dict):
                                merged[key]["by_label"][label].update({k: v for k, v in rates.items() if k in allowed and isinstance(v, (int, float))})
        except (OSError, ValueError):
            pass  # a broken override file must never break an analysis: keep the defaults
    return merged


def _eur(x: float) -> str:
    return f"{x:,.0f}".replace(",", " ")


def compact(low, high, lang: str) -> str:
    """'15–25 k€' style range for tables (k only when both ends are round thousands or more), else '150 – 600 €'."""
    t = lambda key, **p: i18n.t(key, lang, **p)  # noqa: E731
    if low is None:
        return t("reno.cost.none_short")
    if low >= 1000 and high >= 1000:
        def k(x):
            v = round(x / 1000, 1)
            txt = f"{v:.1f}".rstrip("0").rstrip(".")
            return txt.replace(".", "," if lang in ("fr", "nl") else ".")
        return t("reno.cost.range_k", low=k(low), high=k(high))
    return t("reno.cost.range", low=_eur(low), high=_eur(high))


def _surface(docs):
    """(m², source doc) used to scale per-m² items: the energy certificate's floor area first, else any other document's."""
    order = sorted((d for d in docs if (d.fields or {}).get("surface_m2")), key=lambda d: d.doc_type != "epc")
    return (order[0].fields["surface_m2"]["value"], order[0]) if order else (None, None)


PRIORITY_OF = {"high": "high", "medium": "medium", "low": "low", "info": "low"}  # worst severity of the findings behind the item
PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}


def build(findings, docs, lang: str) -> dict:
    """{'rows': flat table sorted by priority, 'phases': same items grouped chronologically, totals...}."""
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
        rates = spec
        if "by_label" in spec:  # rates depend on the EPC label that triggered the item (the worst one wins)
            label = "F" if "EPC-POOR:F" in present else "E"
            rates = {**spec, **spec["by_label"][label]}
        low = high = None
        basis = ""
        if spec["kind"] == "flat":
            low, high, basis = rates["low"], rates["high"], t("reno.basis.flat")
        elif spec["kind"] == "per_m2":
            if m2:
                low, high = round(m2 * rates["low"], -2), round(m2 * rates["high"], -2)
                basis = t("reno.basis.per_m2", m2=_eur(m2), lo=rates["low"], hi=rates["high"], file=m2_doc.filename)
            else:
                low, high, basis = rates["flat_low"], rates["flat_high"], t("reno.basis.flat")
        sources = []
        for h in hits:
            for s in h.sources or []:
                if (s["filename"], s["page"]) not in {(x["filename"], x["page"]) for x in sources}:
                    sources.append(s)
        worst = min((PRIORITY_OF.get(h.severity, "low") for h in hits), key=PRIORITY_RANK.get)
        entry = {
            "id": item_id, "phase": spec["phase"], "title": t(f"reno.item.{item_id}.title"), "what": t(f"reno.item.{item_id}.what"),
            "note": t(f"reno.item.{item_id}.note") if i18n.has(f"reno.item.{item_id}.note", lang) else "",
            "priority": worst, "priority_label": t(f"reno.prio.{worst}"),
            "low": low, "high": high, "basis": basis, "confidence": spec["confidence"], "confidence_label": t(f"reno.conf.{spec['confidence']}"),
            "cost": compact(low, high, lang), "cost_full": t("reno.cost.range", low=_eur(low), high=_eur(high)) if low is not None else t("reno.cost.none"),
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
        p["cost"] = compact(p["low"], p["high"], lang) if p["high"] else ""
    rows = sorted((i for p in phase_list for i in p["items"]), key=lambda i: (PRIORITY_RANK[i["priority"]], PHASES.index(i["phase"])))
    total_low, total_high = sum(p["low"] for p in phase_list), sum(p["high"] for p in phase_list)
    return {"rows": rows, "phases": phase_list, "total_low": total_low, "total_high": total_high, "unestimated": unestimated, "price_basis": PRICE_BASIS,
            "total": compact(total_low, total_high, lang) if total_high else "",
            "unestimated_text": t("reno.unestimated", n=unestimated) if unestimated else ""}
