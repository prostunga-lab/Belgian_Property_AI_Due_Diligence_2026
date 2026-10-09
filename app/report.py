"""PDF report in the reader's language (fr/nl/en). Every finding states its kind (fact / inference / risk / action) and its sources."""
from __future__ import annotations

import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import renovation
from . import summary as property_summary
from .i18n import t
from .models import Case
from .render import finding_text
from .rules import RULESET_VERSION

SEV_COLOR = {"high": colors.HexColor("#b91c1c"), "medium": colors.HexColor("#c2410c"), "low": colors.HexColor("#a16207"), "info": colors.HexColor("#475569")}
SEV_ORDER = ["high", "medium", "low", "info"]


def build_pdf(case: Case, lang: str = "en") -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                            title=f"Due diligence – {case.title}", lang=lang)
    ss = getSampleStyleSheet()
    small = ss["BodyText"].clone("small", fontSize=8.5, leading=11)
    title_style = ss["Title"].clone("t2", fontSize=16, leading=19, spaceAfter=2)
    story = [Paragraph(escape(t("pdf.title", lang)), title_style), Paragraph(escape(case.title), ss["Heading3"])]
    story.append(Paragraph(escape(t("pdf.address_line", lang, address=case.address or "-", region=t(f"region.{case.region}", lang), ruleset=RULESET_VERSION)), small))
    story.append(Paragraph(escape(t("pdf.analyzed", lang, when=f"{case.analyzed_at:%Y-%m-%d %H:%M}") if case.analyzed_at else t("pdf.not_analyzed", lang)), small))
    story.append(Spacer(1, 4))

    active = [f for f in case.findings if f.review_status != "dismissed"]
    ranked = sorted(active, key=lambda f: (SEV_ORDER.index(f.severity), f.id))
    texts = {f.id: finding_text(f.rule_id, f.params, lang, {"title": f.title, "detail": f.detail, "recommendation": f.recommendation}) for f in ranked}
    prop = property_summary.build(case.documents, lang)
    plan = renovation.build(active, case.documents, lang)
    story += _executive_summary(case, lang, ss, small, prop, plan, ranked, texts)
    story += [PageBreak(), Paragraph(escape(t("pdf.exec.detail_title", lang)), ss["Heading1"]), Paragraph(escape(t("pdf.documents", lang)), ss["Heading3"])]
    for d in case.documents:
        story.append(Paragraph(escape("• " + t("pdf.doc_line", lang, filename=d.filename, type=t(f"doctype.{d.doc_type}", lang),
                                                 conf=f"{d.classification_confidence:.0%}")), small))

    if prop["items"]:
        story.append(Paragraph(escape(t("summary.title", lang)), ss["Heading3"]))
        if prop["headline"]:
            story.append(Paragraph(f"<b>{escape(prop['headline'])}</b>", ss["BodyText"]))
        for it in prop["items"]:
            story.append(Paragraph(escape(f"• {it['label']} : {it['value']}"), small))
        story.append(Paragraph(escape(t("summary.disclaimer", lang)), small))
    events = property_summary.timeline(case.documents, lang)
    if events:
        story.append(Paragraph(escape(t("timeline.title", lang)), ss["Heading3"]))
        for e in events:
            flag = f" (!) {', '.join(e['flag_labels'])}" if e["flags"] else ""
            story.append(Paragraph(escape(f"• {e['date']} — {e['label']} ({e['filename']}, {t('ui.page_abbr', lang)}{e['page']}){flag}"), small))

    if plan["phases"]:
        story.append(Paragraph(escape(t("reno.title", lang) + " — " + t("reno.details", lang)), ss["Heading3"]))
        for ph in plan["phases"]:
            story.append(Paragraph(f"<b>{escape(ph['label'])}</b>" + (f" — {escape(ph['cost'])}" if ph["cost"] else ""), ss["BodyText"]))
            for it in ph["items"]:
                story.append(Paragraph(escape(f"• {it['title']} : {it['cost_full']} ({it['confidence_label']})"), small))
                story.append(Paragraph(escape(it["what"] + (" " + it["note"] if it["note"] else "")), small))
        story.append(Paragraph(escape(t("reno.disclaimer", lang)), small))

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
    rendered = [(f, texts[f.id]) for f in ranked]
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


