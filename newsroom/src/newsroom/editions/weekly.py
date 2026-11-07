"""📅 Weekly summary, Sunday 08:00 Israel time. Written so it can later become a LinkedIn post."""
from __future__ import annotations

import math
from datetime import date, timedelta

from .. import scheduler as sch
from ..models import Story
from ..processing import cluster as cl
from ..processing import volatility as vol
from ..snapshot import Collect, collect
from ..telegram.send import esc, link
from .common import HOUR_HE, pct
from .writer import footer, publish, write

TASK = """כתוב את הטקסטים לסיכום השבועי. המספרים כבר מוכנים בקוד.
הנתונים: {facts}
החזר JSON:
{"headline": "משפט אחד: השבוע במשפט",
 "story_of_week": "פסקה של שלושה עד ארבעה משפטים: מה היה השבוע ולמה זה חשוב. כתוב כך שאפשר יהיה להפוך את זה לפוסט מקצועי בלינקדאין.",
 "my_stocks": "משפט או שניים: איך הגיבו המניות שלי",
 "week_ahead": "משפט או שניים: על מה לשים לב בשבוע הבא"}"""


def close_on(rows: list[list], d: date) -> float | None:
    """Last close on or before `d`."""
    best = None
    for day, c in rows:
        if day <= d.isoformat():
            best = c
        else:
            break
    return best


def weekly_change(rows: list[list], prev_end: date, end: date) -> float | None:
    a, b = close_on(rows, prev_end), close_on(rows, end)
    if not a or not b:
        return None
    return round((b / a - 1) * 100, 2)


def weekly_sigma(rows: list[list], change: float | None, prev_end: date, cfg) -> float | None:
    """The week's move in units of the symbol's normal *weekly* move (daily σ × √5)."""
    if change is None:
        return None
    v = cfg.settings.get("volatility", {})
    prof = vol.profile(rows, (prev_end + timedelta(days=1)).isoformat(), int(v.get("lookback_days", 60)),
                       int(v.get("min_history_days", 20)), float(v.get("default_daily_stdev_pct", 3.0)))
    return round(change / (prof.stdev_pct * math.sqrt(5)), 2)


def build(ctx, snap) -> dict:
    cfg, state = ctx.cfg, ctx.state
    prev_end, end = sch.week_bounds(snap.session, cfg.market.get("extra_closures"))

    def row(sym, name):
        h = state.history(sym)
        ch = weekly_change(h, prev_end, end)
        return {"symbol": sym, "name": name, "change_pct": ch, "sigma": weekly_sigma(h, ch, prev_end, cfg)}

    idx = [row(s, cfg.display_name(s)) for s in cfg.index_symbols]
    sect = sorted((row(s, cfg.market["sectors"][s]) for s in cfg.sector_symbols),
                  key=lambda r: -(r["change_pct"] if r["change_pct"] is not None else -999))
    mine = sorted((row(t, t) for t in cfg.watchlist), key=lambda r: -abs(r["sigma"] or 0))

    arch = state.read_archive(prev_end + timedelta(days=1), snap.today_il)
    stories = [Story(r["title"], r["url"], r["source"], r["published"], kind=r.get("kind", "news"),
                     tickers=r.get("tickers", []), quality=r.get("quality", 2)) for r in arch]
    top = cl.hot(cl.cluster(stories), 5)

    wl, mega = set(cfg.watchlist), set(cfg.market.get("megacaps", []))
    nxt_from, nxt_to = snap.today_ny, snap.today_ny + timedelta(days=7)
    fomc = [str(d) for d in cfg.market.get("fomc_decisions", []) if nxt_from.isoformat() <= str(d) <= nxt_to.isoformat()]
    return {
        "week": f"{(prev_end + timedelta(days=1)).day}.{(prev_end + timedelta(days=1)).month}–{end.day}.{end.month}",
        "indices_week": idx,
        "sector_best": sect[0] if sect else None,
        "sector_worst": next((s for s in reversed(sect) if s["change_pct"] is not None), None),
        "my_stocks_week": mine,
        "top_stories": [{"title": c.lead.title, "url": c.lead.url, "source": c.lead.source,
                         "sources_count": len(c.sources)} for c in top],
        "next_week": {
            "earnings": [{"symbol": e.symbol, "date": e.date, "when": HOUR_HE.get(e.hour, ""), "mine": e.symbol in wl}
                         for e in snap.earnings if e.symbol in wl or e.symbol in mega],
            "macro": [{"label": m.label, "date": m.date, "tier": m.tier} for m in snap.macro_upcoming if m.tier <= 2],
            "fomc": fomc,
        },
    }


