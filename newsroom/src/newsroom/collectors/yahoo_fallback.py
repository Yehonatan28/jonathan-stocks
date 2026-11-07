"""Backup only: VIX, 10-year yield, index futures and Asian indexes.

None of these has an official free real-time source. Yahoo may block automated clients at
any time; when it does, the edition says "no data" instead of failing.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from ..http import SourceError, get_json
from ..models import Quote

log = logging.getLogger(__name__)
URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


def quote(sym: str) -> Quote | None:
    d = get_json(URL.format(sym=sym), params={"range": "1d", "interval": "15m"},
                 headers=HEADERS, timeout=10, retries=1)
    res = ((d.get("chart") or {}).get("result") or [None])[0]
    if not res:
        return None
    meta = res.get("meta", {})
    price, prev = meta.get("regularMarketPrice"), meta.get("chartPreviousClose") or meta.get("previousClose")
    if not price or not prev:
        return None
    return Quote(symbol=sym, price=float(price), prev_close=float(prev),
                 change_pct=round((price / prev - 1) * 100, 2),
                 time=int(meta.get("regularMarketTime") or 0), source="Yahoo (גיבוי)")


def quotes(symbols: list[str]) -> tuple[dict[str, Quote], list[str]]:
    def one(s):
        try:
            return s, quote(s)
        except SourceError as exc:
            log.warning("yahoo %s: %s", s, exc)
            return s, None

    out, failed = {}, []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for s, q in pool.map(one, symbols):
            (out.__setitem__(s, q) if q else failed.append(s))
    return out, failed
