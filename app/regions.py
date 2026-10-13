"""Belgian region detection and per-region requirements.

The region is read from the postal code of the property address found in the documents. Postal-code ranges are a good
indicator, not a legal determination (a handful of municipalities sit on a border), so the result is always presented as
"indicative" and the source of the postal code is shown.

Only Flanders is covered by a rule set that has been checked against the product's reference documents. Brussels and
Wallonia use the same engine with their own list of required documents, flagged as PRELIMINARY: findings still run, but a
visible notice asks for professional validation. Nothing here is legal advice.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

FLANDERS, BRUSSELS, WALLONIA = "flanders", "brussels", "wallonia"

# (first, last, region); the first matching range wins.
_RANGES = [
    (1000, 1299, BRUSSELS),
    (1300, 1499, WALLONIA),   # Walloon Brabant
    (1500, 3999, FLANDERS),   # Flemish Brabant, Antwerp, Limburg
    (4000, 7999, WALLONIA),   # Liège, Namur, Hainaut, Luxembourg
    (8000, 9999, FLANDERS),   # West and East Flanders
]


@dataclass(frozen=True)
class Region:
    code: str
    required: tuple          # document types a seller is expected to provide
    asbestos_attest_required: bool
    verified: bool           # False = preliminary rule set, professional validation requested


REGIONS = {
    FLANDERS: Region(FLANDERS, ("epc", "asbestos", "electrical", "soil", "deed"), True, True),
    # Brussels and Wallonia: an asbestos attest is not required for a sale (to verify with the notary), the soil certificate is.
    BRUSSELS: Region(BRUSSELS, ("epc", "electrical", "soil", "deed", "urbanism"), False, False),
    WALLONIA: Region(WALLONIA, ("epc", "electrical", "soil", "deed"), False, False),
}
DEFAULT = REGIONS[FLANDERS]  # used when the region cannot be determined: the original (Flemish) behaviour

_POSTCODE = re.compile(r"(?<!\d)([1-9]\d{3})(?!\d)")


def from_postcode(code: int) -> str | None:
    for lo, hi, region in _RANGES:
        if lo <= code <= hi:
            return region
    return None


def postcode_of(address: str) -> int | None:
    """Last 4-digit group of an address string ('Kerkstraat 12, 9000 Gent' -> 9000); house numbers are shorter or earlier."""
    found = _POSTCODE.findall(address or "")
    return int(found[-1]) if found else None


def detect(docs) -> dict:
    """{'code': region|None, 'postcode': int|None, 'source': {...}|None, 'conflict': bool}. ``docs`` need .fields/.filename/.id."""
    seen: list[tuple[str, int, object]] = []
    for d in docs:
        f = (d.fields or {}).get("address")
        if not f:
            continue
        pc = postcode_of(str(f["value"]))
        region = from_postcode(pc) if pc else None
        if region:
            seen.append((region, pc, d))
    if not seen:
        return {"code": None, "postcode": None, "source": None, "conflict": False}
    regions = {r for r, _, _ in seen}
    first_region, pc, d = seen[0]
    f = d.fields["address"]
    return {"code": first_region, "postcode": pc, "conflict": len(regions) > 1,
            "source": {"doc_id": d.id, "filename": d.filename, "page": f["page"], "excerpt": f["excerpt"]}}


def get(code: str | None) -> Region:
    return REGIONS.get(code or "", DEFAULT)
