"""Structured property summary and building timeline, built only from fields already extracted from the documents.

Nothing is invented: every item carries its source (document, page, excerpt) and unknown values are shown as such.
Texts come from the i18n catalogs, so the same data is readable in French, Dutch or English.
"""
from __future__ import annotations

import datetime as dt

from . import i18n, regions


def _f(doc, name):
    return (doc.fields or {}).get(name)


def _first(docs, name, types=None):
    for d in docs:
        if (types is None or d.doc_type in types) and _f(d, name):
            return d, _f(d, name)
    return None, None


def _src(doc, field) -> dict:
    return {"doc_id": doc.id, "filename": doc.filename, "page": field["page"], "excerpt": field["excerpt"]}


def _num(x: float) -> str:
    return f"{x:,.0f}".replace(",", " ")


def build(docs: list, lang: str) -> dict:
    """{'headline': str, 'items': [{key,label,value,flag,sources}], 'region': {...}}."""
    t = lambda key, **p: i18n.t(key, lang, **p)  # noqa: E731
    items: list[dict] = []
    head: list[str] = []

    def add(key, value, sources=(), flag=""):
        seen, unique = set(), []
        for src in sources:  # one reference per (document, page)
            if (src["filename"], src["page"]) not in seen:
                seen.add((src["filename"], src["page"]))
                unique.append(src)
        items.append({"key": key, "label": t(f"summary.item.{key}"), "value": value, "flag": flag, "sources": unique})

    # address
    d, f = _first(docs, "address")
    if f:
        add("address", f["value"], [_src(d, f)])

    # region (indicative: postal code of the address)
    info = regions.detect(docs)
    if info["code"]:
        value = t(f"region.{info['code']}") + f" ({t('summary.val.region_indic', postcode=info['postcode'])})"
        prelim = not regions.get(info["code"]).verified
        if prelim:
            value += f", {t('summary.val.region_prelim')}"
        add("region", value, [info["source"]] if info["source"] else [], "warn" if prelim or info["conflict"] else "")

    # construction year
    years = [(d, _f(d, "build_year")) for d in docs if _f(d, "build_year")]
    if years:
        distinct = sorted({f["value"] for _, f in years})
        if len(distinct) > 1:
            add("built", t("summary.val.built_many", list=" / ".join(str(y) for y in distinct)), [_src(d, f) for d, f in years], "warn")
        else:
            add("built", str(distinct[0]), [_src(years[0][0], years[0][1])])
            head.append(t("summary.head.built", year=distinct[0]))

    # surface areas: all distinct values with their documents
    surfaces = [(d, _f(d, "surface_m2")) for d in docs if _f(d, "surface_m2")]
    if surfaces:
        values = sorted({f["value"] for _, f in surfaces})
        text = " · ".join(f"{_num(f['value'])} m² ({d.filename})" for d, f in surfaces)
        differs = len(values) > 1 and (values[-1] - values[0]) / values[0] > 0.10
        if differs:
            text += f" — {t('summary.val.differs')}"
        add("surface", text, [_src(d, f) for d, f in surfaces], "warn" if differs else "")
        if not differs:
            head.append(t("summary.head.surface", m2=_num(values[0])))

    # energy certificate
    d, label = _first(docs, "epc_label", {"epc"})
    _, score = _first(docs, "epc_score", {"epc"})
    if d and (label or score):
        epc = d
        until = _f(epc, "epc_valid_until")
        lab = label["value"] if label else "?"
        text = t("summary.val.epc", label=lab, score=_num(score["value"]) if score else "?")
        if until:
            text += f", {t('summary.val.until', date=until['value'])}"
        add("epc", text, [_src(epc, x) for x in (label, score, until) if x])
        if label:
            head.append(t("summary.head.epc", label=lab))

    # electrical, asbestos, soil, cadastre
    d, f = _first(docs, "electrical_conform", {"electrical"})
    if f:
        ok = f["value"] is True
        add("electrical", t("summary.val.conform" if ok else "summary.val.nonconform"), [_src(d, f)], "" if ok else "bad")
        head.append(t("summary.head.elec_ok" if ok else "summary.head.elec_no"))
    d, f = _first(docs, "asbestos_present", {"asbestos"})
    if f:
        yes = f["value"] is True
        add("asbestos", t("summary.val.asb_yes" if yes else "summary.val.asb_no"), [_src(d, f)], "bad" if yes else "")
        head.append(t("summary.head.asb_yes" if yes else "summary.head.asb_no"))
    d, f = _first(docs, "soil_pollution_mentioned", {"soil"})
    if f:
        yes = f["value"] is True
        add("soil", t("summary.val.soil_yes" if yes else "summary.val.soil_no"), [_src(d, f)], "bad" if yes else "")
    d, f = _first(docs, "cadastral_ref")
    if f:
        add("cadastre", f["value"], [_src(d, f)])

    # extension (EPC or deed)
    d, f = _first(docs, "extension_m2")
    if f:
        add("extension", t("summary.val.ext_m2", m2=_num(f["value"])), [_src(d, f)], "warn")
        head.append(t("summary.head.ext", m2=_num(f["value"])))
    else:
        d, f = _first(docs, "extension_mentioned")
        if f:
            add("extension", t("summary.val.ext_yes"), [_src(d, f)], "warn")
            head.append(t("summary.head.ext_unspec"))

    # invoiced works
    invoices = [d for d in docs if d.doc_type == "invoice"]
    if invoices:
        total = sum(_f(d, "amount_eur")["value"] for d in invoices if _f(d, "amount_eur"))
        add("works", t("summary.val.works", n=len(invoices), total=_num(total)),
            [_src(d, _f(d, "invoice_date") or _f(d, "amount_eur")) for d in invoices if _f(d, "invoice_date") or _f(d, "amount_eur")])

    # urbanism
    ub = next((d for d in docs if d.doc_type == "urbanism"), None)
    if ub:
        bits = []
        if _f(ub, "planning_zone"):
            bits.append(_f(ub, "planning_zone")["value"])
        for name, key in (("infraction", "infraction"), ("flood_risk", "flood"), ("heritage", "heritage")):
            if _f(ub, name) and _f(ub, name)["value"] is True:
                bits.append(t(f"summary.val.{key}"))
        flagged = any(_f(ub, n) and _f(ub, n)["value"] is True for n in ("infraction", "flood_risk"))
        add("urbanism", ", ".join(bits) or t("summary.val.unknown"), [_src(ub, _f(ub, "planning_zone") or next(iter(ub.fields.values())))] if ub.fields else [],
            "bad" if flagged else "")

    # co-ownership
    cp = next((d for d in docs if d.doc_type == "copro"), None)
    if cp:
        bits = []
        if _f(cp, "reserve_eur"):
            bits.append(t("summary.val.reserve", amount=_num(_f(cp, "reserve_eur")["value"])))
        if _f(cp, "monthly_charges_eur"):
            bits.append(t("summary.val.charges", amount=_num(_f(cp, "monthly_charges_eur")["value"])))
        add("copro", ", ".join(bits) or t("summary.val.unknown"), [_src(cp, next(iter(cp.fields.values())))] if cp.fields else [])

    return {"headline": " · ".join(head), "items": items,
            "region": {"code": info["code"], "postcode": info["postcode"], "verified": regions.get(info["code"]).verified if info["code"] else None}}


