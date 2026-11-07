"""Shared by every edition: ask the model for sentences, validate numbers, publish."""
from __future__ import annotations

import json
import logging

from ..llm import prompts
from ..llm.base import LLMError, cached_generate, get_provider
from ..llm.validator import allowed_numbers, validate_fields

log = logging.getLogger(__name__)
FALLBACK = "⚙️ מהדורת גיבוי (בלי מודל שפה)"


def write(ctx, task: str, facts: dict) -> tuple[dict | None, str]:
    try:
        provider = get_provider(ctx.cfg)
    except LLMError:
        return None, FALLBACK
    if provider is None:
        return None, FALLBACK
    prompt = task.replace("{facts}", json.dumps(facts, ensure_ascii=False, indent=1))
    try:
        out = cached_generate(provider, ctx.state, prompts.SYSTEM_HE, prompt)
    except LLMError as exc:
        ctx.fail("LLM", exc)
        return None, "⚙️ מהדורת גיבוי (מודל השפה לא זמין)"
    clean, problems = validate_fields(out, allowed_numbers(facts))
    label = f"✍️ נוסח: {provider.name}"
    if problems:
        log.warning("validator removed %d sentence(s): %s", len(problems), problems)
        label += f" · {len(problems)} משפטים נפסלו בבדיקת המספרים"
    return (clean if isinstance(clean, dict) else None), label


def publish(ctx, name: str, html: str, day: str, silent: bool = False) -> None:
    """Send, mark as sent, and keep the full text for the dashboard."""
    ctx.telegram.send(html, silent=silent)
    ctx.state.mark_sent(name, day)
    ctx.state.set_cache(f"edition-{name}", {"date": day, "html": html, "sent_at": int(ctx.now.timestamp())})


def footer(ctx, label: str, now) -> str:
    from .. import scheduler as sch
    from ..telegram.send import esc, link
    foot = [f"🕐 {now.astimezone(sch.IL).strftime('%H:%M')} · {esc(label)}"]
    if ctx.failed_sources:
        foot.append(f"⚠️ מקורות שלא ענו: {esc(', '.join(ctx.failed_sources))}")
    url = ctx.cfg.s("dashboard_url")
    if url:
        foot.append(link(url, "📊 לגרסה המלאה בדשבורד"))
    foot.append("<i>מידע בלבד, לא המלצה.</i>")
    return "\n".join(foot)
