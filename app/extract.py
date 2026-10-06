"""Structured field extraction. Every field carries its page and verbatim excerpt (traceability).

Regex extractors are the deterministic baseline; an optional LLM pass fills gaps, and its
output is only accepted when the quoted excerpt is verifiably present in the page text.
"""
from __future__ import annotations

import datetime as dt
import json
import re

from . import config

Field = dict  # {"value": Any, "page": int (1-based), "excerpt": str}

MONTHS = {
    "januari": 1, "februari": 2, "maart": 3, "april": 4, "mei": 5, "juni": 6, "juli": 7,
    "augustus": 8, "september": 9, "oktober": 10, "november": 11, "december": 12,
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "décembre": 12, "decembre": 12,
    "january": 1, "february": 2, "march": 3, "may": 5, "june": 6, "july": 7, "august": 8,
    "october": 10, "december_": 12,
}
DATE_RE = (
    r"(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}(?:er)?\s+[A-Za-zéèûô]+\s+\d{4})"
)


def parse_date(s: str) -> dt.date | None:
    s = s.strip().lower()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            return dt.date.fromisoformat(s)
        m = re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})", s)
        if m:
            return dt.date(int(m[3]), int(m[2]), int(m[1]))
        m = re.fullmatch(r"(\d{1,2})(?:er)?\s+([a-zéèûô]+)\s+(\d{4})", s)
        if m and m[2] in MONTHS:
            return dt.date(int(m[3]), MONTHS[m[2]], int(m[1]))
    except ValueError:
        return None
    return None


def parse_number(s: str) -> float | None:
    s = s.replace(" ", "").replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _excerpt(text: str, m: re.Match, pad: int = 60) -> str:
    a, b = max(0, m.start() - pad), min(len(text), m.end() + pad)
    return " ".join(text[a:b].split())


def find(pages: list[str], pattern: str, group: int = 1, flags=re.I) -> tuple[str, int, str] | None:
    for i, text in enumerate(pages):
        m = re.search(pattern, text, flags)
        if m:
            return m.group(group), i + 1, _excerpt(text, m)
    return None


def _put(fields: dict, name: str, hit, conv=lambda x: x):
    if hit:
        val = conv(hit[0])
        if val is not None:
            fields[name] = {"value": val, "page": hit[1], "excerpt": hit[2]}


def _iso(s: str) -> str | None:
    d = parse_date(s)
    return d.isoformat() if d else None


SURF = r"(\d[\d.\s]*(?:,\d+)?)\s*(?:m²|m2|m\s*2|m\?)"
ADDR = (
    r"((?:[A-Z][\w'’\-]+\s){1,4}(?:straat|laan|weg|plein|lei|steenweg|dreef|rue|avenue|boulevard|chaussée)"
    r"\w*\s+\d+\w?(?:\s*,?\s*\d{4}\s+[A-Z][\w\-]+)?)"
)
ADDR_FR = (
    r"((?:Rue|Avenue|Boulevard|Chaussée|Place|Chemin|Quai|Allée)\s+(?:de la |du |des |de l'|d')?[A-ZÉ][\w'’\-]+(?:\s+[A-ZÉ][\w\-]+)*"
    r"\s*,?\s*\d+\w?(?:\s*,?\s*\d{4}\s+[A-ZÉ][\w\-]+)?)"
)
ADDR_ALT = r"((?:[A-Z][\w'’\-]*(?:straat|laan|weg|plein|lei|steenweg|dreef))\s+\d+\w?(?:\s*,?\s*\d{4}\s+[A-Z][\w\-]+)?)"


def _common(pages: list[str], f: dict) -> None:
    _put(f, "address", find(pages, r"(?i:adres|adresse|address|gelegen te|situé à|pand)\s*:?\s*" + ADDR_ALT, flags=0)
         or find(pages, ADDR_ALT, flags=0)
         or find(pages, r"(?i:adresse|situé à|sis à|situé)\s*:?\s*" + ADDR_FR, flags=0)
         or find(pages, ADDR_FR, flags=0))
    _put(f, "build_year", find(pages, r"(?:bouwjaar|jaar van bouw|année de construction|built in|construit en)\D{0,15}((?:18|19|20)\d{2})"), int)