def _executive_summary(case, lang, ss, small, prop, plan, ranked, texts) -> list:
    """Page 1: everything a reader needs without opening the rest, with the professional-advice reserve stated up front."""
    story = [Paragraph(escape(t("pdf.exec.title", lang)), ss["Heading2"])]
    reserve = Table([[Paragraph(escape(t("pdf.exec.reserve", lang)), small)]], colWidths=[17 * cm])
    reserve.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#b45309")), ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fef3c7")),
                                 ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story += [reserve, Spacer(1, 8)]

    sc = case.scores or {"domains": {}, "overall": 0, "level": "low"}
    level_color = {"high": "#b91c1c", "medium": "#c2410c", "low": "#166534"}[sc["level"]]
    story.append(Paragraph(f'{escape(t("pdf.score", lang))} : <font color="{level_color}"><b>{sc["overall"]}/100 — {escape(t("level." + sc["level"], lang))}</b></font>', ss["Heading3"]))
    if prop["headline"]:
        story.append(Paragraph(f"<b>{escape(prop['headline'])}</b>", ss["BodyText"]))
    doms = [[t(f"domain.{d}", lang), f"{v}/100"] for d, v in sc["domains"].items()]
    if doms:
        half = (len(doms) + 1) // 2
        grid = [[*(doms[i] if i < len(doms) else ["", ""]), *(doms[i + half] if i + half < len(doms) else ["", ""])] for i in range(half)]
        dt = Table(grid, colWidths=[4.5 * cm, 2.5 * cm, 4.5 * cm, 2.5 * cm])
        dt.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey), ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("ALIGN", (3, 0), (3, -1), "RIGHT")]))
        story += [Spacer(1, 4), dt]

    key = [f for f in ranked if f.severity in ("high", "medium")]
    story.append(Paragraph(escape(t("pdf.exec.key_findings", lang)), ss["Heading3"]))
    if key:
        for f in key[:5]:
            color = SEV_COLOR[f.severity].hexval()[2:]
            story.append(Paragraph(f'<font color="#{color}"><b>[{escape(t("severity." + f.severity, lang).upper())}]</b></font> {escape(texts[f.id]["title"])}', small))
        rest = len(ranked) - min(len(key), 5)
        if rest > 0:
            story.append(Paragraph(escape(t("pdf.exec.more", lang, n=rest)), small))
    else:
        story.append(Paragraph(escape(t("pdf.exec.no_key_findings", lang)), small))

    if plan["rows"]:
        story.append(Paragraph(escape(t("pdf.exec.actions", lang)), ss["Heading3"]))
        prio = {"high": colors.HexColor("#b91c1c"), "medium": colors.HexColor("#c2410c"), "low": colors.HexColor("#166534")}
        cell = ss["BodyText"].clone("cell", fontSize=8.5, leading=10.5)
        rows = [[t("reno.col.work", lang), t("reno.col.priority", lang), t("reno.col.estimate", lang)]]
        rows += [[Paragraph(escape(it["title"]), cell), it["priority_label"], it["cost"]] for it in plan["rows"]]
        if plan["total"]:
            rows.append([Paragraph(f"<b>{escape(t('reno.total', lang))}</b>", cell), "", plan["total"]])
        style = [("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                 ("ALIGN", (2, 0), (2, -1), "RIGHT"), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
        for n, it in enumerate(plan["rows"], 1):
            style += [("TEXTCOLOR", (1, n), (1, n), prio[it["priority"]]), ("FONTNAME", (1, n), (1, n), "Helvetica-Bold")]
        if plan["total"]:
            style.append(("FONTNAME", (2, len(rows) - 1), (2, len(rows) - 1), "Helvetica-Bold"))
        table = Table(rows, colWidths=[9 * cm, 3.5 * cm, 4.5 * cm], repeatRows=1)
        table.setStyle(TableStyle(style))
        story += [table, Paragraph(escape(" ".join(x for x in (plan["unestimated_text"], t("reno.priority_legend", lang), t("reno.disclaimer_short", lang)) if x)), small)]

    asks = list(dict.fromkeys(texts[f.id]["recommendation"] for f in key if texts[f.id]["recommendation"]))[:3]
    if asks:
        story.append(Paragraph(escape(t("pdf.exec.before_signing", lang)), ss["Heading3"]))
        for a in asks:
            story.append(Paragraph(escape(f"• {a}"), small))
    return story
