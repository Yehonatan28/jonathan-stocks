"""Check every source with the real keys: is the endpoint really free on our plan?

Run from GitHub: Actions -> newsroom -> Run workflow -> task: probe. The report is printed in the
log and sent to Telegram (if Telegram is configured).
"""
from __future__ import annotations

import time
from datetime import date, timedelta

from ..config import Config, scrub
from ..http import SourceError, get_json, request


def _check(name: str, fn) -> tuple[str, bool, str]:
    t0 = time.time()
    try:
        detail = fn() or "ok"
        return name, True, f"{detail} ({time.time() - t0:.1f}s)"
    except Exception as exc:  # noqa: BLE001
        return name, False, scrub(f"{type(exc).__name__}: {exc}")[:160]


def run() -> int:
    cfg = Config.load()
    s = cfg.secrets
    today = date.today()
    fh = {"X-Finnhub-Token": s.finnhub}
    fb = "https://finnhub.io/api/v1"

    def finnhub_quote():
        d = get_json(f"{fb}/quote", params={"symbol": "AAPL"}, headers=fh, retries=0)
        return f"AAPL {d.get('c')}"

    def finnhub_premium(path, params):
        def f():
            try:
                get_json(f"{fb}{path}", params=params, headers=fh, retries=0)
                return "זמין"
            except SourceError as exc:
                if "403" in str(exc) or "401" in str(exc):
                    raise SourceError("לא זמין במסלול החינמי") from exc
                raise
        return f

    def gemini_models():
        d = get_json("https://generativelanguage.googleapis.com/v1beta/models",
                     headers={"x-goog-api-key": s.gemini}, params={"pageSize": 200}, retries=0)
        names = {m["name"].split("/", 1)[1] for m in d.get("models", [])}
        wanted = cfg.s("llm", "models") or []
        have = [m for m in wanted if m in names]
        missing = [m for m in wanted if m not in names]
        if not have:
            raise SourceError(f"אף מודל מהרשימה לא קיים. דוגמאות: {sorted(n for n in names if 'flash' in n)[:5]}")
        return f"זמינים: {', '.join(have)}" + (f" · חסרים: {', '.join(missing)}" if missing else "")

    def gemini_call():
        from ..llm.gemini import Gemini
        g = Gemini(s.gemini, cfg.s("llm", "models") or [], retries=1)
        out = g.generate_json("Return JSON only.", 'Return {"ok": true}')
        return f"{g.used_model}: {out}"

    def telegram():
        d = get_json(f"https://api.telegram.org/bot{s.telegram_token}/getMe", retries=0)
        return "@" + d["result"]["username"]

    def tiingo():
        d = get_json("https://api.tiingo.com/tiingo/daily/spy/prices",
                     params={"startDate": (today - timedelta(days=7)).isoformat()},
                     headers={"Authorization": f"Token {s.tiingo}"}, retries=0)
        return f"SPY {len(d)} ימים"

    def fred():
        d = get_json("https://api.stlouisfed.org/fred/series/observations",
                     params={"series_id": "DGS10", "api_key": s.fred, "file_type": "json",
                             "sort_order": "desc", "limit": 1}, retries=0)
        o = d["observations"][0]
        return f"DGS10 {o['value']} ({o['date']})"

    def fred_calendar():
        d = get_json("https://api.stlouisfed.org/fred/releases/dates",
                     params={"api_key": s.fred, "file_type": "json", "realtime_start": today.isoformat(),
                             "realtime_end": (today + timedelta(days=14)).isoformat(),
                             "include_release_dates_with_no_data": "true", "limit": 1000}, retries=0)
        return f"{len(d.get('release_dates', []))} פרסומים ב-14 הימים הקרובים"

    def coingecko():
        d = get_json("https://api.coingecko.com/api/v3/simple/price", params={"ids": "bitcoin", "vs_currencies": "usd"},
                     headers={"x-cg-demo-api-key": s.coingecko} if s.coingecko else {}, retries=0)
        return f"BTC ${d['bitcoin']['usd']:,}"

    def sec():
        if "@" not in s.sec_contact:
            raise SourceError("SEC_CONTACT חסר (צריך אימייל)")
        d = get_json("https://data.sec.gov/submissions/CIK0000320193.json",
                     headers={"User-Agent": f"Newsroom personal research {s.sec_contact}"}, retries=0)
        return f"Apple: {d['filings']['recent']['form'][0]}"

    def feed(url):
        return lambda: f"{len(request('GET', url, timeout=10, retries=0).content) // 1024}KB"

    def yahoo():
        from ..collectors.yahoo_fallback import quote
        q = quote("^VIX")
        if not q:
            raise SourceError("no data")
        return f"VIX {q.price}"

    checks = [
        ("Telegram", telegram),
        ("Finnhub quote", finnhub_quote),
        ("Finnhub market news", finnhub_premium("/news", {"category": "general"})),
        ("Finnhub company news", finnhub_premium("/company-news", {"symbol": "AAPL", "from": (today - timedelta(days=2)).isoformat(), "to": today.isoformat()})),
        ("Finnhub earnings calendar", finnhub_premium("/calendar/earnings", {"from": today.isoformat(), "to": today.isoformat()})),
        ("Finnhub profile", finnhub_premium("/stock/profile2", {"symbol": "AAPL"})),
        ("Finnhub candles (צפוי: בתשלום)", finnhub_premium("/stock/candle", {"symbol": "AAPL", "resolution": "D", "from": int(time.time()) - 86400 * 10, "to": int(time.time())})),
        ("Finnhub economic calendar (צפוי: בתשלום)", finnhub_premium("/calendar/economic", {})),
        ("Tiingo", tiingo),
        ("FRED", fred),
        ("FRED release calendar", fred_calendar),
        ("CoinGecko", coingecko),
        ("SEC EDGAR", sec),
        ("Gemini models", gemini_models),
        ("Gemini call", gemini_call),
        ("Yahoo (גיבוי)", yahoo),
    ]
    for f in cfg.sources.get("rss", []) + cfg.sources.get("fed", []):
        checks.append((f"RSS {f['key']}", feed(f["url"])))

    results = [_check(n, fn) for n, fn in checks]
    lines = [f"{'✅' if ok else '❌'} {n}: {d}" for n, ok, d in results]
    report = "🔎 בדיקת מקורות\n" + "\n".join(lines)
    print(report)
    if s.telegram_token and s.telegram_chat_id:
        try:
            from ..telegram.send import Telegram, esc
            Telegram(s.telegram_token, s.telegram_chat_id).send(esc(report))
        except Exception as exc:  # noqa: BLE001
            print("telegram send failed:", scrub(str(exc)))
    return 0
