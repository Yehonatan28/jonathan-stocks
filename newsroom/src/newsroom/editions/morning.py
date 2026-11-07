"""☀️ The morning edition (07:00 Israel time).

Flow: gather (APIs) -> facts (numbers, ready) -> the model writes only the sentences ->
validator strips any sentence with a number that is not in the facts -> render. If the model
fails, every section falls back to a fixed template, so the edition always goes out.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .. import scheduler as sch
from ..collectors import coingecko, rss, yahoo_fallback
from ..collectors.fred import match_macro
from ..collectors.sec import describe_items
from ..collectors.tiingo import refresh_history
from ..http import SourceError
from ..llm import prompts
from ..llm.base import LLMError, cached_generate, get_provider
from ..llm.validator import allowed_numbers, validate_fields
from ..models import EarningsEvent, Filing, Quote, Story
from ..processing import cluster as cl
from ..processing import links, volatility as vol
from ..telegram.send import esc, link
from .common import HOUR_HE, bp, concept_of, money, pct, r2, sigma_tag

log = logging.getLogger(__name__)


@dataclass
class MorningData:
    today_il: date
    today_ny: date
    session: date
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
    earnings_today: list[EarningsEvent] = field(default_factory=list)
    earnings_reported: list[EarningsEvent] = field(default_factory=list)
    macro_today: list = field(default_factory=list)


# ================================================================ gather ===

def gather(ctx) -> MorningData:
    cfg, state = ctx.cfg, ctx.state
    today_il = ctx.now.astimezone(sch.IL).date()
    today_ny = ctx.now.astimezone(sch.NY).date()
    extra = cfg.market.get("extra_closures") or []
    d = MorningData(today_il=today_il, today_ny=today_ny,
                    session=sch.last_completed_session(ctx.now, extra))
    since = int((ctx.now - timedelta(hours=int(cfg.s("morning", "news_lookback_hours", default=24)))).timestamp())
    fh = ctx.finnhub

    def job_quotes():
        if not fh:
            return
        d.quotes, failed = fh.quotes(cfg.all_quote_symbols())
        if failed and len(failed) > len(d.quotes):
            ctx.fail("Finnhub quotes", f"{len(failed)} failed")

    def job_history():
        if ctx.tiingo:
            failed = refresh_history(ctx.tiingo, state, cfg.watchlist + cfg.index_symbols + cfg.sector_symbols,
                                     today_il)
            if failed:
                ctx.fail("Tiingo", ", ".join(failed[:5]))

    def job_rss():
        stories, failed = rss.fetch_feeds(cfg.sources.get("rss", []))
        d.stories.extend(s for s in stories if s.published >= since)
        if failed:
            ctx.fail("RSS", ", ".join(failed))
        fed, failed = rss.fetch_feeds(cfg.sources.get("fed", []), kind="fed")
        d.fed = [s for s in fed if s.published >= since]
        if failed:
            ctx.fail("Fed RSS", ", ".join(failed))

    def job_finnhub_news():
        if not fh:
            return
        try:
            d.stories.extend(s for s in fh.market_news() if s.published >= since)
            frm = d.session - timedelta(days=1)
            for t in cfg.watchlist:
                d.stories.extend(s for s in fh.company_news(t, frm, today_ny) if s.published >= since)
            d.earnings_today = fh.earnings(today_ny, today_ny)
            d.earnings_reported = [e for e in fh.earnings(d.session, today_ny)
                                   if e.eps_actual is not None
                                   and (e.date == d.session.isoformat() or e.hour == "bmo")]
        except SourceError as exc:
            ctx.fail("Finnhub news", exc)

    def job_btc():
        try:
            d.btc = coingecko.bitcoin(cfg.secrets.coingecko)
        except SourceError as exc:
            ctx.fail("CoinGecko", exc)

    def job_fred():
        if not ctx.fred:
            return
        try:
            for sid in cfg.market.get("fred_series", {}):
                v = ctx.fred.latest(sid)
                if v:
                    d.fred[sid] = v
            d.macro_today = match_macro(ctx.fred.release_dates(today_ny, 1),
                                        cfg.market.get("macro_releases", []), on=today_ny)
        except SourceError as exc:
            ctx.fail("FRED", exc)

    def job_sec():
        if not ctx.sec:
            return
        try:
            d.filings, failed = ctx.sec.recent(cfg.watchlist, cfg.sources.get("sec_forms", ["8-K"]))
            if failed:
                ctx.fail("SEC", ", ".join(failed))
        except SourceError as exc:
            ctx.fail("SEC", exc)

    def job_yahoo():
        if cfg.s("sources", "yahoo_fallback", default=False):
            d.yahoo, failed = yahoo_fallback.quotes(list(cfg.market.get("yahoo_symbols", {})))
            if failed and not d.yahoo:
                ctx.fail("Yahoo (גיבוי)", "blocked")

    jobs = [job_quotes, job_history, job_rss, job_finnhub_news, job_btc, job_fred, job_sec, job_yahoo]
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = [(j, pool.submit(j)) for j in jobs]
        for j, f in futures:
            try:
                f.result()
            except Exception as exc:  # noqa: BLE001 - one broken source must not stop the edition
                ctx.fail(j.__name__.removeprefix("job_"), exc)
                log.exception("collector crashed")

    _volatility(d, cfg, state)
    _tag_and_cluster(d, cfg, ctx)
    state.archive(today_il, [s.archive_row() for s in d.stories + d.fed])
    return d


def _volatility(d: MorningData, cfg, state) -> None:
    v = cfg.settings.get("volatility", {})
    for sym, q in d.quotes.items():
        prof = vol.profile(state.history(sym), d.session.isoformat(), int(v.get("lookback_days", 60)),
                           int(v.get("min_history_days", 20)), float(v.get("default_daily_stdev_pct", 3.0)))
        d.profiles[sym] = prof
        d.sigmas[sym] = vol.sigma(q.change_pct, prof)


def _tag_and_cluster(d: MorningData, cfg, ctx) -> None:
    names = ctx.state.cache("company_names")
    if ctx.finnhub:
        for t in cfg.watchlist:
            if t not in names:
                try:
                    names[t] = ctx.finnhub.profile_name(t) or ""
                except SourceError:
                    pass
        ctx.state.set_cache("company_names", names)
    aliases = {t: links.aliases(t, names.get(t)) for t in cfg.watchlist}
    cl.tag_tickers(d.stories, aliases)
    d.clusters = cl.cluster(d.stories)


# ================================================================= facts ===

def _session_note(d: MorningData) -> str | None:
    yesterday_ny = d.today_ny - timedelta(days=1)
    if d.session == yesterday_ny:
        return None
    name = sch.holiday_name(yesterday_ny)
    if name:
        return f"הבורסה בניו יורק הייתה סגורה אתמול ({name}). הנתונים הם מהמסחר של {d.session.day}.{d.session.month}."
    return f"הנתונים הם מהמסחר האחרון, {sch.heb_date(d.session)}."


def my_stocks(d: MorningData, cfg) -> list[dict]:
    notable = float(cfg.s("volatility", "notable_sigma", default=1.0))
    groups = cfg.market.get("groups", {})
    rows = []
    for t in cfg.watchlist:
        q = d.quotes.get(t)
        z = d.sigmas.get(t)
        heads = [c for c in d.clusters if t in c.tickers]
        sources = {s for c in heads for s in c.sources}
        filings = [f for f in d.filings if f.ticker == t]
        earn = [e for e in d.earnings_reported if e.symbol == t]
        has_news = len(sources) >= 2 or filings or earn
        if not (has_news or (z is not None and abs(z) >= notable)):
            continue
        score = abs(z or 0) + 2 * bool(filings) + 2 * bool(earn) + min(len(sources), 4) * 0.5
        note = next((g.get("note") for g in groups.values() if t in g.get("members", []) or t == g.get("etf")), None)
        rows.append({
            "ticker": t,
            "change_pct": r2(q.change_pct) if q else None,
            "sigma": z if q else None,
            "normal_daily_move_pct": d.profiles[t].stdev_pct if t in d.profiles else None,
            "headlines": [{"title": c.lead.title, "source": c.lead.source, "url": c.lead.url,
                           "sources_count": len(c.sources)} for c in heads[:3]],
            "filings": [{"form": f.form, "items": describe_items(f.items), "url": f.url} for f in filings[:2]],
            "earnings": [{"eps_actual": e.eps_actual, "eps_estimate": e.eps_estimate} for e in earn[:1]],
            "group_note": note,
            "_score": score,
        })
    rows.sort(key=lambda r: -r["_score"])
    return rows[: int(cfg.s("morning", "max_my_stocks", default=6))]


def build_facts(d: MorningData, cfg) -> tuple[dict, dict[str, cl.Cluster], list[dict]]:
    idx = [{"name": cfg.display_name(s), "symbol": s, "change_pct": r2(d.quotes[s].change_pct)}
           for s in cfg.index_symbols if s in d.quotes]
    sectors = sorted(({"name": cfg.market["sectors"][s], "symbol": s, "change_pct": r2(d.quotes[s].change_pct)}
                      for s in cfg.sector_symbols if s in d.quotes), key=lambda x: -x["change_pct"])
    hot = cl.hot(d.clusters, int(cfg.s("morning", "hot_stories", default=3)) + 3)   # multi-source first
    refs = {f"s{i + 1}": c for i, c in enumerate(hot)}
    stocks = my_stocks(d, cfg)
    mags = links.mags_overlap(cfg.watchlist, cfg.market.get("groups", {}).get("mags", {}),
                              d.quotes, d.sigmas, float(cfg.s("volatility", "notable_sigma", default=1.0)))
    macro = {}
    for sid, label in cfg.market.get("fred_series", {}).items():
        if sid in d.fred:
            f = d.fred[sid]
            macro[label] = {"value": f["value"], "change": f["change"], "date": f["date"]}
            if sid == "DGS10" and f["change"] is not None:
                macro[label]["change_bp"] = round(f["change"] * 100)
    overnight = {}
    if d.btc:
        overnight["ביטקוין"] = {"price_usd": round(d.btc.price), "change_24h_pct": r2(d.btc.change_pct)}
    for sym, label in cfg.market.get("yahoo_symbols", {}).items():
        if sym in d.yahoo:
            overnight[label] = {"value": r2(d.yahoo[sym].price), "change_pct": r2(d.yahoo[sym].change_pct)}
    watch_or_mega = set(cfg.watchlist) | set(cfg.market.get("megacaps", []))
    sess = sch.session(d.today_ny, cfg.market.get("extra_closures"))
    facts = {
        "date": sch.heb_date(d.today_il) + f".{d.today_il.year}",
        "session_note": _session_note(d),
        "indices_last_session": idx,
        "sectors_last_session": sectors,
        "macro_daily_fred": macro,
        "my_stocks": [{k: v for k, v in r.items() if not k.startswith("_") and k != "url"} for r in stocks],
        "mags_overlap": mags,
        "hot_stories": [{"id": k, "sources_count": len(c.sources),
                         "titles": list(dict.fromkeys(s.title for s in c.stories))[:4],
                         "tickers": sorted(c.tickers)} for k, c in refs.items()],
        "fed_last_24h": [s.title for s in d.fed[:4]],
        "overnight": overnight,
        "today": {
            "us_market": "פתוחה" if sess else f"סגורה ({sch.holiday_name(d.today_ny) or 'סוף שבוע'})",
            "open_israel_time": sess[0].astimezone(sch.IL).strftime("%H:%M") if sess else None,
            "early_close": bool(sess and sess[1].hour < 16),
            "macro": [{"label": m.label, "time_israel": sch.et_to_il(d.today_ny, m.time_et).strftime("%H:%M")}
                      for m in d.macro_today],
            "fomc_decision": d.today_ny.isoformat() in {str(x) for x in cfg.market.get("fomc_decisions", [])},
            "earnings": [{"symbol": e.symbol, "when": HOUR_HE.get(e.hour, "")}
                         for e in d.earnings_today if e.symbol in watch_or_mega],
        },
        "israel_proxies": [{"name": cfg.display_name(i["symbol"]), "change_pct": r2(d.quotes[i["symbol"]].change_pct)}
                           for i in cfg.market.get("israel", []) if i["symbol"] in d.quotes],
        "groups_notes": {k: g.get("note") for k, g in cfg.market.get("groups", {}).items()},
    }
    return facts, refs, stocks


# ================================================================ writer ===

def write_text(ctx, facts: dict) -> tuple[dict | None, str]:
    """Ask the model for the sentences. Returns (validated text or None, label for the footer)."""
    try:
        provider = get_provider(ctx.cfg)
    except LLMError as exc:
        log.warning("llm config: %s", exc)
        return None, "⚙️ מהדורת גיבוי (בלי מודל שפה)"
    if provider is None:
        return None, "⚙️ מהדורת גיבוי (בלי מודל שפה)"
    try:
        out = cached_generate(provider, ctx.state, prompts.SYSTEM_HE, prompts.morning_prompt(facts))
    except LLMError as exc:
        ctx.fail("LLM", exc)
        return None, "⚙️ מהדורת גיבוי (מודל השפה לא זמין)"
    clean, problems = validate_fields(out, allowed_numbers(facts))
    if problems:
        log.warning("validator removed %d sentence(s): %s", len(problems), problems)
    label = f"✍️ נוסח: {provider.name}"
    if problems:
        label += f" · {len(problems)} משפטים נפסלו בבדיקת המספרים"
    return clean if isinstance(clean, dict) else None, label


# ================================================================ render ===

def _t(text: dict | None, key: str):
    return (text or {}).get(key) or None


def render(d: MorningData, cfg, facts: dict, refs: dict[str, cl.Cluster], stocks: list[dict],
           text: dict | None, footer_label: str, failed_sources: list[str], now: datetime) -> str:
    out: list[str] = []
    idx = facts["indices_last_session"]

    # 📌 headline
    headline = _t(text, "headline")
    if not headline:
        headline = ("וול סטריט: " + ", ".join(f"{i['name']} {pct(i['change_pct'])}" for i in idx[:2])) if idx \
            else "מהדורת הבוקר"
    out.append(f"☀️ <b>מהדורת בוקר</b> · {esc(sch.heb_date(d.today_il))}\n📌 <b>{esc(headline)}</b>")

    # ⚡ three things
    things = [x for x in (_t(text, "three_things") or []) if isinstance(x, dict) and x.get("text")][:3]
    lines = []
    for x in things:
        c = refs.get(str(x.get("story_id")))
        lines.append(f"• {esc(x['text'])}" + (f" {link(c.lead.url, '🔗')}" if c else ""))
    used = {str(x.get("story_id")) for x in things}
    if not lines:
        fallback = list(refs.items())[:3]
        used = {k for k, _ in fallback}
        lines = [f"• {link(c.lead.url, c.lead.title)} ({esc(c.lead.source)})" for _, c in fallback]
    if lines:
        out.append("⚡ <b>שלושה דברים שחייבים לדעת</b>\n" + "\n".join(lines))

    # 📊 Wall Street
    if idx:
        sect = facts["sectors_last_session"]
        block = [f"📊 <b>וול סטריט</b> · {esc(sch.heb_date(d.session))}"]
        if facts["session_note"]:
            block.append(f"<i>{esc(facts['session_note'])}</i>")
        block.append(" · ".join(f"{esc(i['name'])} {pct(i['change_pct'])}" for i in idx))
        if len(sect) >= 2:
            block.append(f"מוביל: {esc(sect[0]['name'])} ({sect[0]['symbol']}) {pct(sect[0]['change_pct'])} · "
                         f"מפגר: {esc(sect[-1]['name'])} ({sect[-1]['symbol']}) {pct(sect[-1]['change_pct'])}")
        m = facts["macro_daily_fred"]
        extras = []
        if "תשואת 10 שנים" in m:
            y = m["תשואת 10 שנים"]
            extras.append(f"10Y {y['value']:.2f}% {bp(y['change'])}")
        if "VIX" in m:
            extras.append(f"VIX {m['VIX']['value']:.1f}")
        if extras:
            block.append(" · ".join(extras) + " <i>(FRED, סגירה יומית)</i>")
        moved = _t(text, "what_moved")
        if moved:
            block.append(esc(moved))
        out.append("\n".join(block))

    # 💼 my stocks
    if stocks:
        why = _t(text, "my_stocks") or {}
        block = ["💼 <b>המניות שלי</b>"]
        for r in stocks:
            t = r["ticker"]
            head = f"<b>{t}</b> {pct(r['change_pct'])}{sigma_tag(r['sigma'])}"
            extra = []
            for f in r["filings"]:
                extra.append(link(f["url"], f"{f['form']}" + (f" · {f['items']}" if f["items"] else "")))
            if why.get(t):
                block.append(f"{head}\n{esc(why[t])}" + (f"\n📄 {' · '.join(extra)}" if extra else ""))
            else:
                h = r["headlines"][0] if r["headlines"] else None
                line = f"{head}" + (f"\n{link(h['url'], h['title'])}" if h else "")
                block.append(line + (f"\n📄 {' · '.join(extra)}" if extra else ""))
        mags = facts.get("mags_overlap") or {}
        if mags.get("moved_together"):
            direction = "עלו" if mags["direction"] == "up" else "ירדו"
            block.append(f"🎯 <i>ריכוזיות: {', '.join(mags['moved_together'])} {direction} יחד, "
                         f"והן גם בתוך MAGS. החשיפה כפולה.</i>")
        out.append("\n\n".join(block[:1]) + "\n" + "\n\n".join(block[1:]))

    # 🔥 hot
    hot_txt = {str(x.get("story_id")): x.get("text") for x in (_t(text, "hot_stories") or [])
               if isinstance(x, dict) and x.get("text")}
    n_hot = int(cfg.s("morning", "hot_stories", default=3))
    hot_items = [(k, c) for k, c in refs.items() if k not in used][:n_hot]
    if hot_items or d.fed:
        block = ["🔥 <b>מה כולם מדברים עליו</b>"]
        for k, c in hot_items:
            extra_n = len(c.sources) - 1
            more = "" if extra_n < 1 else " ועוד מקור" if extra_n == 1 else f" ועוד {extra_n} מקורות"
            body = esc(hot_txt[k]) if hot_txt.get(k) else esc(c.lead.title)
            block.append(f"• {body} ({link(c.lead.url, c.lead.source)}{more})")
        for s in d.fed[:2]:
            block.append(f"• 🏛 {link(s.url, s.title)}")
        out.append("\n".join(block))

    # 🌙 overnight
    on = facts["overnight"]
    if on:
        parts = []
        for label, v in on.items():
            if "price_usd" in v:
                parts.append(f"{esc(label)} {money(v['price_usd'])} {pct(v['change_24h_pct'])} (24ש')")
            elif label not in ("VIX", "תשואת 10 שנים"):
                parts.append(f"{esc(label)} {pct(v['change_pct'])}")
        block = ["🌙 <b>מה קרה בלילה</b>", " · ".join(parts)]
        if _t(text, "overnight"):
            block.append(esc(text["overnight"]))
        out.append("\n".join(block))

    # 📅 today
    today = facts["today"]
    block = ["📅 <b>מה צפוי היום</b>"]
    if today["open_israel_time"]:
        block.append(f"• פתיחת המסחר בניו יורק: {today['open_israel_time']} שעון ישראל"
                     + (" (יום מקוצר)" if today["early_close"] else ""))
    else:
        block.append(f"• הבורסה בניו יורק {esc(today['us_market'])}")
    for m in today["macro"]:
        block.append(f"• {m['time_israel']} · {esc(m['label'])}")
    if today["fomc_decision"]:
        block.append(f"• {sch.et_to_il(d.today_ny, '14:00').strftime('%H:%M')} · 🏛 החלטת הריבית של הפד")
    if today["earnings"]:
        block.append("• דוחות: " + ", ".join(f"{e['symbol']}" + (f" ({e['when']})" if e["when"] else "")
                                            for e in today["earnings"][:10]))
    if len(block) == 2 and not today["macro"]:
        block.append("• אין פרסומי מאקרו מרכזיים או דוחות של חברות גדולות")
    out.append("\n".join(block))

    # 🇮🇱 one line
    il_line = _t(text, "israel_line")
    if not il_line and facts["israel_proxies"]:
        il_line = " · ".join(f"{p['name']} {pct(p['change_pct'])}" for p in facts["israel_proxies"]) + " (אתמול בניו יורק)"
        out.append(f"🇮🇱 {esc(il_line)}")
    elif il_line:
        out.append(f"🇮🇱 {esc(il_line)}")

    # 📚 concept
    concept = _t(text, "concept") or {}
    term, explain = concept.get("term"), concept.get("explain")
    if not (term and explain):
        term, explain = concept_of(d.today_il)
    out.append(f"📚 <b>{esc(term)}</b>: {esc(explain)}")

    # footer
    foot = [f"🕐 {now.astimezone(sch.IL).strftime('%H:%M')} · {esc(footer_label)}"]
    if failed_sources:
        foot.append(f"⚠️ מקורות שלא ענו: {esc(', '.join(failed_sources))}")
    url = cfg.s("dashboard_url")
    if url:
        foot.append(link(url, "📊 לגרסה המלאה בדשבורד"))
    foot.append("<i>מידע בלבד, לא המלצה.</i>")
    out.append("\n".join(foot))
    return "\n\n".join(out)


# =================================================================== run ===

def run(ctx, force: bool = False) -> bool:
    d = gather(ctx)
    facts, refs, stocks = build_facts(d, ctx.cfg)
    text, label = write_text(ctx, facts)
    msg = render(d, ctx.cfg, facts, refs, stocks, text, label, ctx.failed_sources, ctx.now)
    ctx.telegram.send(msg)
    ctx.state.mark_sent("morning", d.today_il.isoformat())
    ctx.state.set("last_morning_facts", {"date": d.today_il.isoformat(), "facts": facts})
    return True
