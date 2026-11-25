# Jonathan Stocks · Financial intelligence & portfolio analytics

**Live:** https://jonathan-stocks.vercel.app · [About](https://jonathan-stocks.vercel.app/about) ·
[Data & methodology](https://jonathan-stocks.vercel.app/methodology)

Market context, company research, portfolio accounting and risk tools in one workstation, built around
three rules: **every number shows its source and freshness**, **nothing is invented** (a figure without
its inputs is a dash, never a guess), and **information, not advice** (no buy or sell calls).

## Workspaces

| Workspace | Modules |
|---|---|
| **Market Intelligence** | Market Overview: breadth over all S&P 500 members (advance/decline, % above 50/200-day, near 52-week highs/lows, cap- vs equal-weighted move), 11 sector funds vs SPY over 1D–YTD, rates/FX/commodities/crypto, leaders and laggards, CNN Fear & Greed. Market Heatmap (sector treemap). |
| **Equity Research** | Company Research: five fiscal years and eight quarters from SEC XBRL filings with ratios and formulas. Stock Screener over the S&P 500 and Nasdaq-100 with presets, saved screens and CSV export. Compare & Correlate: up to eight symbols, indexed performance, volatility, drawdown, beta, correlation matrix and rolling correlation, filed fundamentals side by side. |
| **Portfolio** | Holdings and watchlist. Transactions & P&L: buys, sells, dividends, cash, fees and splits with FIFO lots, realised and unrealised gains per currency, and time-weighted performance against SPY with Sharpe, Sortino, beta, alpha and drawdown (each only with enough history). |
| **Quant & Risk** | Risk Engine (daily action plan for stops). Portfolio Risk: weights, open risk to the stops, sector limits, stop distance in ATR, correlation, position sizing for long and short. Strategy Lab: user-defined rules backtested with next-open fills, costs and no look-ahead. Gap detection, engine replay, price alerts. |
| **Intelligence** | Market news from US and Israeli publishers (RSS), deduplicated, with per-symbol feeds. |

Every screen has an address (`#/research?t=MSFT`, `#/relative?s=AAPL,MSFT`), works at phone, tablet and
desktop widths, and shows a provenance badge: source, *Delayed / End of day / As filed*, and retrieval time.

## Architecture

```
Browser (vanilla JS, no framework)          Flask service (Vercel serverless)            Sources
  shell.js   navigation, provenance   ──►    app.py         routes, security, cache  ──►  Yahoo Finance (per-symbol daily bars)
  market.js  screener.js research.js         provenance.py  X-Data-* headers              SEC EDGAR XBRL company facts
  ledger.js  risk.js lab.js relative.js      quant/         one indicator library         CNN Fear & Greed
  app.js     legacy modules                  marketintel scanner fundamentals             Publisher RSS (CNBC, FT, Globes, ...)
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

See [docs/LIMITATIONS.md](docs/LIMITATIONS.md). In short: quotes are delayed; valuation multiples (P/E,
yield) are unavailable while Yahoo refuses the batch quote endpoint to the host; Tel Aviv listings have no SEC
filings; performance is measured one currency at a time; backtests are long-only with full allocation.

## Documents

- [docs/AUDIT.md](docs/AUDIT.md): the audit the transformation started from
- [docs/PLAN.md](docs/PLAN.md): the phased plan and what is done
- [docs/RISK_ENGINE.md](docs/RISK_ENGINE.md): the command centre's rules in detail
- [docs/LIMITATIONS.md](docs/LIMITATIONS.md): what it does not do, and why
- [docs/CV.md](docs/CV.md): project descriptions for a CV and LinkedIn
