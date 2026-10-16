"""Renders the legal pages from app/legal_texts.py. Unknown facts are shown as visible markers, never invented."""
from html import escape

from markupsafe import Markup

from . import config, i18n
from .legal_texts import DOCS, TEXTS, TITLES, VERSION


def titles(lang: str) -> dict:
    return TITLES[lang]


def _trial_label(lang: str) -> str:
    """'3 jours', or '1 jour (particuliers) / 3 jours (professionnels)' when the two account types differ."""
    ind, pro = config.TRIAL_DAYS_INDIVIDUAL, config.TRIAL_DAYS
    if ind == pro or not ind or not pro:
        return i18n.t("trial.days", lang, n=ind or pro)
    return i18n.t("trial.split", lang, individual=i18n.t("trial.days", lang, n=ind), professional=i18n.t("trial.days", lang, n=pro))


def _values(lang: str) -> dict:
    def fact(value: str, what: str) -> str:
        return escape(value) if value else f'<mark class="todo">[{escape(i18n.t("legal.todo", lang, what=what))}]</mark>'
    return {
        "company": fact(config.COMPANY_NAME, {"fr": "dénomination", "nl": "naam", "en": "name"}[lang]),
        "address": fact(config.COMPANY_ADDRESS, {"fr": "adresse", "nl": "adres", "en": "address"}[lang]),
        "enterprise": fact(config.COMPANY_ENTERPRISE_NUMBER, {"fr": "numéro BCE/TVA", "nl": "KBO/btw-nummer", "en": "BCE/VAT number"}[lang]),
        "email": fact(config.CONTACT_EMAIL, "e-mail"),
        "phone": fact(config.COMPANY_PHONE, {"fr": "téléphone", "nl": "telefoon", "en": "phone"}[lang]),
        "hosting": fact(config.HOSTING_PROVIDER, "hosting"),
        "hosting_region": fact(config.HOSTING_REGION, {"fr": "région", "nl": "regio", "en": "region"}[lang]),
        "todo": f'<mark class="todo">[{escape(i18n.t("legal.todo_decision", lang))}]</mark>',
        "minutes": escape(str(config.PROCESSING_PROMISE_MINUTES)),
        "trial_days": escape(_trial_label(lang)), "trial_dossiers": escape(str(config.TRIAL_DOSSIERS)),
    }


def _enabled() -> set:
    return {name for name, on in (("stripe", config.STRIPE_SECRET_KEY), ("ai", config.ANTHROPIC_API_KEY), ("smtp", config.MAIL_ENABLED), ("trial", config.TRIAL_DAYS > 0 or config.TRIAL_DAYS_INDIVIDUAL > 0)) if on}


def render(doc: str, lang: str) -> list[dict]:
    """[{title, blocks: [("p"|"ul", Markup | [Markup])]}]; consecutive bullets are grouped in one list."""
    vals, on = _values(lang), _enabled()
    out = []
    for title, items in TEXTS[lang][doc]:
        blocks: list = []
        for item in items:
            if isinstance(item, tuple):
                feature, item = item
                if feature not in on:
                    continue
            bullet = item.startswith("- ")
            html = Markup(_fill(str(escape(item[2:] if bullet else item)), vals))
            if bullet:
                if blocks and blocks[-1][0] == "ul":
                    blocks[-1][1].append(html)
                else:
                    blocks.append(("ul", [html]))
            else:
                blocks.append(("p", html))
        out.append({"title": title, "blocks": blocks})
    return out


def _fill(text: str, vals: dict) -> str:
    for key, value in vals.items():
        text = text.replace("{" + key + "}", value)
    return text


__all__ = ["DOCS", "VERSION", "render", "titles"]
