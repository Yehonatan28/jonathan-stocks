"""🌆 Close summary: ~15 minutes after the close. Short, and sent without sound."""
from __future__ import annotations

from .. import scheduler as sch
from ..alerts.antinoise import take_queue
from ..alerts.format import queued_section
from ..processing.scoring import score_all
from ..snapshot import Collect, Snapshot, collect
from ..telegram.send import esc, link
from .common import pct, sigma_tag
from .writer import footer, publish, write

TASK = """כתוב כותרת אחת לסיכום יום המסחר שנסגר עכשיו, ומשפט אחד על הרשימה שלי. לפי הנתונים בלבד.
הנתונים: {facts}
החזר JSON: {"headline": "...", "my_line": "..."}"""


def build(cfg, snap: Snapshot) -> dict:
    idx = [{"name": cfg.display_name(s), "change_pct": round(snap.quotes[s].change_pct, 2)}
           for s in cfg.index_symbols if s in snap.quotes]
    sect = sorted(({"name": cfg.market["sectors"][s], "symbol": s, "change_pct": round(snap.quotes[s].change_pct, 2)}
                   for s in cfg.sector_symbols if s in snap.quotes), key=lambda x: -x["change_pct"])
    mine = sorted(({"ticker": t, "change_pct": round(snap.quotes[t].change_pct, 2), "sigma": snap.sigmas.get(t)}
                   for t in cfg.watchlist if t in snap.quotes), key=lambda r: -abs(r["sigma"] or 0))
    top = score_all(snap.clusters, cfg, snap.sigmas)[:1]
    return {
        "indices": idx, "sector_best": sect[0] if sect else None, "sector_worst": sect[-1] if sect else None,
        "sectors_up": sum(1 for s in sect if s["change_pct"] > 0), "sectors_total": len(sect),
        "my_stocks": mine,
        "top_story": {"title": top[0].cluster.lead.title, "url": top[0].cluster.lead.url,
                      "source": top[0].cluster.lead.source} if top else None,
    }


def render(ctx, snap: Snapshot, facts: dict, text: dict | None, label: str, queued: list[dict]) -> str:
    notable = float(ctx.cfg.s("volatility", "notable_sigma", default=1.0))
    out = [f"🌆 <b>סיכום סגירה</b> · {esc(sch.heb_date(snap.today_ny))}"]
    if text and text.get("headline"):
        out[0] += f"\n📌 <b>{esc(text['headline'])}</b>"
    if facts["indices"]:
        lines = [" · ".join(f"{esc(i['name'])} {pct(i['change_pct'])}" for i in facts["indices"])]
        b, w = facts["sector_best"], facts["sector_worst"]
        if b and w:
            lines.append(f"מוביל: {esc(b['name'])} {pct(b['change_pct'])} · מפגר: {esc(w['name'])} {pct(w['change_pct'])}"
                         f" · {facts['sectors_up']} מתוך {facts['sectors_total']} סקטורים עלו")
        out.append("\n".join(lines))
    moved = [r for r in facts["my_stocks"] if abs(r["sigma"] or 0) >= notable]
    rest = len(facts["my_stocks"]) - len(moved)
    block = ["💼 <b>הרשימה שלי</b>"]
    if moved:
        block.append(" · ".join(f"<b>{r['ticker']}</b> {pct(r['change_pct'])}{sigma_tag(r['sigma'], notable)}"
                                for r in moved))
    if rest:
        block.append(f"<i>{'שאר' if moved else 'כל'} הרשימה ({rest}) בלי תנועה חריגה.</i>")
    if text and text.get("my_line"):
        block.append(esc(text["my_line"]))
    out.append("\n".join(block))
    if facts["top_story"]:
        s = facts["top_story"]
        out.append(f"🔥 {link(s['url'], s['title'])} ({esc(s['source'])})")
    q = queued_section(queued)
    if q:
        out.append(q)
    out.append(footer(ctx, label, ctx.now))
    return "\n\n".join(out)


def run(ctx) -> None:
    snap = collect(ctx, Collect(lookback_hours=8, earnings_days=None, btc=False, sec=False, yahoo=False))
    facts = build(ctx.cfg, snap)
    text, label = write(ctx, TASK, facts)
    queued = take_queue(ctx.state)
    silent = bool(ctx.cfg.s("editions", "close", "silent", default=True))
    publish(ctx, "close", render(ctx, snap, facts, text, label, queued), snap.today_ny.isoformat(), silent=silent)
