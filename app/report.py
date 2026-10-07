"""PDF report in the reader's language (fr/nl/en). Every finding states its kind (fact / inference / risk / action) and its sources."""
from __future__ import annotations

import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .i18n import t
from .models import Case
from .render import finding_text
from .rules import RULESET_VERSION

SEV_COLOR = {"high": colors.HexColor("#b91c1c"), "medium": colors.HexColor("#c2410c"), "low": colors.HexColor("#a16207"), "info": colors.HexColor("#475569")}
SEV_ORDER = ["high", "medium", "low", "info"]


def build_pdf(case: Case, lang: str = "en") -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
                            title=f"Due diligence – {case.title}", lang=lang)
    ss = getSampleStyleSheet()
    small = ss["BodyText"].clone("small", fontSize=8.5, leading=11)
    story = [Paragraph(escape(t("pdf.title", lang)), ss["Title"]), Paragraph(escape(case.title), ss["Heading2"])]
    story.append(Paragraph(escape(t("pdf.address_line", lang, address=case.address or "-", region=t(f"region.{case.region}", lang), ruleset=RULESET_VERSION)), small))
    story.append(Paragraph(escape(t("pdf.analyzed", lang, when=f"{case.analyzed_at:%Y-%m-%d %H:%M}") if case.analyzed_at else t("pdf.not_analyzed", lang)), small))
    story.append(Spacer(1, 10))

    sc = case.scores or {"domains": {}, "overall": 0, "level": "low"}
    rows = [[t("pdf.score", lang), f"{sc['overall']}/100 ({t('level.' + sc['level'], lang)})"]] + \
           [[t(f"domain.{d}", lang), f"{v}/100"] for d, v in sc["domains"].items()]
    table = Table(rows, colWidths=[7 * cm, 5 * cm])
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                               ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0"))]))
    story += [table, Spacer(1, 12), Paragraph(escape(t("pdf.documents", lang)), ss["Heading3"])]
    for d in case.documents:
        story.append(Paragraph(escape("• " + t("pdf.doc_line", lang, filename=d.filename, type=t(f"doctype.{d.doc_type}", lang),
                                                 conf=f"{d.classification_confidence:.0%}")), small))

    ai = case.ai_summary
    if ai or any(d.ai_analysis for d in case.documents):
        story.append(Paragraph(escape(t("pdf.ai_title", lang)), ss["Heading3"]))
        if ai:
            story.append(Paragraph(escape(t("pdf.ai_global", lang, risk=ai.get("risque_global", "n/a"), summary=ai.get("synthese", ""))), small))
            for item in list(ai.get("incoherences") or []) + list(ai.get("budget_travaux_a_negocier") or []):
                story.append(Paragraph(escape(f"• {item}"), small))
        for d in case.documents:
            if d.ai_analysis and d.ai_analysis.get("synthese"):
                story.append(Paragraph(escape(f"{d.filename}: {d.ai_analysis['synthese']}"), small))

    story.append(Paragraph(escape(t("pdf.findings", lang)), ss["Heading3"]))
    rendered = []
    for f in sorted(case.findings, key=lambda f: (SEV_ORDER.index(f.severity), f.id)):
        if f.review_status == "dismissed":
            continue
        rendered.append((f, finding_text(f.rule_id, f.params, lang, {"title": f.title, "detail": f.detail, "recommendation": f.recommendation})))
    for f, text in rendered:
        color = SEV_COLOR[f.severity].hexval()[2:]
        status = {"confirmed": t("pdf.validated", lang), "pending": t("pdf.not_validated", lang)}.get(f.review_status, "")
        story.append(Paragraph(f'<font color="#{color}"><b>[{escape(t("severity." + f.severity, lang).upper())}]</b></font> <b>{escape(text["title"])}</b> — '
                               f'<i>{escape(t("kind." + f.kind, lang))} · {escape(t("domain." + f.domain, lang))}</i>{escape(status)}', ss["BodyText"]))
        story.append(Paragraph(escape(text["detail"]), small))
        if text["recommendation"]:
            story.append(Paragraph(escape(t("pdf.recommendation", lang, text=text["recommendation"])), small))
        for s in f.sources:
            line = t("pdf.source", lang, filename=s["filename"], page=s["page"]) + (" — " + t("ui.quoted", lang, text=s["excerpt"]) if s.get("excerpt") else "")
            story.append(Paragraph(escape(line), small))
        story.append(Paragraph(escape(t("pdf.rule", lang, rule=f.rule_id, version=f.rule_version)), small))
        story.append(Spacer(1, 6))

    questions: dict[str, list[str]] = {}
    for f, text in rendered:
        if f.question_for and text["recommendation"]:
            questions.setdefault(f.question_for, []).append(text["recommendation"])
    if questions:
        story.append(Paragraph(escape(t("pdf.questions", lang)), ss["Heading3"]))
        for who, qs in questions.items():
            story.append(Paragraph(f"<b>{escape(t('party.' + who, lang))}</b>", small))
            for q in dict.fromkeys(qs):
                story.append(Paragraph(escape(f"• {q}"), small))

    story += [Spacer(1, 14), Paragraph(escape(t("pdf.disclaimer", lang)), small)]
    doc.build(story)
    return buf.getvalue()
