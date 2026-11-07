"""The model writes "מה קרה" / "למה זה חשוב" for a batch of alerts in ONE call, and rates stories.

Numbers are checked per alert against that alert's own facts: an invented number in one alert
removes only that sentence, and the template sentence takes its place.
"""
from __future__ import annotations

import json
import logging
import re

from ..llm import prompts
from ..llm.base import LLMError, cached_generate, get_provider
from ..llm.validator import allowed_numbers, validate_fields
from ..telegram.send import esc
from .models import Alert

log = logging.getLogger(__name__)

TASK = """כתוב טקסט קצר להתראות בטלגרם. לכל פריט: "what" (מה קרה, משפט אחד) ו-"why" (למה זה חשוב לי, משפט אחד).
לסיפורים (kind=story) תן גם "rating": ציון חשיבות 1 עד 10 למשקיע לטווח בינוני בבורסה האמריקאית.
השתמש רק במספרים שמופיעים ב-facts של אותו פריט. אם יש group_note, השתמש בו ב-why.
אם אין הסבר בנתונים לתנועת מחיר, כתוב שאין עדיין הסבר. אל תנחש.

הפריטים:
{items}

החזר JSON: {{"items": [{{"id": "...", "what": "...", "why": "...", "rating": null}}]}}"""


def _plain(html_text: str) -> str:
    return re.sub(r"<[^>]+>", "", html_text).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")


def enrich(ctx, alerts: list[Alert]) -> str | None:
    """Mutates alerts in place. Returns the provider name, or None when templates are used."""
    if not alerts:
        return None
    try:
        provider = get_provider(ctx.cfg)
    except LLMError:
        return None
    if provider is None:
        return None
    items = []
    for i, a in enumerate(alerts[:10]):
        items.append({"id": f"a{i}", "kind": a.kind, "headline": _plain(a.headline), "facts": a.facts})
    try:
        out = cached_generate(provider, ctx.state, prompts.SYSTEM_HE,
                              TASK.format(items=json.dumps(items, ensure_ascii=False, indent=1)))
    except LLMError as exc:
        ctx.fail("LLM", exc)
        return None
    by_id = {str(x.get("id")): x for x in out.get("items", []) if isinstance(x, dict)}
    use_rating = bool(ctx.cfg.s("alerts", "use_llm_rating", default=True))
    for i, a in enumerate(alerts[:10]):
        x = by_id.get(f"a{i}")
        if not x:
            continue
        allowed = allowed_numbers({"h": _plain(a.headline), "f": a.facts})
        clean, problems = validate_fields({"what": x.get("what"), "why": x.get("why")}, allowed)
        if problems:
            log.warning("alert %s: removed %s", a.key, problems)
        if isinstance(clean.get("what"), str) and clean["what"].strip():
            a.what = esc(clean["what"].strip())
        if isinstance(clean.get("why"), str) and clean["why"].strip():
            a.why = esc(clean["why"].strip())
        r = x.get("rating")
        if use_rating and a.kind == "story" and isinstance(r, (int, float)) and 1 <= r <= 10:
            a.score = round(0.7 * a.score + 0.3 * float(r), 1)
    return provider.name