# --- timeline ------------------------------------------------------------------------------

EVENTS = [  # (doc types, field, event kind)
    (("epc",), "epc_issue_date", "epc_issued"), (("epc",), "epc_valid_until", "epc_expires"),
    (("asbestos",), "attest_date", "asbestos_attest"), (("electrical",), "inspection_date", "electrical_inspection"),
    (("soil",), "soil_attest_date", "soil_attest"), (("deed",), "deed_date", "deed"), (("cadastre",), "extract_date", "cadastre_extract"),
    (("urbanism",), "info_date", "urbanism_info"), (("plan",), "plan_date", "plan"), (("copro",), "assembly_date", "copro_assembly"),
]


def timeline(docs: list, lang: str, today: dt.date | None = None) -> list[dict]:
    """Chronological events [{date, year_only, kind, label, filename, page, excerpt, flags}], oldest first."""
    today = today or dt.date.today()
    t = lambda key, **p: i18n.t(key, lang, **p)  # noqa: E731
    raw: list[tuple[dt.date, bool, str, str, object, dict]] = []

    def push(date, year_only, kind, label, doc, field):
        raw.append((date, year_only, kind, label, doc, field))

    for d in docs:
        for types, name, kind in EVENTS:
            f = _f(d, name)
            if d.doc_type in types and f:
                try:
                    push(dt.date.fromisoformat(f["value"]), False, kind, t(f"timeline.event.{kind}"), d, f)
                except (TypeError, ValueError):
                    pass
        if d.doc_type == "invoice" and _f(d, "invoice_date"):
            f = _f(d, "invoice_date")
            kinds = ", ".join(t(f"timeline.works.{k}") for k in (_f(d, "works_kinds") or {"value": []})["value"]) or "…"
            try:
                push(dt.date.fromisoformat(f["value"]), False, "works", t("timeline.event.works", kinds=kinds), d, f)
            except ValueError:
                pass
        if d.doc_type == "electrical" and _f(d, "installation_year"):
            f = _f(d, "installation_year")
            push(dt.date(int(f["value"]), 1, 1), True, "electrical_installed", t("timeline.event.electrical_installed"), d, f)
    years = [(d, _f(d, "build_year")) for d in docs if _f(d, "build_year")]
    if years:
        d, f = years[0]
        push(dt.date(int(f["value"]), 1, 1), True, "construction", t("timeline.event.construction"), d, f)
    build = next((r[0] for r in raw if r[2] == "construction"), None)
    out = []
    for date, year_only, kind, label, doc, f in sorted(raw, key=lambda r: (r[0], r[2] != "construction")):
        flags = []
        if build and kind != "construction" and date.year < build.year:
            flags.append("before_build")
        if kind == "epc_expires":
            flags.append("expired" if date < today else "upcoming")
        out.append({"date": str(date.year) if year_only else date.isoformat(), "year_only": year_only, "kind": kind, "label": label,
                    "filename": doc.filename, "page": f["page"], "excerpt": f["excerpt"], "flags": flags,
                    "flag_labels": [t(f"timeline.flag.{x}") for x in flags]})
    return out
