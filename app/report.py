"""PDF report. Every finding states its kind (fact / AI inference / potential risk / recommended action) and its sources."""
from __future__ import annotations

import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import Case
from .rules import RULESET_VERSION

KIND = {"fact": "Feit uit document", "inference": "AI-inferentie", "risk": "Mogelijk risico", "action": "Aanbevolen actie"}
SEV_COLOR = {"high": colors.HexColor("#b91c1c"), "medium": colors.HexColor("#c2410c"), "low": colors.HexColor("#a16207"), "info": colors.HexColor("#475569")}
DISCLAIMER = (
    "Dit rapport is een hulpmiddel bij het nazicht van een vastgoeddossier en vormt geen juridisch, notarieel, "
    "architecturaal of technisch advies. Conclusies moeten door een bevoegde professional worden bevestigd. "
    "Les conclusions de ce rapport doivent être validées par un professionnel agréé."
)


def build_pdf(case: Case) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
                            title=f"Due diligence – {case.title}")
    ss = getSampleStyleSheet()
    small = ss["BodyText"].clone("small", fontSize=8.5, leading=11)
    story = [Paragraph("Property Due Diligence Report", ss["Title"]), Paragraph(escape(case.title), ss["Heading2"])]
    story.append(Paragraph(escape(f"Adres: {case.address or '-'} · Regio: {case.region} · Regelset {RULESET_VERSION}"), small))
    story.append(Paragraph(escape(f"Geanalyseerd: {case.analyzed_at:%Y-%m-%d %H:%M} UTC" if case.analyzed_at else "Niet geanalyseerd"), small))
    story.append(Spacer(1, 10))

    sc = case.scores or {"domains": {}, "overall": 0, "level": "low"}
    rows = [["Property Risk Score", f"{sc['overall']}/100 ({sc['level']})"]] + [[d.capitalize(), f"{v}/100"] for d, v in sc["domains"].items()]
    t = Table(rows, colWidths=[7 * cm, 5 * cm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0"))]))
    story += [t, Spacer(1, 12), Paragraph("Documenten", ss["Heading3"])]
    for d in case.documents:
        story.append(Paragraph(escape(f"• {d.filename} → {d.doc_type} (vertrouwen {d.classification_confidence:.0%})"), small))

    story.append(Paragraph("Bevindingen", ss["Heading3"]))
    findings = sorted(case.findings, key=lambda f: ["high", "medium", "low", "info"].index(f.severity))
    for f in findings:
        if f.review_status == "dismissed":
            continue
        color = SEV_COLOR[f.severity].hexval()[2:]
        status = {"confirmed": " ✔ gevalideerd door professional", "pending": " (nog niet gevalideerd)"}.get(f.review_status, "")
        story.append(Paragraph(f'<font color="#{color}"><b>[{f.severity.upper()}]</b></font> <b>{escape(f.title)}</b> — '
                               f'<i>{KIND.get(f.kind, f.kind)} · {f.domain}</i>{status}', ss["BodyText"]))
        story.append(Paragraph(escape(f.detail), small))
        if f.recommendation:
            story.append(Paragraph(escape(f"Aanbeveling: {f.recommendation}"), small))
        for s in f.sources:
            ex = f" — “{s['excerpt']}”" if s.get("excerpt") else ""
            story.append(Paragraph(escape(f"Bron: {s['filename']}, p.{s['page']}{ex}"), small))
        story.append(Paragraph(escape(f"Regel {f.rule_id} · {f.rule_version}"), small))
        story.append(Spacer(1, 6))

    questions: dict[str, list[str]] = {}
    for f in findings:
        if f.question_for and f.recommendation and f.review_status != "dismissed":
            questions.setdefault(f.question_for, []).append(f.recommendation)
    if questions:
        story.append(Paragraph("Vragen en acties per partij", ss["Heading3"]))
        names = {"notary": "Notaris", "seller": "Verkoper", "syndic": "Syndicus"}
        for who, qs in questions.items():
            story.append(Paragraph(f"<b>{names.get(who, who)}</b>", small))
            for q in dict.fromkeys(qs):
                story.append(Paragraph(escape(f"• {q}"), small))

    story += [Spacer(1, 14), Paragraph(escape(DISCLAIMER), small)]
    doc.build(story)
    return buf.getvalue()
