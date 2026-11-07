"""Tiingo (free): end-of-day history, used only to compute each symbol's normal volatility.

Free plan: 50 requests/hour, 1,000/day, 500 distinct symbols/month. The history is cached in
state and refreshed at most once per day per symbol, incrementally.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from ..http import RateLimiter, SourceError, get_json

log = logging.getLogger(__name__)
BASE = "https://api.tiingo.com/tiingo/daily/{sym}/prices"
KEEP_ROWS = 300


def tiingo_symbol(sym: str) -> str:
    return sym.replace(".", "-").lower()


class Tiingo:
    def __init__(self, key: str):
        if not key:
            raise SourceError("TIINGO_API_KEY missing")
        self.headers = {"Authorization": f"Token {key}", "Content-Type": "application/json"}
        self.limiter = RateLimiter(45, 3600)

    def closes(self, sym: str, start: date) -> list[list]:
        rows = get_json(BASE.format(sym=tiingo_symbol(sym)), params={"startDate": start.isoformat()},
                        headers=self.headers, limiter=self.limiter, timeout=15, retries=1)
        return [[r["date"][:10], float(r.get("adjClose") or r["close"])] for r in rows if r.get("close")]


def refresh_history(client: Tiingo, state, symbols: list[str], today: date) -> list[str]:
    """Bring every symbol's cached closes up to date. Returns the symbols that failed."""
    marks = state.get("history_refreshed", {})
    failed = []
    for sym in symbols:
        if marks.get(sym) == today.isoformat():
            continue
        rows = state.history(sym)
        start = (date.fromisoformat(rows[-1][0]) + timedelta(days=1)) if rows else today - timedelta(days=420)
        if start > today:
            marks[sym] = today.isoformat()
            continue
        try:
            new = client.closes(sym, start)
        except SourceError as exc:
            log.warning("tiingo %s: %s", sym, exc)
            failed.append(sym)
            continue
        known = {r[0] for r in rows}
        rows.extend(r for r in new if r[0] not in known)
        state.set_history(sym, rows[-KEEP_ROWS:])
        marks[sym] = today.isoformat()
    state.set("history_refreshed", marks)
    return failed
