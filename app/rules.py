"""Versioned regulatory + cross-document rules (Flanders MVP).

Each rule returns findings with: domain, severity, kind (fact|inference|risk|action), sources (doc/page/excerpt),
rule_id, rule_version and ``params``. Findings carry NO prose: the text for a finding is looked up in the i18n catalogs
(``rule.<RULE_ID>.title|detail|rec``, optional ``.<variant>``) when it is displayed, so the same analysis can be read in
French, Dutch or English. Rules are decision support only; legal pointers are "to verify", not legal advice.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

RULESET_VERSION = "VL-2026.1"  # region-date versioning; bump when regulation changes


@dataclass
class DocView:
    id: int
    filename: str
    doc_type: str
    pages: list[str]
    fields: dict
    ocr_pages: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


@dataclass
class F:
    rule_id: str
    domain: str  # legal|urbanistic|energy|technical|environmental|documentation
    severity: str  # info|low|medium|high
    kind: str
    params: dict = field(default_factory=dict)  # values for the catalog templates; params["variant"] picks a text variant
    question_for: str = ""
    sources: list = field(default_factory=list)
    rule_version: str = RULESET_VERSION


def src(doc: DocView, name: str) -> dict:
    f = doc.fields[name]
    return {"doc_id": doc.id, "filename": doc.filename, "page": f["page"], "excerpt": f["excerpt"]}


def by_type(docs: list[DocView], t: str) -> DocView | None:
    return next((d for d in docs if d.doc_type == t), None)


def val(doc: DocView | None, name: str):
    return doc.fields[name]["value"] if doc and name in doc.fields else None


def _norm_addr(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", s.lower())) - {"de", "het", "van", "te"}


def _today() -> dt.date:
    return dt.date.today()


# --- completeness ---------------------------------------------------------------------------

REQUIRED = {  # doc type -> (domain, default severity, party to ask)
    "epc": ("energy", "high", "seller"),
    "asbestos": ("environmental", "high", "seller"),
    "electrical": ("technical", "medium", "seller"),
    "soil": ("environmental", "medium", "seller"),
    "deed": ("legal", "medium", "notary"),
}


def r_missing_docs(docs, ctx):
    present = {d.doc_type for d in docs}
    for t, (domain, sev, party) in REQUIRED.items():
        if t in present:
            continue
        params: dict = {}
        if t == "asbestos":
            by = next((val(d, "build_year") for d in docs if val(d, "build_year")), None)
            if by and by >= 2001:
                sev, params = "low", {"variant": "young", "year": by}
        yield F(f"DOC-{t.upper()}", "documentation", sev, "action", params, party)


OCR_LOW_CONFIDENCE = 75.0


def r_unreadable(docs, ctx):
    for d in docs:
        whole = [{"doc_id": d.id, "filename": d.filename, "page": 1, "excerpt": ""}]
        if sum(len(p) for p in d.pages) < 80:
            params = {"filename": d.filename, "warnings": list(d.warnings), "variant": "warned" if d.warnings else "empty"}
            yield F("DOC-OCR", "documentation", "medium", "risk", params, "", whole)
            continue
        if d.ocr_pages:
            low = [o for o in d.ocr_pages if o["confidence"] < OCR_LOW_CONFIDENCE]
            if low:
                yield F("DOC-OCR-LOWQ", "documentation", "medium", "risk",
                        {"filename": d.filename, "threshold": f"{OCR_LOW_CONFIDENCE:.0f}", "pages": ", ".join(str(o["page"]) for o in low)}, "", whole)
            else:
                yield F("DOC-OCR-USED", "documentation", "info", "fact",
                        {"filename": d.filename, "pages": ", ".join(str(o["page"]) for o in d.ocr_pages)}, "", whole)
        for w in d.warnings:
            yield F("DOC-WARN", "documentation", "low", "action", {"filename": d.filename, "warning": w}, "", whole)
        if d.doc_type == "unknown":
            yield F("DOC-UNK", "documentation", "low", "action", {"filename": d.filename}, "", whole)


# --- energy ---------------------------------------------------------------------------------

LABEL_MAX = [("A", 100), ("B", 200), ("C", 300), ("D", 400), ("E", 500)]


def _label_for(score: float) -> str:
    for lab, mx in LABEL_MAX:
        if score <= mx:
            return lab
    return "F"


def r_epc_validity(docs, ctx):
    d = by_type(docs, "epc")
    if not d:
        return
    until = val(d, "epc_valid_until")
    if until and dt.date.fromisoformat(until) < _today():
        yield F("EPC-EXPIRED", "energy", "high", "risk", {"until": until}, "seller", [src(d, "epc_valid_until")])
    elif not until and (issue := val(d, "epc_issue_date")):
        if dt.date.fromisoformat(issue) < _today().replace(year=_today().year - 10):
            yield F("EPC-OLD", "energy", "high", "risk", {"issue": issue}, "seller", [src(d, "epc_issue_date")])


def r_epc_label(docs, ctx):
    d = by_type(docs, "epc")
    if not d:
        return
    score, label = val(d, "epc_score"), val(d, "epc_label")
    if score is not None and label and _label_for(score) != label[0]:
        yield F("EPC-LABEL-MISMATCH", "energy", "medium", "inference",
                {"score": f"{score:.0f}", "expected": _label_for(score), "label": label}, "seller", [src(d, "epc_score"), src(d, "epc_label")])
    lab = (label or (_label_for(score) if score is not None else "") or "")[:1]
    if lab in ("E", "F"):
        sev = "high" if lab == "F" else "medium"
        yield F("EPC-POOR", "energy", sev, "risk", {"label": lab}, "notary",
                [src(d, "epc_label" if "epc_label" in d.fields else "epc_score")])


# --- environmental / technical --------------------------------------------------------------

def r_asbestos(docs, ctx):
    d = by_type(docs, "asbestos")
    if not d:
        return
    if val(d, "asbestos_present") is True:
        yield F("ASB-PRESENT", "environmental", "high", "risk", {}, "seller", [src(d, "asbestos_present")])
    elif val(d, "asbestos_present") is False:
        yield F("ASB-CLEAR", "environmental", "info", "fact", {}, "", [src(d, "asbestos_present")])
    elif "asbestos_present" not in d.fields:
        yield F("ASB-UNCLEAR", "environmental", "medium", "risk", {}, "", [{"doc_id": d.id, "filename": d.filename, "page": 1, "excerpt": ""}])


def r_electrical(docs, ctx):
    d = by_type(docs, "electrical")
    if not d:
        return
    if val(d, "electrical_conform") is False:
        yield F("ELEC-NONCONFORM", "technical", "high", "risk", {}, "seller", [src(d, "electrical_conform")])
    ins = val(d, "inspection_date")
    if ins and dt.date.fromisoformat(ins) < _today().replace(year=_today().year - 25):
        yield F("ELEC-OLD", "technical", "medium", "risk", {"date": ins}, "seller", [src(d, "inspection_date")])


def r_soil(docs, ctx):
    d = by_type(docs, "soil")
    if not d:
        return
    pol = val(d, "soil_pollution_mentioned")
    if pol is True:
        yield F("SOIL-POLLUTION", "environmental", "high", "risk", {}, "notary", [src(d, "soil_pollution_mentioned")])
    elif pol is False:
        yield F("SOIL-CLEAR", "environmental", "info", "fact", {}, "", [src(d, "soil_pollution_mentioned")])
    else:
        yield F("SOIL-UNCLEAR", "environmental", "medium", "risk", {}, "", [{"doc_id": d.id, "filename": d.filename, "page": 1, "excerpt": ""}])


def r_cadastre(docs, ctx):
    cad, deed = by_type(docs, "cadastre"), by_type(docs, "deed")
    if cad and val(cad, "unbuilt_plot"):
        by = next((val(d, "build_year") for d in docs if d is not cad and val(d, "build_year")), None)
        if by or by_type(docs, "epc"):
            yield F("CAD-UNBUILT", "urbanistic", "high", "inference", {}, "notary", [src(cad, "unbuilt_plot")])
    if cad and deed and val(cad, "cadastral_ref") and val(deed, "cadastral_ref"):
        a, b = val(cad, "cadastral_ref"), val(deed, "cadastral_ref")
        if a.split("/")[0] != b.split("/")[0] or a != b:
            yield F("X-CADASTRE", "legal", "high", "inference", {"deed": b, "extract": a}, "notary",
                    [src(deed, "cadastral_ref"), src(cad, "cadastral_ref")])


# --- cross-document -------------------------------------------------------------------------

def r_address(docs, ctx):
    """One finding listing every distinct address, rather than one per document pair."""
    items = [(d, d.fields["address"]["value"]) for d in docs if "address" in d.fields]
    groups: list[list] = []
    for d, addr in items:
        tokens = _norm_addr(addr)
        for g in groups:
            ref = g[0][2]
            if tokens and ref and len(tokens & ref) / min(len(tokens), len(ref)) >= 0.6:
                g.append((d, addr, tokens))
                break
        else:
            groups.append([(d, addr, tokens)])
    if len(groups) > 1:
        detail = " ; ".join(f"'{g[0][1]}' ({', '.join(x[0].filename for x in g)})" for g in groups)
        yield F("X-ADDRESS", "legal", "high", "inference", {"list": detail}, "notary",
                [src(x[0], "address") for g in groups for x in g])


def r_surface(docs, ctx):
    items = [(d, d.fields["surface_m2"]) for d in docs if "surface_m2" in d.fields]
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            (da, fa), (db, fb) = items[i], items[j]
            hi, lo = max(fa["value"], fb["value"]), min(fa["value"], fb["value"])
            if lo and (hi - lo) / lo > 0.10:
                yield F("X-SURFACE", "urbanistic", "high" if (hi - lo) / lo > 0.25 else "medium", "inference",
                        {"a": f"{fa['value']:.0f}", "fa": da.filename, "pa": fa["page"], "b": f"{fb['value']:.0f}", "fb": db.filename,
                         "pb": fb["page"], "diff": f"{100 * (hi - lo) / lo:.0f}"},
                        "notary", [src(da, "surface_m2"), src(db, "surface_m2")])


def r_extension_permit(docs, ctx):
    deed, epc = by_type(docs, "deed"), by_type(docs, "epc")
    ext_doc = next((d for d in (epc, deed) if d and (val(d, "extension_m2") or val(d, "extension_mentioned"))), None)
    if not ext_doc:
        return
    if not (deed and (val(deed, "permit_mentioned") or val(deed, "urbanism_info"))):
        name = "extension_m2" if "extension_m2" in ext_doc.fields else "extension_mentioned"
        yield F("URB-EXT-NOPERMIT", "urbanistic", "high", "risk", {}, "notary", [src(ext_doc, name)])


def r_urbanism_info(docs, ctx):
    deed = by_type(docs, "deed")
    if deed and not (val(deed, "urbanism_info") or val(deed, "permit_mentioned")):
        yield F("URB-NO-INFO", "urbanistic", "medium", "risk", {}, "notary",
                [{"doc_id": deed.id, "filename": deed.filename, "page": 1, "excerpt": ""}])


def r_build_year(docs, ctx):
    items = [(d, d.fields["build_year"]) for d in docs if "build_year" in d.fields]
    years = {f["value"] for _, f in items}
    if len(years) > 1:
        yield F("X-BUILDYEAR", "legal", "medium", "inference", {"list": ", ".join(f"{f['value']} ({d.filename})" for d, f in items)},
                "seller", [src(d, "build_year") for d, _ in items])


def r_old_house_asbestos(docs, ctx):
    asb = by_type(docs, "asbestos")
    by = next((val(d, "build_year") for d in docs if val(d, "build_year")), None)
    if asb and by and by < 2001 and val(asb, "asbestos_present") is False:
        d = next(d for d in docs if val(d, "build_year") == by)
        yield F("ASB-OLD-NEG", "environmental", "low", "inference", {"year": by}, "seller", [src(d, "build_year"), src(asb, "asbestos_present")])


def r_cadastre_owner_facts(docs, ctx):
    deed = by_type(docs, "deed")
    if deed and "cadastral_ref" not in deed.fields:
        yield F("LEG-CADASTRE", "legal", "low", "action", {}, "notary",
                [{"doc_id": deed.id, "filename": deed.filename, "page": 1, "excerpt": ""}])


def r_deed_after_docs(docs, ctx):
    deed = by_type(docs, "deed")
    dd = val(deed, "deed_date")
    if not dd:
        return
    for d in docs:
        if d.doc_type == "asbestos" and (ad := val(d, "attest_date")) and ad > dd:
            yield F("X-DATES", "documentation", "medium", "inference", {"attest": ad, "deed": dd}, "notary",
                    [src(d, "attest_date"), src(deed, "deed_date")])


# Every rule id a finding can carry; tests check that each one has title/detail text in every language.
RULE_IDS = [
    "DOC-EPC", "DOC-ASBESTOS", "DOC-ELECTRICAL", "DOC-SOIL", "DOC-DEED", "DOC-OCR", "DOC-OCR-LOWQ", "DOC-OCR-USED", "DOC-WARN",
    "DOC-UNK", "EPC-EXPIRED", "EPC-OLD", "EPC-LABEL-MISMATCH", "EPC-POOR", "ASB-PRESENT", "ASB-CLEAR", "ASB-UNCLEAR",
    "ASB-OLD-NEG", "ELEC-NONCONFORM", "ELEC-OLD", "SOIL-POLLUTION", "SOIL-CLEAR", "SOIL-UNCLEAR", "CAD-UNBUILT", "X-CADASTRE",
    "X-ADDRESS", "X-SURFACE", "URB-EXT-NOPERMIT", "URB-NO-INFO", "X-BUILDYEAR", "LEG-CADASTRE", "X-DATES",
]

RULES = [
    r_missing_docs, r_unreadable, r_epc_validity, r_epc_label, r_asbestos, r_electrical, r_address,
    r_surface, r_extension_permit, r_urbanism_info, r_build_year, r_old_house_asbestos,
    r_cadastre_owner_facts, r_deed_after_docs, r_soil, r_cadastre,
]


def run_rules(docs: list[DocView], ctx: dict | None = None) -> list[F]:
    out: list[F] = []
    for rule in RULES:
        out.extend(rule(docs, ctx or {}))
    return out
