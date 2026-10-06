"""Versioned regulatory + cross-document rules (Flanders MVP).

Each rule returns findings with: domain, severity, kind (fact|inference|risk|action),
sources (doc/page/excerpt), rule_id and rule_version. Rules are decision support only;
legal_basis strings are pointers to verify, not legal advice.
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


@dataclass
class F:
    rule_id: str
    domain: str  # legal|urbanistic|energy|technical|environmental|documentation
    severity: str  # info|low|medium|high
    kind: str
    title: str
    detail: str
    recommendation: str = ""
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

REQUIRED = {
    "epc": ("EPC (energieprestatiecertificaat)", "energy", "high",
            "Verplicht bij verkoop in Vlaanderen en te vermelden in de aankondiging."),
    "asbestos": ("Asbestattest", "environmental", "high",
                 "In Vlaanderen verplicht bij verkoop van gebouwen met bouwvergunning van vóór 2001."),
    "electrical": ("Keuringsverslag elektrische installatie", "technical", "medium",
                   "Keuring (AREI) is vereist bij verkoop van een woning; ontbreken bemoeilijkt de onderhandeling."),
    "deed": ("Akte / compromis", "legal", "medium", "Basisdocument voor eigendom, oppervlakte en vergunningsverklaringen."),
}


def r_missing_docs(docs, ctx):
    present = {d.doc_type for d in docs}
    for t, (label, domain, sev, why) in REQUIRED.items():
        if t not in present:
            asb_note = ""
            if t == "asbestos":
                by = next((val(d, "build_year") for d in docs if val(d, "build_year")), None)
                if by and by >= 2001:
                    sev, asb_note = "low", f" Bouwjaar {by} (≥ 2001): attest mogelijk niet vereist — te bevestigen."
            yield F(f"DOC-{t.upper()}", "documentation", sev, "action", f"Ontbrekend document: {label}",
                    why + asb_note, f"Vraag het document op bij de verkoper/notaris.",
                    "seller" if t != "deed" else "notary")


def r_unreadable(docs, ctx):
    for d in docs:
        if sum(len(p) for p in d.pages) < 80:
            yield F("DOC-OCR", "documentation", "medium", "risk", f"Document niet leesbaar: {d.filename}",
                    "Geen of nauwelijks tekst gevonden (gescand document zonder OCR).",
                    "Lever een doorzoekbare PDF aan of activeer OCR.", "", [{"doc_id": d.id, "filename": d.filename, "page": 1, "excerpt": ""}])
        elif d.doc_type == "unknown":
            yield F("DOC-UNK", "documentation", "low", "action", f"Documenttype niet herkend: {d.filename}",
                    "Het document kon niet automatisch geklasseerd worden.", "Controleer manueel of het relevant is.", "",
                    [{"doc_id": d.id, "filename": d.filename, "page": 1, "excerpt": ""}])


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
        yield F("EPC-EXPIRED", "energy", "high", "risk", "EPC verlopen",
                f"Het EPC is geldig tot {until} en dus niet meer geldig (geldigheid 10 jaar).",
                "Vraag een nieuw EPC aan vóór de verkoop.", "seller", [src(d, "epc_valid_until")])
    elif not until and (issue := val(d, "epc_issue_date")):
        if dt.date.fromisoformat(issue) < _today().replace(year=_today().year - 10):
            yield F("EPC-OLD", "energy", "high", "risk", "EPC ouder dan 10 jaar",
                    f"EPC opgesteld op {issue}; de geldigheid bedraagt 10 jaar.", "Vraag een nieuw EPC aan.", "seller", [src(d, "epc_issue_date")])


def r_epc_label(docs, ctx):
    d = by_type(docs, "epc")
    if not d:
        return
    score, label = val(d, "epc_score"), val(d, "epc_label")
    if score is not None and label and _label_for(score) != label[0]:
        yield F("EPC-LABEL-MISMATCH", "energy", "medium", "inference", "Label en score zijn inconsistent",
                f"Score {score:.0f} kWh/m² komt overeen met label {_label_for(score)}, maar het document vermeldt label {label}.",
                "Controleer het EPC in de officiële EPC-databank.", "seller", [src(d, "epc_score"), src(d, "epc_label")])
    lab = (label or (_label_for(score) if score is not None else "") or "")[:1]
    if lab in ("E", "F"):
        sev = "high" if lab == "F" else "medium"
        yield F("EPC-POOR", "energy", sev, "risk", f"Slechte energieprestatie (label {lab})",
                "Hoog energieverbruik: verwacht aanzienlijke renovatiekosten en mogelijke renovatieverplichtingen voor de koper in Vlaanderen.",
                "Laat een renovatieraming opmaken en bekijk de renovatieverplichting (E/F-labels).", "notary",
                [src(d, "epc_label" if "epc_label" in d.fields else "epc_score")])


# --- environmental / technical --------------------------------------------------------------

def r_asbestos(docs, ctx):
    d = by_type(docs, "asbestos")
    if not d:
        return
    if val(d, "asbestos_present") is True:
        yield F("ASB-PRESENT", "environmental", "high", "risk", "Asbest aangetroffen of vermoed",
                "Het attest meldt asbest of asbestverdachte materialen. Dit brengt saneringskosten en veiligheidsmaatregelen met zich mee.",
                "Vraag het inventarisrapport, de locatie en een kostenraming voor beheer/verwijdering.", "seller", [src(d, "asbestos_present")])
    elif val(d, "asbestos_present") is False:
        yield F("ASB-CLEAR", "environmental", "info", "fact", "Geen asbest vermeld in het attest", "Het attest vermeldt geen asbest.", "", "", [src(d, "asbestos_present")])
    elif "asbestos_present" not in d.fields:
        yield F("ASB-UNCLEAR", "environmental", "medium", "risk", "Asbestresultaat niet eenduidig",
                "Het resultaat kon niet betrouwbaar uit het attest gehaald worden.", "Manuele controle vereist.", "", [{"doc_id": d.id, "filename": d.filename, "page": 1, "excerpt": ""}])


def r_electrical(docs, ctx):
    d = by_type(docs, "electrical")
    if not d:
        return
    if val(d, "electrical_conform") is False:
        yield F("ELEC-NONCONFORM", "technical", "high", "risk", "Elektrische installatie niet conform",
                "Het keuringsverslag vermeldt inbreuken. Bij verkoop moet de koper de installatie binnen een wettelijke termijn laten regulariseren (te verifiëren: 18 maanden).",
                "Vraag een offerte voor regularisatie en bespreek de kosten in de prijsonderhandeling.", "seller", [src(d, "electrical_conform")])
    ins = val(d, "inspection_date")
    if ins and dt.date.fromisoformat(ins) < _today().replace(year=_today().year - 25):
        yield F("ELEC-OLD", "technical", "medium", "risk", "Keuringsverslag ouder dan 25 jaar",
                f"Keuring van {ins}; een conforme keuring blijft 25 jaar geldig (te verifiëren).", "Vraag een nieuwe keuring.", "seller", [src(d, "inspection_date")])


# --- cross-document -------------------------------------------------------------------------

def r_address(docs, ctx):
    items = [(d, d.fields["address"]["value"]) for d in docs if "address" in d.fields]
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = _norm_addr(items[i][1]), _norm_addr(items[j][1])
            if a and b and len(a & b) / min(len(a), len(b)) < 0.6:
                yield F("X-ADDRESS", "legal", "high", "inference", "Adressen komen niet overeen tussen documenten",
                        f"'{items[i][1]}' ({items[i][0].filename}) vs '{items[j][1]}' ({items[j][0].filename}).",
                        "Controleer of alle documenten bij hetzelfde pand horen.", "notary", [src(items[i][0], "address"), src(items[j][0], "address")])


def r_surface(docs, ctx):
    items = [(d, d.fields["surface_m2"]) for d in docs if "surface_m2" in d.fields]
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            (da, fa), (db, fb) = items[i], items[j]
            hi, lo = max(fa["value"], fb["value"]), min(fa["value"], fb["value"])
            if lo and (hi - lo) / lo > 0.10:
                yield F("X-SURFACE", "urbanistic", "high" if (hi - lo) / lo > 0.25 else "medium", "inference",
                        "Oppervlaktes komen niet overeen",
                        f"{fa['value']:.0f} m² ({da.filename}, p.{fa['page']}) vs {fb['value']:.0f} m² ({db.filename}, p.{fb['page']}): "
                        f"verschil {100 * (hi - lo) / lo:.0f}%. Definities (bewoonbaar vs. bruikbaar) kunnen verschillen, maar ook een niet-vergunde uitbreiding is mogelijk.",
                        "Vraag een stedenbouwkundig uittreksel en vergelijk met de vergunde plannen.", "notary", [src(da, "surface_m2"), src(db, "surface_m2")])


def r_extension_permit(docs, ctx):
    deed, epc = by_type(docs, "deed"), by_type(docs, "epc")
    ext_doc = next((d for d in (epc, deed) if d and (val(d, "extension_m2") or val(d, "extension_mentioned"))), None)
    if not ext_doc:
        return
    if not (deed and (val(deed, "permit_mentioned") or val(deed, "urbanism_info"))):
        name = "extension_m2" if "extension_m2" in ext_doc.fields else "extension_mentioned"
        yield F("URB-EXT-NOPERMIT", "urbanistic", "high", "risk", "Uitbreiding zonder aantoonbare vergunning",
                "Een uitbreiding/verbouwing wordt vermeld, maar de akte vermeldt geen bouw- of omgevingsvergunning.",
                "Vraag het vergunningenregister en de vergunde plannen op; overweeg regularisatie.", "notary", [src(ext_doc, name)])


def r_urbanism_info(docs, ctx):
    deed = by_type(docs, "deed")
    if deed and not (val(deed, "urbanism_info") or val(deed, "permit_mentioned")):
        yield F("URB-NO-INFO", "urbanistic", "medium", "risk", "Geen stedenbouwkundige inlichtingen in de akte",
                "De akte vermeldt geen stedenbouwkundige inlichtingen of vergunningen (vereist bij overdracht in Vlaanderen).",
                "Vraag de stedenbouwkundige inlichtingen en het vergunningenregister aan de verkoper/notaris.", "notary",
                [{"doc_id": deed.id, "filename": deed.filename, "page": 1, "excerpt": ""}])


def r_build_year(docs, ctx):
    items = [(d, d.fields["build_year"]) for d in docs if "build_year" in d.fields]
    years = {f["value"] for _, f in items}
    if len(years) > 1:
        yield F("X-BUILDYEAR", "legal", "medium", "inference", "Bouwjaar verschilt tussen documenten",
                "Vermelde bouwjaren: " + ", ".join(f"{f['value']} ({d.filename})" for d, f in items),
                "Controleer het bouwjaar (impact op asbest-, elektriciteits- en vergunningsvereisten).", "seller",
                [src(d, "build_year") for d, _ in items])


def r_old_house_asbestos(docs, ctx):
    asb = by_type(docs, "asbestos")
    by = next((val(d, "build_year") for d in docs if val(d, "build_year")), None)
    if asb and by and by < 2001 and val(asb, "asbestos_present") is False:
        d = next(d for d in docs if val(d, "build_year") == by)
        yield F("ASB-OLD-NEG", "environmental", "low", "inference", "Asbestvrij attest voor woning van vóór 2001",
                f"Bouwjaar {by}: asbesthoudend materiaal is in die periode gangbaar. Een negatief attest is mogelijk, maar verdient een controle van de attestering.",
                "Controleer of het attest door een erkend deskundige is opgesteld.", "seller", [src(d, "build_year"), src(asb, "asbestos_present")])


def r_cadastre_owner_facts(docs, ctx):
    deed = by_type(docs, "deed")
    if deed and "cadastral_ref" not in deed.fields:
        yield F("LEG-CADASTRE", "legal", "low", "action", "Kadastrale referentie niet gevonden",
                "Geen kadastrale sectie/nummer gedetecteerd in de akte.", "Verifieer de kadastrale gegevens.", "notary",
                [{"doc_id": deed.id, "filename": deed.filename, "page": 1, "excerpt": ""}])


def r_deed_after_docs(docs, ctx):
    deed = by_type(docs, "deed")
    dd = val(deed, "deed_date")
    if not dd:
        return
    for d in docs:
        if d.doc_type == "asbestos" and (ad := val(d, "attest_date")) and ad > dd:
            yield F("X-DATES", "documentation", "medium", "inference", "Asbestattest dateert van na de akte",
                    f"Attest {ad} vs akte {dd}: het attest moet vóór de verkoop beschikbaar zijn.",
                    "Controleer de chronologie met de notaris.", "notary", [src(d, "attest_date"), src(deed, "deed_date")])


RULES = [
    r_missing_docs, r_unreadable, r_epc_validity, r_epc_label, r_asbestos, r_electrical, r_address,
    r_surface, r_extension_permit, r_urbanism_info, r_build_year, r_old_house_asbestos,
    r_cadastre_owner_facts, r_deed_after_docs,
]


def run_rules(docs: list[DocView], ctx: dict | None = None) -> list[F]:
    out: list[F] = []
    for rule in RULES:
        out.extend(rule(docs, ctx or {}))
    return out
