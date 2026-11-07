"""Alert layout (spec 5.4). Several alerts in one run become ONE combined message."""
from __future__ import annotations

from ..telegram.send import link
from .models import Alert


def block(a: Alert, dashboard_url: str = "") -> str:
    lines = [a.headline, f"<b>מה קרה:</b> {a.what}", f"<b>למה זה חשוב:</b> {a.why}"]
    refs = []
    if a.url:
        refs.append(link(a.url, "🔗 מקור"))
    if dashboard_url:
        refs.append(link(dashboard_url.rstrip("/") + (f"/#t={a.symbol}" if a.symbol else "/"), "📊 בדשבורד"))
    if refs:
        lines.append("  ·  ".join(refs))
    return "\n".join(lines)


def combine(alerts: list[Alert], dashboard_url: str = "") -> str:
    if len(alerts) == 1:
        return block(alerts[0], dashboard_url)
    urgent = sum(a.urgent for a in alerts)
    head = f"🔔 <b>{len(alerts)} עדכונים</b>" + (f" · {urgent} דחופים" if urgent else "")
    return head + "\n\n" + "\n\n".join(block(a, dashboard_url) for a in alerts)


def queued_section(items: list[dict], title: str = "📥 <b>מה נצבר מאז ההודעה האחרונה</b>") -> str | None:
    if not items:
        return None
    lines = [title]
    for a in items:
        tail = f" {link(a['url'], '🔗')}" if a.get("url") else ""
        lines.append(f"• {a['headline']}{tail}")
    return "\n".join(lines)