def extract_epc(pages: list[str]) -> dict:
    f: dict = {}
    _common(pages, f)
    _put(f, "epc_score", find(pages, r"(?:energiescore|spec\w*\s+energieverbruik|score|consommation)\D{0,40}?(\d{2,4})\s*kWh/m²"), float)
    if "epc_score" not in f:
        _put(f, "epc_score", find(pages, r"(\d{2,4})\s*kWh/m²"), float)
    _put(f, "epc_label", find(pages, r"(?i:energielabel|label|classe(?: énergétique)?)\s*:?\s*([A-F]\+{0,2})\b", flags=0), str.upper)
    _put(f, "epc_number", find(pages, r"(\d{8}-\d{7})"))
    _put(f, "epc_valid_until", find(pages, r"(?:geldig tot|valable jusqu'au|valid until)\s*:?\s*" + DATE_RE), _iso)
    _put(f, "epc_issue_date", find(pages, r"(?:opgesteld op|datum van opmaak|date d'établissement|issued on|datum)\s*:?\s*" + DATE_RE), _iso)
    _put(f, "surface_m2", find(pages, r"(?:bruikbare vloeroppervlakte|vloeroppervlakte|surface utile|useful floor area)\D{0,20}?" + SURF), parse_number)
    _put(f, "extension_m2", find(pages, r"(?:uitbreiding|extension|aanbouw)\D{0,40}?" + SURF), parse_number)
    return f


def extract_deed(pages: list[str]) -> dict:
    f: dict = {}
    _common(pages, f)
    _put(f, "surface_m2", find(pages, r"(?:bewoonbare oppervlakte|woonoppervlakte|oppervlakte van|superficie (?:habitable )?de|surface de)\D{0,20}?" + SURF), parse_number)
    _put(f, "cadastral_ref", find(pages, r"(?:sectie|section)\s+([A-Z]\s+(?:nummer|numéro|n°|nr\.?)\s*\d+(?:/\w+)?)"), lambda s: " ".join(s.upper().split()))
    _put(f, "deed_date", find(pages, r"(?:verleden op|passé le|dd\.|datum van de akte|date)\s*:?\s*" + DATE_RE), _iso)
    _put(f, "seller", find(pages, r"(?i:\b(?:verkoper|vendeur)\b)\s*:?\s*([A-ZÉ][^\n,;.]{3,60})", flags=0))
    _put(f, "buyer", find(pages, r"(?i:\b(?:koper|acquéreur)\b)\s*:?\s*([A-ZÉ][^\n,;.]{3,60})", flags=0))
    _put(f, "extension_mentioned", find(pages, r"((?:uitbreiding|aanbouw|extension|verbouwing|transformation)[^\n.]{0,80})"), lambda s: True)
    _put(f, "extension_m2", find(pages, r"(?:uitbreiding|extension|aanbouw)\D{0,40}?" + SURF), parse_number)
    _put(f, "permit_mentioned", find(pages, r"((?:stedenbouwkundige vergunning|bouwvergunning|omgevingsvergunning|permis d'urbanisme|vergunning)[^\n.]{0,80})"), lambda s: True)
    _put(f, "urbanism_info", find(pages, r"((?:stedenbouwkundig uittreksel|uittreksel uit het vergunningenregister|vergunningenregister|renseignements urbanistiques)[^\n.]{0,80})"), lambda s: True)
    _put(f, "pre_emption_or_conditions", find(pages, r"(voorkooprecht|droit de préemption)[^\n.]{0,60}"), lambda s: True)
    return f


ASB_NEG = re.compile(r"\b(geen|niet|zonder|pas de|aucun\w*|sans|no|not|free of)\b|asbestveilig|asbestvrij", re.I)
ASB_POS = re.compile(
    r"asbest\w*\s+(?:werd\s+)?(?:aangetroffen|aanwezig|vastgesteld|gevonden)|asbestverdacht\w*|"
    r"asbesthoudende\s+\w+(?:\s+\w+)?\s+(?:aangetroffen|aanwezig|vastgesteld)|aanwezigheid van asbest|"
    r"(?:werd|werden)\s+asbest\w*\s+\w*\s*(?:aangetroffen|vastgesteld)|"
    r"amiante\s+(?:présent|détecté|décelé|identifié)|présence d'amiante|asbestos\s+(?:was\s+)?(?:found|present|detected)",
    re.I,
)


