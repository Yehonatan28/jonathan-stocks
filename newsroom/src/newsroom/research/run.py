"""The evening research run: refresh candles (within Tiingo's budget, across several runs if
needed), analyse the universe, choose the setups, write the thesis, keep an honest track record."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta

from .. import scheduler as sch
from ..collectors.tiingo import Budget, refresh_history
from ..http import SourceError
from ..llm import prompts
from ..llm.base import LLMError, cached_generate, get_provider
from ..llm.validator import allowed_numbers, validate_fields
from . import engine

log = logging.getLogger(__name__)

TASK = """אתה אנליסט טכני בכיר בבורסה האמריקאית. כתוב לכל סטאפ:
"thesis": שני משפטים מקצועיים: מה המבנה הטכני ולמה הוא מעניין עכשיו.
"confirm": משפט אחד: מה יאשר את הסטאפ (מחיר ומחזור).
"invalidate": משפט אחד: מה יבטל אותו.
השתמש רק במספרים שמופיעים בנתונים של אותו סטאפ. בלי "קנה", בלי "מכור", בלי "כדאי". זה ניתוח, לא המלצה.

הסטאפים:
{items}

החזר JSON: {{"items": [{{"symbol": "...", "thesis": "...", "confirm": "...", "invalidate": "..."}}]}}"""


def due(ctx) -> bool:
    r = ctx.cfg.research
    if not r or not r.get("enabled", True):
        return False
    ny = ctx.now.astimezone(sch.NY)
    target = sch.last_completed_session(ctx.now, ctx.cfg.market.get("extra_closures"))
    done = (ctx.state.cache("research") or {}).get("session")
    if done == target.isoformat():
        return False
    if target == ny.date():
        return ny.time() >= sch._hm(r.get("run_after_et", "18:00"))
    return True                                      # a later day: yesterday's research is still missing


def _earnings_map(ctx, universe: list[str], today: date) -> dict[str, str]:
    cached = ctx.state.cache("research_earnings")
    if cached.get("day") == today.isoformat():
        return cached.get("map", {})
    out: dict[str, str] = {}
    if ctx.finnhub:
        try:
            uni = set(universe)
            for e in ctx.finnhub.earnings(today, today + timedelta(days=14)):
                if e.symbol in uni and (e.symbol not in out or e.date < out[e.symbol]):
                    out[e.symbol] = e.date
        except SourceError as exc:
            ctx.fail("Finnhub earnings", exc)
    ctx.state.set_cache("research_earnings", {"day": today.isoformat(), "map": out})
    return out


def _story_scores(state) -> dict[str, float]:
    out: dict[str, float] = {}
    for s in state.cache("last_scored", []) or []:
        for t in s.get("tickers", []):
            out[t] = max(out.get(t, 0), s.get("score", 0))
    return out


# ------------------------------------------------------------- track record ---

def update_log(log_rows: list[dict], candles: dict[str, list[list]]) -> list[dict]:
    """Follow every past pick day by day. Conservative: a day that touches both the stop and
    the target counts as a stop."""
    for p in log_rows:
        if p["status"] not in ("watching", "triggered"):
            continue
        rows = [r for r in candles.get(p["symbol"], []) if r[0] > p.get("checked", p["date"])]
        for d, o, h, lo, c, v in rows:
            p["checked"] = d
            p["days"] = p.get("days", 0) + 1
            if p["status"] == "watching":
                if lo <= p["stop"] and h < p["trigger"]:
                    p["status"], p["closed"] = "cancelled", d
                    break
                if h >= p["trigger"]:
                    p["status"], p["triggered_on"], p["days"] = "triggered", d, 0
                    if lo <= p["stop"]:
                        p["status"], p["closed"], p["r"] = "stopped", d, -1.0
                        break
                    continue
                if p["days"] >= 15:
                    p["status"], p["closed"] = "expired", d
                    break
            else:
                risk = p["trigger"] - p["stop"]
                if lo <= p["stop"]:
                    p["status"], p["closed"], p["r"] = "stopped", d, -1.0
                    break
                if h >= p["target"]:
                    p["status"], p["closed"], p["r"] = "target", d, round((p["target"] - p["trigger"]) / risk, 2)
                    break
                if p["days"] >= 40:
                    p["status"], p["closed"], p["r"] = "timeout", d, round((c - p["trigger"]) / risk, 2)
                    break
                p["open_r"] = round((c - p["trigger"]) / risk, 2)
    return log_rows[-200:]


def stats(log_rows: list[dict]) -> dict:
    closed = [p for p in log_rows if p.get("r") is not None]
    wins = [p for p in closed if p["r"] > 0]
    return {
        "picks": len(log_rows),
        "triggered": sum(1 for p in log_rows if p.get("triggered_on")),
        "closed": len(closed),
        "win_rate": round(100 * len(wins) / len(closed)) if closed else None,
        "avg_r": round(sum(p["r"] for p in closed) / len(closed), 2) if closed else None,
        "open": sum(1 for p in log_rows if p["status"] == "triggered"),
        "watching": sum(1 for p in log_rows if p["status"] == "watching"),
    }


# ------------------------------------------------------------------ writing ---

def _facts(a: engine.Analysis) -> dict:
    m = a.metrics
    return {"symbol": a.symbol, "setup": engine.SETUP_HE.get(a.setup or ""), "levels": a.levels,
            "score": a.score, "rs_rating": m.get("rs_rating"), "trend_template": m.get("trend_template"),
            "close": m.get("close"), "base_depth_pct": m.get("base_depth_pct"), "base_len": m.get("base_len"),
            "contractions_pct": m.get("contractions_pct"), "vol_ratio": m.get("vol_ratio"), "dry_up": m.get("dry_up"),
            "rsi14": m.get("rsi14"), "ext_ema21_pct": m.get("ext_ema21_pct"), "from_high52_pct": m.get("from_high52_pct"),
            "tags": a.tags, "reasons": a.reasons, "flags": a.flags,
            "link": {k: v for k, v in a.link.items() if k != "corr"}, "corr_to_portfolio": a.link.get("corr")}


def template_text(a: engine.Analysis) -> dict:
    lv = a.levels
    return {
        "thesis": f"{engine.SETUP_HE.get(a.setup or '', '')}. " + "; ".join(a.reasons[:3]) + ("." if a.reasons else ""),
        "confirm": f"סגירה מעל {lv['trigger']:g} במחזור גבוה מהממוצע.",
        "invalidate": f"סגירה מתחת ל-{lv['stop']:g}.",
    }


def write_theses(ctx, picks: list[engine.Analysis]) -> dict[str, dict]:
    out = {a.symbol: template_text(a) for a in picks}
    if not picks:
        return out
    try:
        provider = get_provider(ctx.cfg)
    except LLMError:
        provider = None
    if provider is None:
        return out
    facts = [_facts(a) for a in picks]
    try:
        res = cached_generate(provider, ctx.state, prompts.SYSTEM_HE,
                              TASK.format(items=json.dumps(facts, ensure_ascii=False, indent=1)))
    except LLMError as exc:
        ctx.fail("LLM", exc)
        return out
    by_sym = {str(x.get("symbol")): x for x in res.get("items", []) if isinstance(x, dict)}
    for a, f in zip(picks, facts):
        x = by_sym.get(a.symbol)
        if not x:
            continue
        clean, problems = validate_fields({k: x.get(k) for k in ("thesis", "confirm", "invalidate")}, allowed_numbers(f))
        if problems:
            log.warning("research %s: removed %s", a.symbol, problems)
        for k, v in clean.items():
            if isinstance(v, str) and v.strip():
                out[a.symbol][k] = v.strip()
    return out


# --------------------------------------------------------------------- run ---

def compact(a: engine.Analysis) -> dict:
    m = a.metrics
    keep = ("close", "change_pct", "rs_rating", "trend_template", "trend_passed", "sma50", "sma200", "ema21",
            "atr_pct", "rsi14", "base_depth_pct", "base_len", "contractions_pct", "vol_ratio", "dry_up",
            "ext_ema21_pct", "from_high52_pct", "high52", "pivot", "bbw_rank", "rs_line_high", "sector_rs_3m",
            "ret_1m", "ret_3m", "date")
    return {"symbol": a.symbol, "setup": a.setup, "setup_he": engine.SETUP_HE.get(a.setup or ""), "score": a.score,
            "breakdown": a.breakdown, "levels": a.levels, "tags": a.tags, "reasons": a.reasons, "flags": a.flags,
            "link": a.link, "metrics": {k: m.get(k) for k in keep}}


def run(ctx, force: bool = False) -> dict | None:
    cfg, state = ctx.cfg, ctx.state
    r = cfg.research
    if not r or (not force and not due(ctx)):
        return None
    target = sch.last_completed_session(ctx.now, cfg.market.get("extra_closures"))
    universe = cfg.research_universe()
    progress = state.get("research_progress") or {}
    if progress.get("session") != target.isoformat():
        progress = {"session": target.isoformat(), "attempts": 0}
    progress["attempts"] += 1
    pending: list[str] = []
    if ctx.tiingo:
        pending = refresh_history(ctx.tiingo, state, universe, ctx.now.astimezone(sch.IL).date(),
                                  Budget(state), max_calls=int(r.get("calls_per_run", 35)))
    late = ctx.now.astimezone(sch.NY).time() >= sch._hm("23:30") or progress["attempts"] >= 6
    if pending and not late and not force:
        progress["pending"] = len(pending)
        state.set("research_progress", progress)
        log.info("research: %d symbols left for the next run", len(pending))
        return None

    data = {s: state.ohlc(s) for s in universe}
    today = ctx.now.astimezone(sch.NY).date()
    analyses = engine.analyze_universe(data, r, cfg.watchlist, today, _earnings_map(ctx, universe, today),
                                       _story_scores(state))
    prev = state.cache("research") or {}
    prev_syms = [p["symbol"] for p in prev.get("picks", [])]
    picks = engine.choose(analyses, int(r.get("picks", 3)), float(r.get("min_score", 60)), prev_syms)
    shortlist = [a for a in engine.choose(analyses, int(r.get("picks", 3)) + int(r.get("shortlist", 8)),
                                          float(r.get("min_score", 60)) - 10, prev_syms)
                 if a.symbol not in {p.symbol for p in picks}]
    texts = write_theses(ctx, picks)

    log_rows = update_log(state.cache("research_log", []) or [], data)
    logged = {(p["symbol"], p["date"]) for p in log_rows}
    for a in picks:
        if a.symbol not in prev_syms and (a.symbol, target.isoformat()) not in logged:
            log_rows.append({"symbol": a.symbol, "date": a.metrics["date"], "setup": a.setup, "score": a.score,
                             **{k: a.levels[k] for k in ("trigger", "stop", "target", "rr")}, "status": "watching"})
    state.set_cache("research_log", log_rows)

    by_sym = {a.symbol: a for a in analyses}
    result = {
        "session": target.isoformat(),
        "generated": int(ctx.now.timestamp()),
        "universe": len(universe),
        "analyzed": sum(1 for a in analyses if a.metrics),
        "missing": [a.symbol for a in analyses if not a.metrics][:20],
        "picks": [{**compact(a), **texts.get(a.symbol, {}), "status": "ממשיך" if a.symbol in prev_syms else "חדש",
                   "candles": a.candles[-70:]} for a in picks],
        "shortlist": [compact(a) for a in shortlist],
        "holdings": [compact(by_sym[t]) for t in cfg.watchlist if t in by_sym and by_sym[t].metrics],
        "track": stats(log_rows),
        "track_recent": [p for p in reversed(log_rows)][:12],
    }
    state.set_cache("research", result)
    state.set("research_progress", {"session": target.isoformat(), "done": True})
    log.info("research: %d analysed, picks %s", result["analyzed"], [p["symbol"] for p in result["picks"]])
    return result
