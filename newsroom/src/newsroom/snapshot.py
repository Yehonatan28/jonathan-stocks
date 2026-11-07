"""One collection layer for every consumer (editions, alerts, dashboard).

`collect(ctx, Collect(...))` fetches only what the caller asks for, in parallel, and never
raises because of a single source: failures are recorded on ctx.failed_sources.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from . import scheduler as sch
from .collectors import coingecko, rss, yahoo_fallback
from .collectors.fred import match_macro
from .collectors.tiingo import refresh_history
from .http import SourceError
from .models import EarningsEvent, Filing, MacroEvent, Quote, Story
from .processing import cluster as cl
from .processing import links, volatility as vol

log = logging.getLogger(__name__)


@dataclass
class Collect:
    lookback_hours: int = 24
    quotes: bool = True
    megacaps: bool = False
    history: bool = False
    rss: bool = True
    fed: bool = True
    market_news: bool = True
    company_news: list[str] | None = None
    earnings_days: tuple[int, int] | None = (0, 0)   # (from, to) days relative to today (NY)
    btc: bool = True
    fred_series: bool = False
    macro_days: int = 0                              # 0 = no calendar; n = today .. today+n
    sec: bool = True
    yahoo: bool = True


@dataclass
class Snapshot:
    today_il: date
    today_ny: date
    session: date                                     # last *completed* NY session
    now: datetime | None = None
    quotes: dict[str, Quote] = field(default_factory=dict)
    sigmas: dict[str, float] = field(default_factory=dict)
    profiles: dict[str, vol.VolProfile] = field(default_factory=dict)
    btc: Quote | None = None
    fred: dict[str, dict] = field(default_factory=dict)
    yahoo: dict[str, Quote] = field(default_factory=dict)
    stories: list[Story] = field(default_factory=list)
    fed: list[Story] = field(default_factory=list)
    clusters: list[cl.Cluster] = field(default_factory=list)
    filings: list[Filing] = field(default_factory=list)
    earnings: list[EarningsEvent] = field(default_factory=list)
    earnings_today: list[EarningsEvent] = field(default_factory=list)
    earnings_reported: list[EarningsEvent] = field(default_factory=list)
    macro_today: list[MacroEvent] = field(default_factory=list)
    macro_upcoming: list[MacroEvent] = field(default_factory=list)

    def quote(self, symbol: str) -> Quote | None:
        """Finnhub, CoinGecko or Yahoo, by symbol."""
        if symbol == "BTC":
            return self.btc
        return self.quotes.get(symbol) or self.yahoo.get(symbol)


def collect(ctx, opts: Collect) -> Snapshot:
    cfg, state = ctx.cfg, ctx.state
    extra = cfg.market.get("extra_closures") or []
    today_ny = ctx.now.astimezone(sch.NY).date()
    snap = Snapshot(today_il=ctx.now.astimezone(sch.IL).date(), today_ny=today_ny,
                    session=sch.last_completed_session(ctx.now, extra), now=ctx.now)
    since = int((ctx.now - timedelta(hours=opts.lookback_hours)).timestamp())
    fh = ctx.finnhub

    def job_quotes():
        if not fh:
            return
        syms = cfg.all_quote_symbols()
        if opts.megacaps:
            syms += [m for m in cfg.market.get("megacaps", []) if m not in syms]
        snap.quotes, failed = fh.quotes(syms)
        if failed and len(failed) > len(snap.quotes):
            ctx.fail("Finnhub quotes", f"{len(failed)} failed")

    def job_history():
        if ctx.tiingo:
            failed = refresh_history(ctx.tiingo, state, cfg.watchlist + cfg.index_symbols + cfg.sector_symbols,
                                     snap.today_il)
            if failed:
                ctx.fail("Tiingo", ", ".join(failed[:5]))

    def job_rss():
        if opts.rss:
            stories, failed = rss.fetch_feeds(cfg.sources.get("rss", []))
            snap.stories.extend(s for s in stories if s.published >= since)
            if failed:
                ctx.fail("RSS", ", ".join(failed))
        if opts.fed:
            fed, failed = rss.fetch_feeds(cfg.sources.get("fed", []), kind="fed")
            snap.fed = sorted((s for s in fed if s.published >= since), key=lambda s: -s.published)
            if failed:
                ctx.fail("Fed RSS", ", ".join(failed))

    def job_finnhub_news():
        if not fh:
            return
        try:
            if opts.market_news:
                snap.stories.extend(s for s in fh.market_news() if s.published >= since)
            frm = snap.session - timedelta(days=1)
            for t in opts.company_news or []:
                snap.stories.extend(s for s in fh.company_news(t, frm, today_ny) if s.published >= since)
            if opts.earnings_days:
                a, b = opts.earnings_days
                start = min(snap.session, today_ny + timedelta(days=a))
                snap.earnings = fh.earnings(start, today_ny + timedelta(days=b))
        except SourceError as exc:
            ctx.fail("Finnhub news", exc)

    def job_btc():
        if not opts.btc:
            return
        try:
            snap.btc = coingecko.bitcoin(cfg.secrets.coingecko)
        except SourceError as exc:
            ctx.fail("CoinGecko", exc)

    def job_fred():
        if not ctx.fred or not (opts.fred_series or opts.macro_days):
            return
        try:
            if opts.fred_series:
                for sid in cfg.market.get("fred_series", {}):
                    v = ctx.fred.latest(sid)
                    if v:
                        snap.fred[sid] = v
            if opts.macro_days:
                cal = state.cache("macro_calendar")
                key = f"{today_ny.isoformat()}:{opts.macro_days}"
                if cal.get("key") != key:                      # once per day is enough
                    cal = {"key": key, "rows": ctx.fred.release_dates(today_ny, opts.macro_days)}
                    state.set_cache("macro_calendar", cal)
                snap.macro_upcoming = match_macro(cal["rows"], cfg.market.get("macro_releases", []))
        except SourceError as exc:
            ctx.fail("FRED", exc)

    def job_sec():
        if not opts.sec or not ctx.sec:
            return
        try:
            snap.filings, failed = ctx.sec.recent(cfg.watchlist, cfg.sources.get("sec_forms", ["8-K"]),
                                                  hours=max(opts.lookback_hours, 26))
            if failed:
                ctx.fail("SEC", ", ".join(failed))
        except SourceError as exc:
            ctx.fail("SEC", exc)

    def job_yahoo():
        if opts.yahoo and cfg.s("sources", "yahoo_fallback", default=False):
            snap.yahoo, failed = yahoo_fallback.quotes(list(cfg.market.get("yahoo_symbols", {})))
            if failed and not snap.yahoo:
                ctx.fail("Yahoo (גיבוי)", "blocked")

    jobs = [job_rss, job_finnhub_news, job_btc, job_fred, job_sec, job_yahoo]
    if opts.quotes:
        jobs.insert(0, job_quotes)
    if opts.history:
        jobs.insert(1, job_history)
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = [(j, pool.submit(j)) for j in jobs]
        for j, f in futures:
            try:
                f.result()
            except Exception as exc:  # noqa: BLE001 - one broken source must not stop the run
                ctx.fail(j.__name__.removeprefix("job_"), exc)
                log.exception("collector crashed")

    derive(snap, cfg, state)
    tag_and_cluster(snap, cfg, ctx)
    state.archive(snap.today_il, [s.archive_row() for s in snap.stories + snap.fed])
    persist_market(state, snap)
    return snap


def persist_market(state, snap: Snapshot) -> None:
    """Merge this run's numbers into one compact view the dashboard reads. Newer prints win."""
    m = state.cache("market")
    quotes = m.setdefault("quotes", {})

    def put(q, sigma=None, stdev=None):
        old = quotes.get(q.symbol)
        if old and old.get("time", 0) > q.time:
            return
        quotes[q.symbol] = {"price": q.price, "change_pct": round(q.change_pct, 3), "prev_close": q.prev_close,
                            "time": q.time, "source": q.source, "sigma": sigma, "stdev": stdev}

    for sym, q in snap.quotes.items():
        prof = snap.profiles.get(sym)
        put(q, snap.sigmas.get(sym), prof.stdev_pct if prof else None)
    for q in snap.yahoo.values():
        put(q)
    if snap.btc:
        put(snap.btc)
    if snap.fred:
        m["fred"] = {**m.get("fred", {}), **snap.fred}
    if snap.macro_upcoming:
        m["macro_upcoming"] = [vars(e) for e in snap.macro_upcoming]
    if snap.earnings:
        m["earnings"] = [vars(e) for e in snap.earnings]
    m["updated"] = int(snap.now.timestamp()) if snap.now else m.get("updated")
    state.set_cache("market", m)


