"""🔔 Before the open: 30 minutes before New York opens. Short and sharp."""
from __future__ import annotations

from datetime import datetime

from .. import scheduler as sch
from ..alerts import macro
from ..alerts.antinoise import take_queue
from ..alerts.format import queued_section
from ..snapshot import Collect, Snapshot, collect
from ..telegram.send import esc
from .common import pct, sigma_tag
from .writer import footer, publish, write

TASK = """כתוב משפט אחד או שניים לפני פתיחת המסחר בניו יורק: על מה לשים לב היום, לפי הנתונים בלבד.
הנתונים: {facts}
החזר JSON: {"line": "..."}"""


def premarket(snap: Snapshot, cfg, now: datetime) -> list[dict]:
    """Watchlist prints from this morning (before 09:30 NY), biggest relative moves first."""
    open_dt = datetime.combine(snap.today_ny, sch.OPEN_ET, sch.NY)
    rows = []
    for t in cfg.watchlist:
        q = snap.quotes.get(t)
        if not q or not q.time:
            continue
        ts = datetime.fromtimestamp(q.time, sch.NY)
        if ts.date() != snap.today_ny or ts >= open_dt:
            continue
        rows.append({"ticker": t, "change_pct": round(q.change_pct, 2), "sigma": snap.sigmas.get(t)})
    return sorted(rows, key=lambda r: -abs(r["sigma"] or 0))[:6]


def build(ctx, snap: Snapshot) -> tuple[dict, list]:
    cfg = ctx.cfg
    fut = {cfg.market["yahoo_symbols"][s]: round(snap.yahoo[s].change_pct, 2)
           for s in ("ES=F", "NQ=F") if s in snap.yahoo}
    macro_rows = macro.values_today(ctx, snap, max_tier=3)
    wl, mega = set(cfg.watchlist), set(cfg.market.get("megacaps", []))
    earn = []
    for e in snap.earnings_reported:
        if e.symbol in wl or e.symbol in mega:
            surprise = (round((e.eps_actual - e.eps_estimate) / abs(e.eps_estimate) * 100, 1)
                        if e.eps_estimate not in (None, 0) else None)
            earn.append({"symbol": e.symbol, "eps_actual": e.eps_actual, "eps_estimate": e.eps_estimate,
                         "surprise_pct": surprise, "mine": e.symbol in wl})
    s = sch.session(snap.today_ny, cfg.market.get("extra_closures"))
    facts = {
        "open_israel_time": s[0].astimezone(sch.IL).strftime("%H:%M") if s else None,
        "early_close": bool(s and s[1].hour < 16),
        "futures": fut,
        "premarket_watchlist": premarket(snap, cfg, ctx.now),
        "macro_this_morning": [{"release": ev.label, "values": rows} for ev, rows in macro_rows],
        "earnings_this_morning": earn,
        "upcoming_today": [{"label": m.label, "time_israel": sch.et_to_il(snap.today_ny, m.time_et).strftime("%H:%M")}
                           for m in snap.macro_today if m.time_et >= "09:30"],
    }
    return facts, macro_rows


def render(ctx, snap: Snapshot, facts: dict, text: dict | None, label: str, queued: list[dict]) -> str:
    out = [f"🔔 <b>לפני הפתיחה</b> · {esc(sch.heb_date(snap.today_ny))}"
           + (f" · פתיחה ב-{facts['open_israel_time']}" if facts["open_israel_time"] else "")
           + (" · <i>יום מקוצר</i>" if facts["early_close"] else "")]
    if text and text.get("line"):
        out.append(f"📌 {esc(text['line'])}")
    if facts["futures"]:
        out.append("📈 " + " · ".join(f"{esc(k)} {pct(v)}" for k, v in facts["futures"].items()))
    pm = facts["premarket_watchlist"]
    if pm:
        out.append("💼 <b>פרה-מרקט ברשימה</b>\n" + " · ".join(
            f"<b>{r['ticker']}</b> {pct(r['change_pct'])}{sigma_tag(r['sigma'])}" for r in pm))
    else:
        out.append("💼 <i>אין עדיין מחירי פרה-מרקט ברשימה בנתונים החינמיים.</i>")
    if facts["macro_this_morning"]:
        lines = ["📊 <b>פורסם הבוקר</b>"]
        for m in facts["macro_this_morning"]:
            vals = " · ".join(f"{esc(v['label'])} {v['value']:g}{v['unit']} (קודם {v['prev']:g}{v['unit']})"
                              for v in m["values"])
            lines.append(f"• {esc(m['release'])}: {vals}")
        out.append("\n".join(lines))
    if facts["earnings_this_morning"]:
        lines = ["🧾 <b>דוחות הבוקר</b>"]
        for e in facts["earnings_this_morning"]:
            s = f" ({e['surprise_pct']:+.1f}%)" if e["surprise_pct"] is not None else ""
            est = f" מול {e['eps_estimate']:g}" if e["eps_estimate"] is not None else ""
            lines.append(f"• {'⭐ ' if e['mine'] else ''}<b>{e['symbol']}</b> EPS {e['eps_actual']:g}{est}{s}")
        out.append("\n".join(lines))
    if facts["upcoming_today"]:
        out.append("📅 " + " · ".join(f"{u['time_israel']} {esc(u['label'])}" for u in facts["upcoming_today"]))
    q = queued_section(queued)
    if q:
        out.append(q)
    out.append(footer(ctx, label, ctx.now))
    return "\n\n".join(out)


def run(ctx) -> None:
    snap = collect(ctx, Collect(lookback_hours=14, earnings_days=(0, 0), macro_days=1, btc=False, sec=False))
    facts, _ = build(ctx, snap)
    text, label = write(ctx, TASK, facts)
    queued = take_queue(ctx.state)
    publish(ctx, "preopen", render(ctx, snap, facts, text, label, queued), snap.today_ny.isoformat())
