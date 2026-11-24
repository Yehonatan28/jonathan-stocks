# Jonathan Stocks · Audit of the existing application

Audited: 24 Nov 2026, against `main` at `0444688` (release #10), which both
https://jonathan-stocks.vercel.app and https://jonathan-stocks.onrender.com serve.

Method: read the whole codebase; ran the three test suites; drove every page of the
UI in a headless browser on desktop (1440 px) and phone (390 px) with the offline
dev server (`devserver.py`, synthetic data); called ten public API routes on both
live deployments from a GitHub Actions runner (read only: no accounts created,
nothing written).

## 1. Architecture

| Layer | What it is |
|---|---|
| Backend | Flask, one module `app.py` (1,142 lines) plus `engine.py` (analysis, risk, backtest, gaps), `market.py` (index constituents, Yahoo batch quotes, CNN Fear & Greed), `news.py` (RSS aggregator) |
| Frontend | One server-rendered page `templates/index.html` (2,145 lines of HTML, CSS and vanilla JS in one file); TradingView Lightweight Charts 4.1.3 and Chart.js 4.4.1 from CDNs |
| State | Signed-in: SQLite tables `users, portfolio, watchlist, alerts, pf_history, settings`. Guest: `localStorage` in the browser |
| Auth | Flask signed session cookie (HttpOnly, SameSite=Lax, Secure on hosts), salted password hashes, sign-in throttling, every row scoped to `user_id` (proved by `test_security.py`) |
| Caching | In-process dict with TTL (`cache_get/cache_set`), lost on every cold start |
| Data | Yahoo Finance unofficial endpoints (chart, quoteSummary, v7 quote with crumb, spark, search), CNN Fear & Greed (unofficial), 15 RSS feeds |
| Deploy | Vercel (serverless, `api/index.py`), Render free (`render.yaml`, gunicorn 1 worker, 8 threads) |
| Tests | `test_engine.py` 36/36, `test_news.py` 22/22, `test_security.py` all pass; `test_ui.js`, `test_flows.js` (Playwright) |

## 2. Feature inventory

Legend: ✅ fully functional · 🟡 partially functional · ❌ broken · 🎭 decorative only · ⬜ missing · 🔑 needs external credentials

| Area | Feature | Status | Evidence / note |
|---|---|---|---|
| Market | US index cards, Tel Aviv cards (TA-35/90/125 + 3 stocks) | ✅ | Render on both widths |
| Market | Ticker tape | ✅ | |
| Market | Fear & Greed gauge with components and history | ✅ | Live 200 in 0.2 s; CNN endpoint is unofficial |
| Market | "Market breadth" card | 🎭 | Computed from the 12 tape tickers only, labelled as market breadth |
| Market | S&P 500 / Nasdaq 100 heatmap, 507 names, extended hours | ✅ on Vercel · ❌ on Render | Vercel 200 in 7.9 s (489/507 covered). Render: no answer in 90 s, then the process died and every route returned 502 |
| Market | Sector treemap (top 100) | ✅ | Vercel 1.6 s, Render 33 s |
| Market | Market status, clock, Ctrl+K palette, glossary | ✅ | |
| Research | Global search (Yahoo search) | ✅ | |
| Research | Stock card: price, RSI, MACD, ATR %, Bollinger %B, volume ratio | 🟡 | Numbers disagree with the engine (see 3.2) |
| Research | Company profile panel | 🟡 | Yahoo quoteSummary profile + analyst trend; no statements, no valuation history |
| Research | Interactive chart: candles/line, periods, MA overlays, levels, backtest trades | ✅ | Lightweight Charts |
| Research | Earnings | 🟡 | Next date and EPS estimate only |
| Research | Compare | 🟡 | Head-to-head card of quick stats; no fundamentals, no normalised chart |
| Research | Financial statements, valuation multiples, scanner with fundamentals, ETF research | ⬜ | |
| Portfolio | Positions with live P&L, stops (fixed/trailing), targets | ✅ | |
| Portfolio | Transactions, lots, realised P&L, cash, dividends, fees, splits, currencies | ⬜ | A position is one row: qty × entry |
| Portfolio | Value history (`pf_history`) | 🟡 | The browser posts one value a day while open; gaps when not opened |
| Portfolio | Performance analytics (CAGR, volatility, Sharpe, beta, drawdown vs benchmark) | ⬜ | |
| Portfolio | Watchlist | ✅ | One list only |
| Risk | Command centre: urgent actions ranked by severity, open risk, unprotected positions, entry signals | ✅ | The strongest part of the product |
| Risk | Position sizing from account equity and risk % | ✅ | Long only |
| Risk | Correlation, sector/currency concentration, portfolio volatility | ⬜ | |
| Quant | Gap detector with fill status | ✅ | Vercel 1.8 s |
| Quant | Backtest of the engine's own rules on one ticker | ✅ | Fixed strategy; no costs or slippage settings; no monthly heatmap |
| Alerts | Price alerts | 🟡 | Price level only, fire only while the page is open (stated honestly in the UI) |
| News | RSS aggregator, Israel/US filters, illustrated headlines | 🟡 | Yahoo Finance feed returns 404; the rest answer |
| Accounts | Register / sign in | 🟡 | Works, but on Vercel the SQLite file lives in `/tmp` and is lost on a cold start; on Render free the disk is rebuilt on every deploy and sleep |
| Accounts | Guest mode (`localStorage`) | ✅ | Survives, per browser |
| Platform | Logos via `logo.clearbit.com` | ❌ (to confirm live) | Clearbit's free logo API was retired; the UI falls back to the symbol |
| Platform | Landing page, legal pages, data documentation, social preview/OG tags | ⬜ | |
| Platform | AI research assistant | ⬜ 🔑 | Needs an LLM key |
| Platform | Economic calendar | ⬜ 🔑 | FRED release calendar needs a key; FOMC dates can be static |

## 3. Highest-impact problems

1. **Accounts do not persist in production.** Vercel `/tmp` SQLite is wiped on cold start; Render resets its disk. Anyone who registers loses everything. Needs a hosted database (🔑).
2. **Contradictory indicator values between modules.** `/api/stock` computes RSI with an EWM span and ATR as the EWM of high−low; `engine.py` uses Wilder smoothing and true range. The same ticker shows two RSI/ATR values on two screens.
3. **Render cannot serve the heatmap.** The free instance stops answering and returns 502 for every route afterwards. Vercel is the production host; Render should be retired or limited.
4. **No fundamentals at all.** The product cannot yet "evaluate companies": no statements, margins, ROIC, valuation multiples or history.
5. **Portfolio is positions, not accounting.** No transactions, lots, realised P&L or cash, so returns, CAGR and Sharpe cannot be computed correctly.
6. **Data provenance is invisible.** Values carry no source, timestamp or live/delayed/historical status; the in-process cache can serve stale data without saying so.
7. **One 2,145-line HTML file.** Hard to extend to five workspaces without regressions; needs modules (no framework or build step required).
8. **Breadth is mislabelled.** "Market breadth" is 12 tickers, not the market.

## 4. What is sound and kept

The risk engine and its action list, the Wilder indicator code in `engine.py`, the gap
detector, the heatmap with batch quotes and crumb handling, the account isolation and
throttling (with tests), guest mode, the RSS aggregator and its tests, the chart
component. These are preserved and extended, not rewritten.

## 5. External dependencies found

| Need | Free option | Status |
|---|---|---|
| Persistent database | Turso (libSQL, SQLite-compatible) or Neon Postgres, free tiers | 🔑 owner must create the account and add the URL/token to Vercel |
| Fundamentals (statements) | SEC EDGAR XBRL `companyfacts` (official, US issuers, no key; a contact User-Agent is required) | Available |
| Estimates, earnings calendar, recommendation trends | Finnhub free tier (key exists in the owner's other project) or Yahoo quoteSummary (unofficial) | 🔑 for Finnhub |
| Macro calendar, Treasury yields | FRED (free key) | 🔑 |
| AI assistant | Gemini (key exists in the owner's other project) | 🔑 |
| Prices, history, search | Yahoo (unofficial, already in use; delayed) | Available, fragile |