def derive(snap: Snapshot, cfg, state) -> None:
    """Volatility per symbol, and the earnings / macro views. Pure given state history."""
    v = cfg.settings.get("volatility", {})
    for sym, q in snap.quotes.items():
        # The yardstick ends the day before the quote's own session (intraday or last close).
        ref = datetime.fromtimestamp(q.time, sch.NY).date().isoformat() if q.time else snap.session.isoformat()
        prof = vol.profile(state.history(sym), ref, int(v.get("lookback_days", 60)),
                           int(v.get("min_history_days", 20)), float(v.get("default_daily_stdev_pct", 3.0)))
        snap.profiles[sym] = prof
        snap.sigmas[sym] = vol.sigma(q.change_pct, prof)
    today = snap.today_ny.isoformat()
    snap.earnings_today = [e for e in snap.earnings if e.date == today]
    snap.earnings_reported = [e for e in snap.earnings if e.eps_actual is not None
                              and snap.session.isoformat() <= e.date <= today]
    snap.macro_today = [m for m in snap.macro_upcoming if m.date == today]


def tag_and_cluster(snap: Snapshot, cfg, ctx) -> None:
    names = ctx.state.cache("company_names")
    if ctx.finnhub:
        missing = [t for t in cfg.watchlist if t not in names]
        for t in missing[:5]:                      # a few per run; the rest next time
            try:
                names[t] = ctx.finnhub.profile_name(t) or ""
            except SourceError:
                pass
        if missing:
            ctx.state.set_cache("company_names", names)
    aliases = {t: links.aliases(t, names.get(t)) for t in cfg.watchlist}
    cl.tag_tickers(snap.stories, aliases)
    snap.clusters = cl.cluster(snap.stories)


def record_intraday(state, snap: Snapshot, symbols: list[str], keep_days: int = 10) -> None:
    """Append this run's prices: the dashboard draws intraday charts from these points."""
    key = snap.today_ny.isoformat()
    path_name = f"intraday-{key}"
    series = state.cache(path_name)
    for s in symbols:
        q = snap.quote(s)
        if q and q.time:
            pts = series.setdefault(s, [])
            if not pts or pts[-1][0] != q.time:
                pts.append([q.time, round(q.price, 4), round(q.change_pct, 3)])
    state.set_cache(path_name, series)
    for f in (state.root / "cache").glob("intraday-*.json"):
        try:
            if date.fromisoformat(f.stem.removeprefix("intraday-")) < snap.today_ny - timedelta(days=keep_days):
                f.unlink()
        except ValueError:
            continue
