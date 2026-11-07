"""CoinGecko (Demo key, free): bitcoin price and 24h change."""
from __future__ import annotations

import time

from ..http import SourceError, get_json
from ..models import Quote

URL = "https://api.coingecko.com/api/v3/simple/price"


def bitcoin(key: str) -> Quote:
    headers = {"x-cg-demo-api-key": key} if key else {}
    d = get_json(URL, params={"ids": "bitcoin", "vs_currencies": "usd", "include_24hr_change": "true",
                              "include_last_updated_at": "true"}, headers=headers, timeout=12, retries=2)
    b = d.get("bitcoin") or {}
    if "usd" not in b:
        raise SourceError("CoinGecko: no bitcoin price")
    price, chg = float(b["usd"]), float(b.get("usd_24h_change") or 0.0)
    prev = price / (1 + chg / 100) if chg > -100 else price
    return Quote(symbol="BTC", price=price, change_pct=round(chg, 2), prev_close=round(prev, 2),
                 time=int(b.get("last_updated_at") or time.time()), source="CoinGecko")
