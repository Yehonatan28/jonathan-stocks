"""Build the dashboard data (data.json) from state, and push it to Cloudflare KV.

The page itself (dashboard/public) is static and deployed rarely; only this JSON changes.
Every number on the dashboard comes from here, with its source and time.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta

from .. import scheduler as sch
from ..config import ROOT
from ..http import SourceError, request
from ..models import Story
from ..processing import cluster as cl
from ..processing import weather
from ..processing.scoring import score_all

log = logging.getLogger(__name__)
LOCAL_OUT = ROOT / "dashboard" / "public" / "data.json"


def _q(m: dict, sym: str) -> dict | None:
    return (m.get("quotes") or {}).get(sym)


def _row(cfg, m: dict, sym: str, name: str | None = None) -> dict | None:
    q = _q(m, sym)
    if not q:
        return None
    return {"symbol": sym, "name": name or cfg.display_name(sym), "price": q["price"],
            "change_pct": round(q["change_pct"], 2), "sigma": q.get("sigma"), "stdev": q.get("stdev"),
            "source": q.get("source"), "asof": q.get("time")}


# ------------------------------------------------------------------ parts ---

def weather_block(cfg, m: dict) -> dict:
    vixq = _q(m, "^VIX")
    fred = m.get("fred", {})
    vix = vixq["price"] if vixq else (fred.get("VIXCLS") or {}).get("value")
    vix_src = ("Yahoo", vixq["time"]) if vixq else ("FRED", (fred.get("VIXCLS") or {}).get("date"))
    spy = _q(m, "SPY")
    sect = [_q(m, s) for s in cfg.sector_symbols]
    sect = [s for s in sect if s]
    up = sum(1 for s in sect if s["change_pct"] > 0)
    tnx = _q(m, "^TNX")
    if tnx:
        ybp, ysrc = round((tnx["price"] - tnx["prev_close"]) * 100, 1), ("Yahoo", tnx["time"])
        yval = tnx["price"]
    else:
        d = fred.get("DGS10") or {}
        ybp = round(d["change"] * 100, 1) if d.get("change") is not None else None
        yval, ysrc = d.get("value"), ("FRED", d.get("date"))
    uup, btc = _q(m, "UUP"), _q(m, "BTC")
    comp = weather.components(vix, spy["change_pct"] if spy else None, up if sect else None,
                              len(sect) or None, ybp, uup["change_pct"] if uup else None,
                              btc["change_pct"] if btc else None)
    s = weather.score(comp)
    parts = [
        {"key": "vix", "label": "VIX", "display": f"{vix:.1f}" if vix is not None else None,
         "source": vix_src[0], "asof": vix_src[1]},
        {"key": "spx", "label": "S&P 500", "display": spy and spy["change_pct"], "pct": True,
         "source": spy and spy["source"], "asof": spy and spy["time"]},
        {"key": "breadth", "label": "רוחב שוק", "display": f"{up}/{len(sect)} סקטורים" if sect else None,
         "source": "Finnhub", "asof": max((x["time"] for x in sect), default=None)},
        {"key": "yield", "label": "תשואת 10 שנים",
         "display": f"{yval:.2f}%" if yval is not None else None, "bp": ybp, "source": ysrc[0], "asof": ysrc[1]},
        {"key": "dollar", "label": "דולר (UUP)", "display": uup and uup["change_pct"], "pct": True,
         "source": uup and uup["source"], "asof": uup and uup["time"]},
        {"key": "btc", "label": "ביטקוין", "display": btc and btc["change_pct"], "pct": True,
         "source": btc and btc["source"], "asof": btc and btc["time"]},
    ]
    for p in parts:
        p["score"] = round(comp[p["key"]]) if p["key"] in comp else None
    return {"score": s, **weather.state_of(s), "verdict": weather.verdict(comp, vix, up if sect else None, len(sect)),
            "components": parts}


def waterfall(cfg, m: dict) -> dict | None:
    spy = _q(m, "SPY")
    if not spy:
        return None
    weights = cfg.market.get("sector_weights", {})
    items = []
    for s, w in weights.items():
        q = _q(m, s)
        if q:
            items.append({"symbol": s, "label": cfg.market["sectors"].get(s, s),
                          "change_pct": round(q["change_pct"], 2), "weight": w,
                          "contribution": round(w * q["change_pct"] / 100, 3)})
    items.sort(key=lambda x: -abs(x["contribution"]))
    explained = sum(i["contribution"] for i in items)
    mega = []
    for s, w in cfg.market.get("megacap_weights", {}).items():
        q = _q(m, s)
        if q:
            mega.append({"symbol": s, "weight": w, "change_pct": round(q["change_pct"], 2),
                         "contribution": round(w * q["change_pct"] / 100, 3)})
    mega.sort(key=lambda x: -abs(x["contribution"]))
    return {"total": round(spy["change_pct"], 2), "items": items,
            "residual": round(spy["change_pct"] - explained, 3), "megacaps": mega[:8],
            "source": spy["source"], "asof": spy["time"],
            "note": "משקלות משוערים במדד. תרומה = משקל × שינוי."}


def watchlist_block(cfg, m: dict, stories: list) -> list[dict]:
    news = {}
    for s in stories:
        for t in s["tickers"]:
            news[t] = news.get(t, 0) + 1
    groups = {}
    for gname, g in cfg.market.get("groups", {}).items():
        for t in g.get("members", []) + ([g["etf"]] if g.get("etf") else []):
            groups.setdefault(t, []).append(gname)
    out = []
    for t in cfg.watchlist:
        r = _row(cfg, m, t, t)
        if r:
            r["news"] = news.get(t, 0)
            r["groups"] = groups.get(t, [])
            out.append(r)
    return out


def stories_block(ctx, m: dict, day: date) -> list[dict]:
    arch = ctx.state.read_archive(day, day)
    stories = [Story(r["title"], r["url"], r["source"], r["published"], kind=r.get("kind", "news"),
                     tickers=r.get("tickers", []), quality=r.get("quality", 2)) for r in arch]
    start = datetime.combine(day, datetime.min.time(), sch.IL).timestamp()
    stories = [s for s in stories if s.published >= start]
    sigmas = {k: v.get("sigma") or 0.0 for k, v in (m.get("quotes") or {}).items()}
    scored = score_all(cl.cluster(stories), ctx.cfg, sigmas)
    return [{"id": s.cluster.lead.id, "title": s.cluster.lead.title, "url": s.cluster.lead.url,
             "source": s.cluster.lead.source, "sources": sorted(s.cluster.sources), "score": s.score,
             "reasons": s.reasons, "sentiment": s.sentiment, "tickers": sorted(s.cluster.tickers),
             "first": min(x.published for x in s.cluster.stories), "last": s.cluster.latest,
             "kind": s.cluster.lead.kind}
            for s in scored[:60]]


def chains_block(cfg, m: dict, stories: list[dict]) -> list[dict]:
    wl = set(cfg.watchlist)
    out = []
    for ch in cfg.market.get("impact_chains", []):
        keys = [k.lower() for k in ch.get("match", [])]
        ev = next((s for s in stories if any(k in s["title"].lower() for k in keys)), None)
        drv = _row(cfg, m, ch["driver"]) if ch.get("driver") else None
        sec = _row(cfg, m, ch["sector"]) if ch.get("sector") else None
        holds = [r for r in (_row(cfg, m, h, h) for h in ch.get("holdings", []) if h in wl) if r]
        if not holds:
            continue
        moved = (drv and abs(drv["change_pct"]) >= 1.5) or (sec and abs(sec["change_pct"]) >= 1.0)
        if not ev and not moved:
            continue
        if ch.get("driver") == "^TNX" and drv:
            drv["bp"] = round((drv["price"] - (_q(m, "^TNX") or {}).get("prev_close", drv["price"])) * 100, 1)
        out.append({"name": ch["name"], "event": ev and {k: ev[k] for k in ("title", "url", "source", "score", "sentiment")},
                    "driver": drv, "sector": sec, "holdings": holds,
                    "strength": (ev["score"] if ev else 0) + abs((drv or sec or {}).get("change_pct", 0))})
    return sorted(out, key=lambda c: -c["strength"])[:4]


def week_block(cfg, m: dict, today: date) -> dict:
    monday = today - timedelta(days=today.weekday())
    if today.weekday() >= 5:                         # weekend: show the coming week
        monday += timedelta(days=7)
    wl, mega = set(cfg.watchlist), set(cfg.market.get("megacaps", []))
    fomc = {str(d) for d in cfg.market.get("fomc_decisions", [])}
    days = []
    for i in range(5):
        d = monday + timedelta(days=i)
        iso = d.isoformat()
        ev = []
        if iso in fomc:
            ev.append({"kind": "fomc", "label": "החלטת ריבית", "time": sch.et_to_il(d, "14:00").strftime("%H:%M")})
        for x in m.get("macro_upcoming", []):
            if x["date"] == iso and x["tier"] <= 2:
                ev.append({"kind": "macro", "label": x["label"], "tier": x["tier"],
                           "time": sch.et_to_il(d, x["time_et"]).strftime("%H:%M") if x.get("time_et") else ""})
        for e in m.get("earnings", []):
            if e["date"] == iso and (e["symbol"] in wl or e["symbol"] in mega):
                ev.append({"kind": "earnings", "label": e["symbol"], "mine": e["symbol"] in wl,
                           "time": {"bmo": "לפני הפתיחה", "amc": "אחרי הסגירה"}.get(e.get("hour"), "")})
        s = sch.session(d, cfg.market.get("extra_closures"))
        days.append({"date": iso, "label": f"{sch.HEB_DAYS[d.weekday()]} {d.day}.{d.month}",
                     "closed": s is None, "holiday": sch.holiday_name(d), "early": bool(s and s[1].hour < 16),
                     "close_il": s[1].astimezone(sch.IL).strftime("%H:%M") if s else None,
                     "past": d < today, "today": d == today, "events": ev})
    return {"days": days}


def mags_block(cfg, m: dict) -> dict | None:
    g = cfg.market.get("groups", {}).get("mags")
    if not g:
        return None
    wl = set(cfg.watchlist)
    members = []
    for s in g.get("members", []):
        q = _q(m, s) or (_q(m, "GOOG") if s == "GOOGL" else None)
        members.append({"symbol": s, "held": s in wl, "change_pct": q and round(q["change_pct"], 2),
                        "sigma": q and q.get("sigma")})
    held = [x for x in members if x["held"]]
    up = [x["symbol"] for x in held if (x["sigma"] or 0) >= 1]
    down = [x["symbol"] for x in held if (x["sigma"] or 0) <= -1]
    etf = _q(m, g.get("etf", "MAGS"))
    return {"etf": g.get("etf"), "etf_held": g.get("etf") in wl, "etf_change_pct": etf and round(etf["change_pct"], 2),
            "members": members, "held_count": len(held), "basket": len(members),
            "together": up if len(up) >= len(down) else down,
            "direction": "up" if len(up) >= len(down) else "down"}


def intraday_block(ctx, cfg, today_ny: date, stories: list[dict]) -> dict:
    series = ctx.state.cache(f"intraday-{today_ny.isoformat()}")
    if not series:                                    # weekend / before the first run: last session
        prev = sch.previous_trading_day(today_ny + timedelta(days=1))
        series = ctx.state.cache(f"intraday-{prev.isoformat()}")
    keep = cfg.watchlist + cfg.index_symbols + ["BTC"]
    pins = []
    for s in stories:
        if s["score"] < 5:
            continue
        targets = s["tickers"] or ["SPY"]
        for t in targets:
            pins.append({"symbol": t, "ts": s["first"], "title": s["title"], "url": s["url"],
                         "source": s["source"], "score": s["score"], "sentiment": s["sentiment"]})
    return {"series": {k: v for k, v in series.items() if k in keep}, "pins": pins}


def editions_block(state) -> dict:
    out = {}
    for name in ("morning", "preopen", "close", "weekly"):
        e = state.cache(f"edition-{name}")
        if e:
            out[name] = e
    return out


# ------------------------------------------------------------------ build ---

def build_data(ctx) -> dict:
    cfg, state = ctx.cfg, ctx.state
    m = state.cache("market")
    today_il = ctx.now.astimezone(sch.IL).date()
    today_ny = ctx.now.astimezone(sch.NY).date()
    stories = stories_block(ctx, m, today_il)
    if len(stories) < 5:                               # early morning: include yesterday
        stories = stories_block(ctx, m, today_il - timedelta(days=1)) + stories
    fred = m.get("fred", {})
    macro = []
    for sid, label in cfg.market.get("fred_series", {}).items():
        f = fred.get(sid)
        if f:
            macro.append({"id": sid, "label": label, "value": f["value"], "change": f["change"],
                          "source": "FRED", "asof": f["date"]})
    return {
        "generated": int(ctx.now.timestamp()),
        "today": today_il.isoformat(),
        "today_label": sch.heb_date(today_il),
        "session": sch.last_completed_session(ctx.now, cfg.market.get("extra_closures")).isoformat(),
        "market_open": bool((lambda s: s and s[0] <= ctx.now <= s[1])(sch.session(today_ny))),
        "weather": weather_block(cfg, m),
        "indices": [r for r in (_row(cfg, m, s) for s in cfg.index_symbols) if r],
        "proxies": [r for r in (_row(cfg, m, p["symbol"]) for p in cfg.market.get("proxies", [])) if r],
        "btc": _row(cfg, m, "BTC", "ביטקוין"),
        "sectors": sorted((r for r in (_row(cfg, m, s, cfg.market["sectors"][s]) for s in cfg.sector_symbols) if r),
                          key=lambda r: -r["change_pct"]),
        "waterfall": waterfall(cfg, m),
        "watchlist": watchlist_block(cfg, m, stories),
        "stories": stories,
        "chains": chains_block(cfg, m, stories),
        "week": week_block(cfg, m, today_ny),
        "mags": mags_block(cfg, m),
        "intraday": intraday_block(ctx, cfg, today_ny, stories),
        "macro": macro,
        "alerts": list(reversed(state.cache("alerts_log", [])))[:15],
        "editions": editions_block(state),
        "failed_sources": ctx.failed_sources,
        "market_updated": m.get("updated"),
    }


def push_kv(ctx, payload: str) -> None:
    from ..cloudflare import KV
    kv = KV.from_env()
    if kv:
        kv.put("data.json", payload)


def maybe_build(ctx, force: bool = False) -> bool:
    minutes = float(ctx.cfg.s("dashboard", "min_push_minutes", default=10))
    last = ctx.state.get("dashboard_pushed", 0)
    if not force and time.time() - last < minutes * 60:
        return False
    data = build_data(ctx)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    LOCAL_OUT.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_OUT.write_text(payload, encoding="utf-8")
    try:
        push_kv(ctx, payload)
    except SourceError as exc:
        ctx.fail("Cloudflare KV", exc)
        return False
    ctx.state.set("dashboard_pushed", int(time.time()))
    return True
