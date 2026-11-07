"""One alerts pass: collect (light) -> score -> detect -> model text -> anti-noise -> send."""
from __future__ import annotations

import logging
from datetime import datetime, time as dtime

from .. import scheduler as sch
from ..processing.scoring import score_all
from ..snapshot import Collect, Snapshot, collect, record_intraday
from . import detect, macro
from .antinoise import AntiNoise
from .format import combine
from .write import enrich

log = logging.getLogger(__name__)


def market_active(now: datetime, extra=None) -> bool:
    """Pre-market to after-hours on a trading day (04:00-20:00 New York)."""
    ny = now.astimezone(sch.NY)
    return sch.is_trading_day(ny.date(), extra) and dtime(4, 0) <= ny.time() <= dtime(20, 0)


def collect_for_alerts(ctx) -> Snapshot:
    cfg = ctx.cfg
    n = int(ctx.state.get("alert_runs", 0)) + 1
    ctx.state.set("alert_runs", n)
    active = market_active(ctx.now, cfg.market.get("extra_closures"))
    wl = cfg.watchlist
    rotate = [wl[(n * 3 + i) % len(wl)] for i in range(min(3, len(wl)))] if wl and active else []
    return collect(ctx, Collect(
        lookback_hours=6, quotes=active, megacaps=active and n % 2 == 0, company_news=rotate,
        earnings_days=(0, 0) if active else None, macro_days=1 if active else 0,
        sec=True, yahoo=active))


def run(ctx, snap: Snapshot | None = None) -> list:
    cfg, state = ctx.cfg, ctx.state
    snap = snap or collect_for_alerts(ctx)
    record_intraday(state, snap, cfg.watchlist + cfg.index_symbols + cfg.sector_symbols
                    + [p["symbol"] for p in cfg.market.get("proxies", [])] + ["BTC"])
    now = ctx.now.timestamp()
    scored = score_all(snap.clusters, cfg, snap.sigmas)
    candidates = detect.all_alerts(snap, scored, cfg, now) + macro.released_today(ctx, snap)

    an = AntiNoise(state, cfg.settings, now)
    fresh = [a for a in candidates if a.key not in an.mem["sent"] and a.key not in an.mem["queued_keys"]]
    enrich(ctx, [a for a in fresh if a.score >= an.threshold - 1])
    send, queue = an.decide(fresh)
    if send:
        ctx.telegram.send(combine(send, cfg.s("dashboard_url") or ""), silent=all(a.silent for a in send))
    an.commit(send, queue)
    if send:
        import re
        plain = lambda h: re.sub(r"<[^>]+>", "", h).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")  # noqa: E731
        log_ = state.cache("alerts_log", [])
        log_ = (log_ if isinstance(log_, list) else []) + [
            {"ts": int(now), "kind": a.kind, "score": a.score, "urgent": a.urgent, "symbol": a.symbol,
             "headline": plain(a.headline), "what": plain(a.what), "why": plain(a.why), "url": a.url}
            for a in send]
        state.set_cache("alerts_log", log_[-40:])
    state.set_cache("last_scored", [
        {"id": s.cluster.lead.id, "title": s.cluster.lead.title, "url": s.cluster.lead.url,
         "source": s.cluster.lead.source, "sources": sorted(s.cluster.sources), "score": s.score,
         "reasons": s.reasons, "sentiment": s.sentiment, "tickers": sorted(s.cluster.tickers),
         "time": s.cluster.latest, "first": min(x.published for x in s.cluster.stories)}
        for s in scored[:40]])
    log.info("alerts: %d candidates, %d sent, %d queued", len(candidates), len(send), len(queue))
    return send