def _day(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{sch.HEB_DAYS[d.weekday()]} {d.day}.{d.month}"


def render(ctx, snap, facts: dict, text: dict | None, label: str) -> str:
    out = [f"📅 <b>הסיכום השבועי</b> · {facts['week']}"]
    if text and text.get("headline"):
        out[0] += f"\n📌 <b>{esc(text['headline'])}</b>"
    idx = [i for i in facts["indices_week"] if i["change_pct"] is not None]
    if idx:
        lines = ["📊 <b>השבוע בוול סטריט</b>", " · ".join(f"{esc(i['name'])} {pct(i['change_pct'])}" for i in idx)]
        b, w = facts["sector_best"], facts["sector_worst"]
        if b and w and b["change_pct"] is not None:
            lines.append(f"מוביל: {esc(b['name'])} {pct(b['change_pct'])} · מפגר: {esc(w['name'])} {pct(w['change_pct'])}")
        out.append("\n".join(lines))
    if text and text.get("story_of_week"):
        out.append("📰 <b>הסיפור של השבוע</b>\n" + esc(text["story_of_week"]))
    elif facts["top_stories"]:
        out.append("📰 <b>הסיפורים של השבוע</b>\n" + "\n".join(
            f"• {link(s['url'], s['title'])} ({esc(s['source'])})" for s in facts["top_stories"][:3]))
    mine = [m for m in facts["my_stocks_week"] if m["change_pct"] is not None]
    if mine:
        block = ["💼 <b>המניות שלי השבוע</b>",
                 " · ".join(f"<b>{m['symbol']}</b> {pct(m['change_pct'])}" for m in mine)]
        if text and text.get("my_stocks"):
            block.append(esc(text["my_stocks"]))
        out.append("\n".join(block))
    nw = facts["next_week"]
    block = ["🚉 <b>השבוע הבא</b>"]
    for d in nw["fomc"]:
        block.append(f"• {_day(d)} · 🏛 החלטת הריבית של הפד")
    for m in nw["macro"]:
        block.append(f"• {_day(m['date'])} · {esc(m['label'])}")
    earn = [e for e in nw["earnings"]]
    if earn:
        mine_e = [e for e in earn if e["mine"]]
        others = [e for e in earn if not e["mine"]]
        if mine_e:
            block.append("• ⭐ דוחות ברשימה: " + ", ".join(f"{e['symbol']} ({_day(e['date'])})" for e in mine_e))
        if others:
            block.append("• דוחות גדולים: " + ", ".join(f"{e['symbol']} ({_day(e['date'])})" for e in others[:8]))
    if text and text.get("week_ahead"):
        block.append(esc(text["week_ahead"]))
    if len(block) == 1:
        block.append("• אין אירועים מרכזיים בלוח")
    out.append("\n".join(block))
    out.append(footer(ctx, label, ctx.now))
    return "\n\n".join(out)


def run(ctx) -> None:
    snap = collect(ctx, Collect(lookback_hours=24, quotes=False, history=True, rss=False, fed=False,
                                market_news=False, earnings_days=(0, 7), btc=False, macro_days=7,
                                sec=False, yahoo=False))
    facts = build(ctx, snap)
    text, label = write(ctx, TASK, facts)
    publish(ctx, "weekly", render(ctx, snap, facts, text, label), snap.today_il.isoformat())
