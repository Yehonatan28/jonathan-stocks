# Jonathan Stocks · Financial intelligence & portfolio analytics

**Live:** https://jonathan-stocks.vercel.app · [About](https://jonathan-stocks.vercel.app/about) ·
[Data & methodology](https://jonathan-stocks.vercel.app/methodology)

Market context, company research, portfolio accounting and risk tools in one workstation, built around
three rules: **every number shows its source and freshness**, **nothing is invented** (a figure without
its inputs is a dash, never a guess), and **information, not advice** (no buy or sell calls).

## Areas

| Area | Tabs |
|---|---|
| **Market** | Overview (market now, today in brief with its basis, your names, breadth, sectors, cross-asset, Fear & Greed), Heatmap (sector treemap with find, sector isolate and table view), News, Calendar |
| **Research** | Company (SEC filings, annual and quarterly, printable report), Screener, Compare (base 100 against SPY, risk, correlation), Trend view, Assistant |
| **Portfolio** | Holdings (stops), Transactions (FIFO P&L and performance), Watchlist, Daily check (rules on the last close), Risk (exposure and limit breaches), Alerts |
| **Lab** | Strategy Lab (rules against buy and hold, with costs), Engine replay, Gaps |

Every screen has a title, one sentence on what it is for and one primary action; global search (Ctrl K)
finds companies and symbols from anywhere. Addresses are stable (`#/research?t=MSFT`, `#/relative?s=AAPL,MSFT`,
`#/lab?t=NVDA`) and the last symbol follows you between tools. Every screen shows a provenance badge: source,
status (*Delayed*, *End of day*, *As filed*, *As published*, *Schedule*, *Estimated*), the date the data is from
and when it was retrieved. Display menu: dark or light theme, comfortable or compact density, English or Hebrew
(right to left).

## Architecture

```
Browser (vanilla JS, no framework)          Flask service (Vercel serverless)            Sources
  shell.js   areas, tabs, provenance  ──►    app.py         routes, security, cache  ──►  Yahoo Finance (per-symbol daily bars)
  market.js  screener.js research.js         provenance.py  X-Data-* headers              SEC EDGAR XBRL company facts
  ledger.js  risk.js lab.js relative.js      quant/         one indicator library         CNN Fear & Greed
  search.js  chartframe.js prefs i18n          marketintel scanner fundamentals             Publisher RSS (CNBC, FT, Globes, ...)
  app.js     legacy modules
                                             ledger performance riskx strategylab relative
                                             storage.py     Turso (libSQL over HTTP) / SQLite
```

- **One indicator library** (`quant/indicators.py`): SMA, EMA, Wilder RSI and ATR, ADX, MACD, Bollinger,
  OBV, VWAP, stochastic. Causal by construction and tested against hand calculations.
- **Pure calculation modules** (no I/O) for breadth, screening, SEC parsing, the ledger, performance,
  risk, backtests and comparison; the routes only fetch and pass data in. Each module's method text is the
  one shown on its screen and on the methodology page.
- **Provenance**: every data answer carries `X-Data-Set`, `X-Data-Source`, `X-Data-Status` and
  `X-Data-Retrieved`; a cached answer reports the time of the original fetch (`provenance.py`).
- **Resilient quotes**: when Yahoo refuses the batch endpoints from the host (HTTP 429 on the crumb), a
  per-symbol path derives price, 50/200-day averages, the 52-week range and relative volume from a year of
  daily bars; failing paths are skipped for ten minutes; `/api/health` reports which path answered.

## Security and privacy

- Passwords hashed with PBKDF2; signed, HttpOnly, Secure, SameSite=Lax session cookie; session key stable
  across serverless instances.
- Content-Security-Policy, frame, MIME and referrer headers, HSTS, `no-store` on API answers.
- Sign-in throttle shared through the database (keyed hash of the address, never the address); per-address
  API budget.
- Per-user isolation tested (another user cannot read, change or delete your rows); guest mode keeps data in
  the browser and guest calculations are computed in memory and not stored; account deletion with password.
- No analytics, no ads, no tracking cookies. See `/privacy`.

## Tests

```
python test_engine.py      # trend engine (36)
python test_news.py        # news aggregation (22)
python test_security.py    # auth, isolation, throttles, headers (28 checks)
python -m pytest -q tests  # indicators, storage (Turso protocol), provenance, breadth, screener, SEC parser,
                           # ledger + API, performance, risk, Strategy Lab (incl. no-look-ahead), comparison,
                           # public pages and account deletion (78)
```

Calculations are checked against numbers worked out by hand (RSI 70.4641, FIFO gains, time-weighted returns
that ignore deposits, beta 2.0 for a doubled series, gap fills at the open, and more).

## Run locally

```
pip install -r requirements.txt
python devserver.py        # the real app with synthetic market data, http://127.0.0.1:5055
python app.py              # the real app against live sources
```

Environment (production): `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN` (accounts), `SEC_CONTACT` (an email the
SEC requires in the User-Agent), optional `SECRET_KEY`. Nothing secret lives in the code.

## Known limitations

See [docs/LIMITATIONS.md](docs/LIMITATIONS.md). In short: quotes are delayed; the screener's P/E and yield use
the last full year's EPS and dividends from SEC filings (not trailing twelve months); forward P/E and P/B are
unavailable while Yahoo refuses its batch quote endpoint to the host; Tel Aviv listings have no SEC
filings; performance is measured one currency at a time; backtests are long-only with full allocation.

## Documents

- [docs/AUDIT.md](docs/AUDIT.md): the audit the transformation started from
- [docs/PLAN.md](docs/PLAN.md): the phased plan and what is done
- [docs/RISK_ENGINE.md](docs/RISK_ENGINE.md): the command centre's rules in detail
- [docs/LIMITATIONS.md](docs/LIMITATIONS.md): what it does not do, and why
- [docs/CV.md](docs/CV.md): project descriptions for a CV and LinkedIn
