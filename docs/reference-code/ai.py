import json, os
from datetime import date
import anthropic
from . import prompts

_client = anthropic.Anthropic()  # lit ANTHROPIC_API_KEY
MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")

def _ask(system: str, user: str, max_tokens: int = 2000) -> str:
    r = _client.messages.create(
        model=MODEL, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in r.content if b.type == "text")

def _json(raw: str) -> dict:
    s, e = raw.find("{"), raw.rfind("}")
    return json.loads(raw[s : e + 1])

TYPES = ("peb", "electrique", "cadastre", "sol")

def classify(text: str) -> str:
    out = _ask(prompts.CLASSIFY, text[:3000], 10).strip().lower().strip(". ")
    return out if out in TYPES else "autre"

def analyze(doc_type: str, text: str) -> dict:
    system = {"peb": prompts.PEB, "electrique": prompts.ELEC, "cadastre": prompts.CADASTRE, "sol": prompts.SOL}[doc_type]
    user = f"Date du jour: {date.today().isoformat()}\n\nTEXTE DU DOCUMENT:\n{text[:30000]}"
    return _json(_ask(system, user))

def cross_check(results: list[dict]) -> dict:
    return _json(_ask(prompts.CROSS, json.dumps(results, ensure_ascii=False), 1200))
