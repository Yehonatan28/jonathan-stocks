"""Tiingo (free): end-of-day history. Feeds two things:
  * history/<SYM>.json  [date, adjClose]                     -> each symbol's normal volatility
  * ohlc/<SYM>.json     [date, open, high, low, close, volume] -> the technical research engine
Both come from the same request, so the research costs no extra calls for watchlist symbols.

Free plan: 50 requests/hour, 1,000/day, 500 distinct symbols/month. Runs are separate processes,
so the hourly budget is tracked in state across runs: a run that would exceed it simply stops
and the next run continues where it left off. Nothing ever sleeps for an hour.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from ..http import SourceError, get_json

log = logging.getLogger(__name__)
BASE = "https://api.tiingo.com/tiingo/daily/{sym}/prices"
KEEP_ROWS = 300
HOURLY_BUDGET = 45


def tiingo_symbol(sym: str) -> str:
    return sym.replace(".", "-").lower()


class Tiingo:
    def __init__(self, key: str):
        if not key:
            raise SourceError("TIINGO_API_KEY missing")
        self.headers = {"Authorization": f"Token {key}", "Content-Type": "application/json"}

    def rows(self, sym: str, start: date) -> list[dict]:
        return get_json(BASE.format(sym=tiingo_symbol(sym)), params={"startDate": start.isoformat()},
                        headers=self.headers, timeout=15, retries=1)

    def closes(self, sym: str, start: date) -> list[list]:
        return [[r["date"][:10], float(r.get("adjClose") or r["close"])] for r in self.rows(sym, start) if r.get("close")]


def ohlc_row(r: dict) -> list | None:
    """Split/dividend-adjusted candle. Falls back to raw values when adjusted ones are absent."""
    try:
        c = float(r.get("adjClose") or r["close"])
        ratio = c / float(r["close"]) if r.get("close") else 1.0
        o = float(r.get("adjOpen") or float(r["open"]) * ratio)
        h = float(r.get("adjHigh") or float(r["high"]) * ratio)
        lo = float(r.get("adjLow") or float(r["low"]) * ratio)
        v = float(r.get("adjVolume") or r.get("volume") or 0)
    except (KeyError, TypeError, ValueError):
        return None
    return [r["date"][:10], round(o, 4), round(h, 4), round(lo, 4), round(c, 4), int(v)]


class Budget:
    """Tiingo calls per clock hour, shared by every run through state."""

    def __init__(self, state, limit: int = HOURLY_BUDGET):
        self.state, self.limit = state, limit
        hour = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
        b = state.get("tiingo_budget") or {}
        if b.get("hour") != hour:
            b = {"hour": hour, "used": 0}
        self.b = b

    def take(self) -> bool:
        if self.b["used"] >= self.limit:
            return False
        self.b["used"] += 1
        self.state.set("tiingo_budget", self.b)
        return True

    @property
    def left(self) -> int:
        return self.limit - self.b["used"]


def refresh_history(client: Tiingo, state, symbols: list[str], today: date, budget: Budget | None = None,
                    max_calls: int | None = None) -> list[str]:
    """Bring every symbol's cached closes + candles up to date (at most once per day each).
    Returns the symbols that failed or were deferred for lack of budget."""
    budget = budget or Budget(state)
    marks = state.get("history_refreshed", {})
    pending, calls = [], 0
    for sym in symbols:
        if marks.get(sym) == today.isoformat():
            continue
        candles = state.ohlc(sym)
        closes = state.history(sym)
        # Too few candles (first run after the upgrade, or a recent IPO): backfill the full window.
        last = candles[-1][0] if len(candles) >= 200 else None
        start = (date.fromisoformat(last) + timedelta(days=1)) if last else today - timedelta(days=430)
        if start > today:
            marks[sym] = today.isoformat()
            continue
        if (max_calls is not None and calls >= max_calls) or not budget.take():
            pending.append(sym)
            continue
        calls += 1
        try:
            raw = client.rows(sym, start)
        except SourceError as exc:
            log.warning("tiingo %s: %s", sym, exc)
            pending.append(sym)
            continue
        new_c = [[r["date"][:10], float(r.get("adjClose") or r["close"])] for r in raw if r.get("close")]
        known = {r[0] for r in closes}
        closes.extend(r for r in new_c if r[0] not in known)
        state.set_history(sym, closes[-KEEP_ROWS:])
        known = {r[0] for r in candles}
        candles.extend(x for x in (ohlc_row(r) for r in raw) if x and x[0] not in known)
        state.set_ohlc(sym, candles[-KEEP_ROWS:])
        marks[sym] = today.isoformat()
    state.set("history_refreshed", marks)
    return pending
