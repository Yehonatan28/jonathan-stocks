"""What triggers an alert. Every detector is a pure function of the snapshot and config."""
from __future__ import annotations

import time
from datetime import datetime

from .. import scheduler as sch
from ..collectors.sec import describe_items
from ..editions.common import bp, pct
from ..processing import cluster as cl
from ..processing.scoring import Scored
from ..snapshot import Snapshot
from ..telegram.send import esc
from .models import Alert

FRESH_SECONDS = 6 * 3600


def _fresh(ts: int, now: float) -> bool:
    return bool(ts) and now - ts <= FRESH_SECONDS


def _emoji(score: float, urgent_at: float) -> str:
    return "🔴" if score >= urgent_at else "🟠"


def _group_note(cfg, t: str) -> str | None:
    for g in cfg.market.get("groups", {}).values():
        if t in g.get("members", []) or t == g.get("etf"):
            return g.get("note")
    return None


def _related(snap: Snapshot, t: str) -> cl.Cluster | None:
    rel = [c for c in snap.clusters if t in c.tickers]
    return max(rel, key=lambda c: (len(c.sources), c.latest)) if rel else None


# ------------------------------------------------------------------ moves ---

def watch_moves(snap: Snapshot, cfg, now: float) -> list[Alert]:
    v = cfg.settings.get("volatility", {})
    k, k_urgent = float(v.get("alert_sigma", 2.0)), float(v.get("urgent_sigma", 3.5))
    urgent_at = float(cfg.s("alerts", "urgent", default=9))
    out = []
    for t in cfg.watchlist:
        q, z = snap.quotes.get(t), snap.sigmas.get(t)
        if not q or z is None or abs(z) < k or not _fresh(q.time, now):
            continue
        prof = snap.profiles[t]
        score = min(10.0, 7.0 + (abs(z) - k))
        if abs(z) >= k_urgent:
            score = max(score, urgent_at)
        day = datetime.fromtimestamp(q.time, sch.NY).date().isoformat()
        direction = "up" if z > 0 else "down"
        rel = _related(snap, t)
        what = (f"הידיעה הבולטת: {esc(rel.lead.title)}" if rel else "אין עדיין ידיעה שמסבירה את התנועה.")
        why = (f"תנועה של {abs(z):.1f} סטיות תקן. ביום רגיל {t} זזה בערך {prof.stdev_pct:.1f}%"
               + (" (היסטוריה קצרה, הסף משוער)." if prof.is_default else "."))
        note = _group_note(cfg, t)
        out.append(Alert(
            key=f"move:{t}:{day}:{direction}:{int(abs(z))}", kind="move", score=round(score, 1),
            headline=f"{_emoji(score, urgent_at)} <b>{t}</b>  {pct(q.change_pct)}   "
                     f"(תנועה חריגה: {abs(z):.1f} סטיות תקן)",
            what=what, why=why + (f" {esc(note)}" if note else ""), symbol=t, tickers=[t],
            url=rel.lead.url if rel else None, source=rel.lead.source if rel else None,
            level=int(abs(z)),
            facts={"symbol": t, "change_pct": round(q.change_pct, 2), "sigma": round(abs(z), 1),
                   "normal_daily_move_pct": prof.stdev_pct, "short_history": prof.is_default,
                   "headlines": [s.title for s in rel.stories[:4]] if rel else [], "group_note": note}))
    return out


