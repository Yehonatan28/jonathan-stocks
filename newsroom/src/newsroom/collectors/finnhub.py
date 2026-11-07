"""Finnhub, free plan: quotes, market news, company news, earnings calendar, company profile.

Free plan = 60 calls/minute and US data only (no indices, no candles, no economic calendar).
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from ..http import RateLimiter, SourceError, get_json
from ..models import EarningsEvent, Quote, Story

log = logging.getLogger(__name__)
BASE = "https://finnhub.io/api/v1"


class Finnhub:
    def __init__(self, key: str, calls_per_minute: int = 55):
        if not key:
            raise SourceError("FINNHUB_API_KEY missing")
        self.key = key
        self.limiter = RateLimiter(calls_per_minute, 60)

    def _get(self, path: str, **params):
        return get_json(f"{BASE}{path}", params=params, headers={"X-Finnhub-Token": self.key},
                        limiter=self.limiter, timeout=12, retries=2)

    def quote(self, symbol: str) -> Quote | None:
        d = self._get("/quote", symbol=symbol)
        if not d or not d.get("pc"):
            return None                      # unknown symbol: Finnhub returns zeros
        price = d.get("c") or d["pc"]
        return Quote(symbol=symbol, price=float(price), prev_close=float(d["pc"]),
                     change_pct=float(d.get("dp") or 0.0), time=int(d.get("t") or 0), source="Finnhub")

    def quotes(self, symbols: list[str]) -> tuple[dict[str, Quote], list[str]]:
        out: dict[str, Quote] = {}
        failed: list[str] = []

        def one(sym: str):
            try:
                return sym, self.quote(sym)
            except SourceError as exc:
                log.warning("quote %s: %s", sym, exc)
                return sym, None

        with ThreadPoolExecutor(max_workers=6) as pool:
            for sym, q in pool.map(one, symbols):
                if q:
                    out[sym] = q
                else:
                    failed.append(sym)
        return out, failed

    def market_news(self, category: str = "general") -> list[Story]:
        rows = self._get("/news", category=category) or []
        return [_story(r) for r in rows if r.get("headline") and r.get("url")]

    def company_news(self, symbol: str, frm: date, to: date) -> list[Story]:
        rows = self._get("/company-news", symbol=symbol, **{"from": frm.isoformat(), "to": to.isoformat()}) or []
        out = []
        for r in rows[:30]:
            if r.get("headline") and r.get("url"):
                s = _story(r)
                s.tickers = sorted({symbol, *s.tickers})
                out.append(s)
        return out

    def earnings(self, frm: date, to: date) -> list[EarningsEvent]:
        d = self._get("/calendar/earnings", **{"from": frm.isoformat(), "to": to.isoformat()}) or {}
        out = []
        for r in d.get("earningsCalendar", []):
            out.append(EarningsEvent(
                symbol=r.get("symbol", ""), date=r.get("date", ""), hour=r.get("hour") or "",
                eps_estimate=r.get("epsEstimate"), eps_actual=r.get("epsActual"),
                revenue_estimate=r.get("revenueEstimate"), revenue_actual=r.get("revenueActual")))
        return out

    def profile_name(self, symbol: str) -> str | None:
        d = self._get("/stock/profile2", symbol=symbol) or {}
        return d.get("name") or None


def _story(r: dict) -> Story:
    related = [t.strip().upper() for t in (r.get("related") or "").split(",") if t.strip()]
    return Story(title=r["headline"].strip(), url=r["url"], source=r.get("source") or "Finnhub",
                 published=int(r.get("datetime") or 0), tickers=related,
                 summary=(r.get("summary") or "")[:280], quality=2)