def extract_asbestos(pages: list[str]) -> dict:
    """Decide per sentence so that 'geen asbest aangetroffen' is never read as a positive finding."""
    f: dict = {}
    _common(pages, f)
    _put(f, "attest_number", find(pages, r"(?:attestnummer|numéro)\s*:?\s*([A-Z0-9\-/]{6,})", flags=0))
    _put(f, "attest_date", find(pages, r"(?:datum|date|opgesteld op)\s*:?\s*" + DATE_RE), _iso)
    pos = neg = None
    for i, text in enumerate(pages):
        for sent in re.split(r"(?<=[.!?])\s+|\n", text):
            if not re.search(r"asbest|amiante|asbestos", sent, re.I):
                continue
            hit = (True, i + 1, " ".join(sent.split()))
            if ASB_POS.search(sent) and not ASB_NEG.search(sent):
                pos = pos or hit
            elif ASB_NEG.search(sent) and not pos:
                neg = neg or (False, i + 1, " ".join(sent.split()))
    chosen = pos or neg
    if chosen:
        f["asbestos_present"] = {"value": chosen[0], "page": chosen[1], "excerpt": chosen[2]}
    return f


def extract_electrical(pages: list[str]) -> dict:
    f: dict = {}
    _common(pages, f)
    nonc = find(pages, r"(niet[\s\-]?conform\w*|non[\s\-]conforme|niet in overeenstemming|inbreuken? (?:vastgesteld|aangetroffen))")
    conf = find(pages, r"((?:installatie\s+(?:is\s+)?)?conform(?:\s+(?:aan|met)\s+(?:de\s+)?(?:arei|rgie|reglementering))?|conforme\b)")
    if nonc:
        _put(f, "electrical_conform", nonc, lambda s: False)
    elif conf:
        _put(f, "electrical_conform", conf, lambda s: True)
    _put(f, "inspection_date", find(pages, r"(?:datum (?:van )?(?:de )?(?:keuring|controle|bezoek)|date de (?:la )?visite|keuring(?:sdatum)?|date)\s*:?\s*" + DATE_RE), _iso)
    _put(f, "installation_year", find(pages, r"(?:installatie|installation)\D{0,30}?((?:19|20)\d{2})"), int)
    return f


EXTRACTORS = {"epc": extract_epc, "deed": extract_deed, "asbestos": extract_asbestos, "electrical": extract_electrical}

LLM_FIELDS = {
    "epc": ["address", "epc_score", "epc_label", "epc_valid_until", "surface_m2", "build_year"],
    "deed": ["address", "surface_m2", "cadastral_ref", "deed_date", "seller", "buyer", "build_year"],
    "asbestos": ["address", "attest_date", "asbestos_present"],
    "electrical": ["address", "inspection_date", "electrical_conform"],
}


def llm_fill(doc_type: str, pages: list[str], fields: dict) -> dict:
    """Optionally fill missing fields with an LLM. Output kept only if the excerpt is verbatim in the page."""
    if not config.ANTHROPIC_API_KEY or doc_type not in LLM_FIELDS:
        return fields
    missing = [n for n in LLM_FIELDS[doc_type] if n not in fields]
    if not missing:
        return fields
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        body = "\n\n".join(f"[PAGE {i + 1}]\n{t}" for i, t in enumerate(pages))[:60000]
        msg = client.messages.create(
            model=config.LLM_MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": (
                f"Belgian property document of type '{doc_type}'. Extract ONLY these fields if explicitly present: {missing}.\n"
                "Dates as ISO YYYY-MM-DD, surfaces as numbers in m², booleans as true/false. "
                'Return strict JSON: {"field": {"value": ..., "page": <int>, "excerpt": "<verbatim text copied from the page>"}}. '
                "Omit fields not present. Never guess.\n\n" + body)}],
        )
        text = msg.content[0].text
        data = json.loads(text[text.index("{"): text.rindex("}") + 1])
    except Exception:  # LLM is best-effort; baseline stays valid
        return fields
    for name, item in data.items():
        if name not in missing or not isinstance(item, dict):
            continue
        page, excerpt = item.get("page"), " ".join(str(item.get("excerpt", "")).split())
        if isinstance(page, int) and 1 <= page <= len(pages) and excerpt and excerpt in " ".join(pages[page - 1].split()):
            fields[name] = {"value": item.get("value"), "page": page, "excerpt": excerpt, "source": "llm"}
    return fields


def extract(doc_type: str, pages: list[str]) -> dict:
    fn = EXTRACTORS.get(doc_type)
    fields = fn(pages) if fn else {}
    return llm_fill(doc_type, pages, fields)
