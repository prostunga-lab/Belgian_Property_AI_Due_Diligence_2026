"""Public demonstration report, built with the REAL analysis engine from synthetic documents (no customer data, nothing stored)."""
from __future__ import annotations

import datetime as dt

from . import classify, extract, regions, render
from .models import Case, Document, Finding
from .rules import DocView, run_rules
from .scoring import score

DOCS = {
    "akte-demo.pdf": """VERKOOPAKTE
Verleden op 12/03/2026 voor notaris Voorbeeld.
Verkoper: Voorbeeld Verkoper
Koper: Voorbeeld Koper
Pand gelegen te Voorbeeldstraat 12, 9000 Gent.
Kadastraal: sectie A nummer 123/B.
Bewoonbare oppervlakte van 185 m².
Bouwjaar 1975.
""",
    "epc-demo.pdf": """Energieprestatiecertificaat (EPC)
Certificaatnummer 20240101-0001234
Adres: Voorbeeldstraat 12, 9000 Gent
Energielabel: E
Energiescore 430 kWh/m²
Bruikbare vloeroppervlakte 240 m²
Uitbreiding van 32 m² (achterbouw)
Datum van opmaak 01/01/2024
Geldig tot 01/01/2034
Bouwjaar 1975
""",
    "asbest-demo.pdf": """Asbestattest
Voorbeeldstraat 12, 9000 Gent
Datum: 01/02/2026
Er werd asbest aangetroffen in de dakbedekking.
""",
    "keuring-demo.pdf": """Keuringsverslag elektrische installatie (AREI)
Adres: Voorbeeldstraat 12, 9000 Gent
Datum van keuring: 05/05/2000
Installatie niet conform.
""",
}


def build() -> Case:
    """A transient (never persisted) Case with documents and findings, ready for the page and the PDF builders."""
    docs, views = [], []
    for i, (name, text) in enumerate(DOCS.items(), 1):
        doc_type, conf = classify.classify([text], name)
        fields = extract.EXTRACTORS[doc_type]([text])  # deterministic extraction only: the demo never calls an external AI service
        docs.append(Document(id=i, filename=name, doc_type=doc_type, classification_confidence=conf, pages=[text], fields=fields, ocr_pages=[], warnings=[], ai_analysis=None))
        views.append(DocView(i, name, doc_type, [text], fields))
    info = regions.detect(views)
    findings = []
    for n, r in enumerate(run_rules(views, {"region_info": info}), 1):
        text = render.finding_text(r.rule_id, r.params, "en")
        findings.append(Finding(id=n, rule_id=r.rule_id, rule_version=r.rule_version, domain=r.domain, severity=r.severity, kind=r.kind, title=text["title"],
                                detail=text["detail"], recommendation=text["recommendation"], params=r.params, question_for=r.question_for, sources=r.sources,
                                review_status="pending"))
    return Case(id=0, title="Voorbeeldstraat 12, 9000 Gent", address="Voorbeeldstraat 12, 9000 Gent", region=info["code"] or "flanders", status="analyzed",
                scores=score(findings), documents=docs, findings=findings, ai_summary=None, analyzed_at=dt.datetime.now(dt.timezone.utc))
