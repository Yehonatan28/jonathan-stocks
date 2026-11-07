"""SEC EDGAR: recent 8-K / 10-Q / 10-K filings of the watchlist.

SEC asks for a User-Agent with a contact email and at most 10 requests per second.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from ..http import RateLimiter, SourceError, get_json
from ..models import Filing

log = logging.getLogger(__name__)

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"

ITEMS_HE = {
    "1.01": "הסכם מהותי", "1.02": "סיום הסכם מהותי", "1.03": "פשיטת רגל",
    "2.01": "השלמת רכישה/מכירה", "2.02": "תוצאות כספיות", "2.03": "התחייבות פיננסית",
    "2.05": "עלויות ארגון מחדש", "2.06": "ירידת ערך", "3.01": "בעיית רישום למסחר",
    "4.02": "אי-הסתמכות על דוחות קודמים", "5.02": "שינוי בהנהלה", "5.07": "הצבעת בעלי מניות",
    "7.01": "גילוי לפי Reg FD", "8.01": "אירוע אחר",
}


class Sec:
    def __init__(self, contact: str, state):
        if not contact or "@" not in contact:
            raise SourceError("SEC_CONTACT (email) missing - SEC requires it in the User-Agent")
        self.headers = {"User-Agent": f"Newsroom personal research {contact}", "Accept-Encoding": "gzip"}
        self.state = state
        self.limiter = RateLimiter(8, 1.0)

    def _cik_map(self) -> dict[str, int]:
        cached = self.state.cache("sec_ciks")
        if cached.get("_ts", 0) > time.time() - 7 * 86400:
            return cached["map"]
        raw = get_json(TICKERS_URL, headers=self.headers, limiter=self.limiter, timeout=20)
        m = {v["ticker"].upper(): int(v["cik_str"]) for v in raw.values()}
        self.state.set_cache("sec_ciks", {"_ts": int(time.time()), "map": m})
        return m

    def recent(self, tickers: list[str], forms: list[str], hours: int = 26) -> tuple[list[Filing], list[str]]:
        ciks = self._cik_map()
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        out: list[Filing] = []
        failed: list[str] = []
        for t in tickers:
            cik = ciks.get(t.upper())
            if not cik:
                continue                       # ETFs (IBIT, XLE, MAGS) do not file 8-Ks
            try:
                d = get_json(SUBMISSIONS.format(cik=cik), headers=self.headers, limiter=self.limiter,
                             timeout=15, retries=1)
            except SourceError as exc:
                log.warning("sec %s: %s", t, exc)
                failed.append(t)
                continue
            out.extend(parse_recent(t, cik, d, forms, since))
        return out, failed


def parse_recent(ticker: str, cik: int, d: dict, forms: list[str], since: datetime) -> list[Filing]:
    r = (d.get("filings") or {}).get("recent") or {}
    out = []
    for i, form in enumerate(r.get("form", [])):
        if form not in forms:
            continue
        accepted = r.get("acceptanceDateTime", [""] * (i + 1))[i]
        try:
            ts = datetime.fromisoformat(accepted.replace("Z", "+00:00"))
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts < since:
            break                               # newest first
        acc = r["accessionNumber"][i].replace("-", "")
        doc = r.get("primaryDocument", [""] * (i + 1))[i]
        out.append(Filing(ticker=ticker, form=form, filed=ts.isoformat(),
                          url=f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}",
                          items=(r.get("items") or [""] * (i + 1))[i] or ""))
    return out


def describe_items(items: str) -> str:
    names = [ITEMS_HE[i.strip()] for i in items.split(",") if i.strip() in ITEMS_HE]
    return ", ".join(names)