def market_moves(snap: Snapshot, cfg, now: float) -> list[Alert]:
    urgent_at = float(cfg.s("alerts", "urgent", default=9))
    out = []
    for rule in cfg.market.get("market_alerts", []):
        sym, label = rule["symbol"], rule["label"]
        q = snap.quote(sym)
        if not q or not _fresh(q.time, now):
            continue
        day = snap.today_il.isoformat()
        if "bp" in rule:
            change_bp = (q.price - q.prev_close) * 100
            if abs(change_bp) < rule["bp"]:
                continue
            bucket = int(abs(change_bp) // rule["bp"])
            score = min(10.0, 7.5 + bucket - 1)
            head = f"{_emoji(score, urgent_at)} <b>{esc(label)}</b>  {q.price:.2f}% {bp(q.price - q.prev_close)}"
            facts = {"label": label, "yield_pct": round(q.price, 2), "change_bp": round(change_bp)}
            direction = "up" if change_bp > 0 else "down"
        else:
            if abs(q.change_pct) < rule["pct"]:
                continue
            bucket = int(abs(q.change_pct) // rule["pct"])
            score = min(10.0, 7.5 + bucket - 1)
            head = f"{_emoji(score, urgent_at)} <b>{esc(label)}</b>  {pct(q.change_pct)}"
            facts = {"label": label, "change_pct": round(q.change_pct, 2), "price": round(q.price, 2)}
            direction = "up" if q.change_pct > 0 else "down"
        affected = _affected_holdings(cfg, sym)
        out.append(Alert(
            key=f"market:{sym}:{day}:{direction}:{bucket}", kind="market", score=round(score, 1),
            headline=head, what="תנועה חריגה בשוק כולו.",
            why=("משפיע על: " + ", ".join(affected)) if affected else "תנועה ברמת השוק, לא רק במניה אחת.",
            symbol=sym, tickers=affected, level=bucket, facts={**facts, "affects_my_holdings": affected}))
    return out


def _affected_holdings(cfg, symbol: str) -> list[str]:
    wl = set(cfg.watchlist)
    if symbol in ("SPY", "QQQ"):
        return []
    found = []
    for ch in cfg.market.get("impact_chains", []):
        if ch.get("driver") == symbol or ch.get("sector") == symbol:
            found += [h for h in ch.get("holdings", []) if h in wl and h not in found]
    return found


def megacap_moves(snap: Snapshot, cfg, now: float) -> list[Alert]:
    th = float(cfg.s("alerts", "megacap_move_pct", default=5.0))
    out = []
    for t in cfg.market.get("megacaps", []):
        if t in cfg.watchlist:
            continue
        q = snap.quotes.get(t)
        if not q or abs(q.change_pct) < th or not _fresh(q.time, now):
            continue
        rel = _related(snap, t)
        day = datetime.fromtimestamp(q.time, sch.NY).date().isoformat()
        out.append(Alert(
            key=f"mega:{t}:{day}:{int(abs(q.change_pct) // th)}", kind="megacap", score=7.5,
            headline=f"🟠 <b>{t}</b>  {pct(q.change_pct)}   (מניה גדולה מחוץ לרשימה)",
            what=(f"הידיעה הבולטת: {esc(rel.lead.title)}" if rel else "תנועה חדה של אחת החברות הגדולות בשוק."),
            why="חברות בגודל הזה מזיזות את המדדים, ולכן גם את MAGS ואת תעודות הסל הסקטוריאליות.",
            symbol=t, tickers=[t], url=rel.lead.url if rel else None, level=int(abs(q.change_pct) // th),
            facts={"symbol": t, "change_pct": round(q.change_pct, 2),
                   "headlines": [s.title for s in rel.stories[:3]] if rel else []}))
    return out


# --------------------------------------------------------------- events ---

def earnings(snap: Snapshot, cfg) -> list[Alert]:
    out = []
    wl = set(cfg.watchlist)
    mega = set(cfg.market.get("megacaps", []))
    for e in snap.earnings_reported:
        if e.symbol not in wl and e.symbol not in mega:
            continue
        surprise = None
        if e.eps_estimate not in (None, 0) and e.eps_actual is not None:
            surprise = round((e.eps_actual - e.eps_estimate) / abs(e.eps_estimate) * 100, 1)
        mine = e.symbol in wl
        score = 8.0 if mine else 7.0
        if surprise is not None and abs(surprise) >= 10:
            score += 1.0
        q = snap.quotes.get(e.symbol)
        line = f"EPS {e.eps_actual:g}" + (f" מול צפי {e.eps_estimate:g}" if e.eps_estimate is not None else "")
        if surprise is not None:
            line += f" (הפתעה של {surprise:+.1f}%)"
        out.append(Alert(
            key=f"earn:{e.symbol}:{e.date}", kind="earnings", score=score,
            headline=f"🟠 <b>{e.symbol}</b>  דוח רבעוני" + (f"  {pct(q.change_pct)}" if q else ""),
            what=line + ".",
            why=("ההפתעה מול הציפיות היא מה שמזיז את המניה, וגם התחזית קדימה (guidance)." if mine
                 else "דוח של אחת החברות הגדולות. יכול להזיז את הסקטור ואת המדדים."),
            symbol=e.symbol, tickers=[e.symbol], level=1,
            facts={"symbol": e.symbol, "eps_actual": e.eps_actual, "eps_estimate": e.eps_estimate,
                   "surprise_pct": surprise, "revenue_actual": e.revenue_actual,
                   "revenue_estimate": e.revenue_estimate,
                   "change_pct": round(q.change_pct, 2) if q else None, "mine": mine}))
    return out


SEC_STRONG = {"1.01", "1.03", "2.01", "2.02", "2.05", "2.06", "3.01", "4.02", "5.02"}


def filings(snap: Snapshot, cfg) -> list[Alert]:
    out = []
    for f in snap.filings:
        items = {i.strip() for i in f.items.split(",") if i.strip()}
        score = 8.0 if items & SEC_STRONG else 7.0
        if f.form in ("10-Q", "10-K"):
            score = 7.0
        desc = describe_items(f.items)
        out.append(Alert(
            key=f"sec:{f.url}", kind="filing", score=score,
            headline=f"🟠 <b>{f.ticker}</b>  הגשת {f.form} ל-SEC" + (f" · {esc(desc)}" if desc else ""),
            what=f"החברה הגישה {f.form}" + (f" בנושא: {esc(desc)}." if desc else "."),
            why="דיווח רשמי, לפעמים לפני שהחדשות מגיעות לאתרים.",
            symbol=f.ticker, tickers=[f.ticker], url=f.url, source="SEC EDGAR", level=1,
            facts={"symbol": f.ticker, "form": f.form, "items": desc}))
    return out


def stories(scored: list[Scored], snap: Snapshot, cfg, now: float) -> list[Alert]:
    a = cfg.settings.get("alerts", {})
    window = float(a.get("story_window_hours", 3)) * 3600
    hot_n = int(a.get("hot_story_sources", 4))
    urgent_at = float(a.get("urgent", 9))
    out = []
    for s in scored:
        c = s.cluster
        recent = [x for x in c.stories if now - x.published <= window]
        if not recent:
            continue
        score = s.score
        hot = len({x.source for x in recent}) >= hot_n
        if hot:
            score = max(score, 7.5)
        if score < float(a.get("threshold", 7)) - 1:      # candidates only; final cut after the model
            continue
        mine = sorted(c.tickers & set(cfg.watchlist))
        tag = "🔥 סיפור חם" if hot else "📰 ידיעה מהותית"
        out.append(Alert(
            key=s.key, kind="story", score=score,
            headline=f"{_emoji(score, urgent_at)} {tag} · {len(c.sources)} מקורות"
                     + (f" · {', '.join(mine)}" if mine else ""),
            what=esc(c.lead.title), why="; ".join(esc(r) for r in s.reasons[:2]) + ".",
            symbol=mine[0] if mine else None, tickers=mine, url=c.lead.url, source=c.lead.source,
            facts={"titles": list(dict.fromkeys(x.title for x in c.stories))[:5], "sources": len(c.sources),
                   "my_tickers": mine, "story_id": c.lead.id},
            tokens=sorted(c.words)))
    return out


def fomc(snap: Snapshot) -> list[Alert]:
    out = []
    for s in snap.fed:
        t = s.title.lower()
        if "fomc statement" in t or ("federal reserve" in t and "issues" in t and "statement" in t):
            out.append(Alert(
                key=f"fed:{s.id}", kind="fed", score=9.5,
                headline="🔴 🏛 <b>החלטת הריבית של הפד</b>",
                what=esc(s.title), why="ההחלטה משפיעה על תשואות האג\"ח, על הדולר ועל מניות הצמיחה.",
                url=s.url, source="Federal Reserve", tickers=[], level=1,
                facts={"title": s.title, "summary": s.summary[:300]}))
    return out


def macro_alert(label: str, rows: list[dict], snap: Snapshot, tier: int) -> Alert:
    """rows: [{'label','value','prev','unit'}] already computed from FRED."""
    lines = []
    for r in rows:
        unit = r.get("unit", "")
        lines.append(f"{esc(r['label'])}: {r['value']:g}{unit} (קודם: {r['prev']:g}{unit})")
    spy, qqq = snap.quotes.get("SPY"), snap.quotes.get("QQQ")
    tnx = snap.yahoo.get("^TNX")
    react = []
    if spy:
        react.append(f"S&P 500 {pct(spy.change_pct)}")
    if qqq:
        react.append(f"נאסד\"ק 100 {pct(qqq.change_pct)}")
    if tnx:
        react.append(f"10Y {bp(tnx.price - tnx.prev_close)}")
    score = 9.0 if tier == 1 else 8.0
    return Alert(
        key=f"macro:{label}:{snap.today_ny.isoformat()}", kind="macro", score=score,
        headline=f"{'🔴' if tier == 1 else '🟠'} 📊 <b>{esc(label)}</b>",
        what="\n".join(lines),
        why=(("תגובת השוק: " + " · ".join(react) + ". ") if react else "")
            + "אין לנו קונצנזוס במקור חינמי, אז ההשוואה היא לנתון הקודם.",
        url="https://fred.stlouisfed.org/", source="FRED", level=1,
        facts={"release": label, "values": rows,
               "spy_change_pct": round(spy.change_pct, 2) if spy else None,
               "qqq_change_pct": round(qqq.change_pct, 2) if qqq else None,
               "consensus_available": False})


def all_alerts(snap: Snapshot, scored: list[Scored], cfg, now: float | None = None) -> list[Alert]:
    now = now or time.time()
    found = (watch_moves(snap, cfg, now) + market_moves(snap, cfg, now) + megacap_moves(snap, cfg, now)
             + earnings(snap, cfg) + filings(snap, cfg) + fomc(snap) + stories(scored, snap, cfg, now))
    return sorted(found, key=lambda a: -a.score)
