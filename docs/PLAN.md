# Jonathan Stocks · Implementation plan and checklist

Positioning: **Jonathan Stocks: Advanced Financial Intelligence & Portfolio Analytics.**
Jonathan News (MarketScope) explains what is happening; Jonathan Stocks is the
analytical infrastructure to investigate what it means. News stays a supporting layer.

Principles: keep Flask + vanilla JS (no framework, no build step), split the single page
into modules; one calculation library used by every screen; every number carries its
source, timestamp and live/delayed/historical status; every financial formula has a
test with an independently computed expected value; nothing is fabricated: a value that
is not available is shown as unavailable.

Legend: [ ] to do · [~] in progress · [x] done · 🔑 needs an external credential

## Phase 1 · Foundations
- [x] Audit (docs/AUDIT.md)
- [x] Remove the buy/sell call and the invented "confidence" from the stock card; state the trend facts
- [x] One indicator library (`quant/indicators.py`: SMA, EMA, Wilder RSI, MACD, true-range ATR, ADX, Bollinger, OBV, VWAP, stochastic) used by every route; remove the duplicate math in `/api/stock`
- [x] Data provenance on every data answer: `X-Data-Set/Source/Status/Retrieved` headers (bodies unchanged, so no screen breaks), `/api/sources` catalogue, top-bar badge and panel per screen (`provenance.py`)
- [x] Cache with explicit age: a cache hit reports the time of the original fetch; the panel shows "retrieved HH:MM · N min ago"; nothing is labelled live
- [x] Storage adapter: SQLite locally, Turso (libSQL over HTTP) in production (`storage.py`), verified live; tables created idempotently
- [x] Security: stable session key on serverless, CSP + frame/nosniff/referrer/permissions headers, HSTS, no-store on API, sign-in throttle shared through the database (hashed addresses), per-address API budget, 8-character passwords
- [x] Design system: dark tokens (charcoal/navy layers, restrained green/red), type scale, spacing, table/chart styles, focus states, reduced motion
- [x] Split `templates/index.html` into `static/css/*.css` and `static/js/*.js` modules
- [x] Navigation: five workspaces, sidebar / tablet rail / phone tab bar with module sheet, breadcrumbs, an address per module (`#/<module>`), back button, Ctrl/Cmd+K search
- [x] Retire Render: every request there is forwarded (301, path and query kept) to the Vercel site

## Phase 2 · Core financial product
- [x] Market Intelligence: rates/FX/commodities/crypto snapshot with status per instrument (yields in bp); real breadth over all S&P 500 members (A/D, near 52w highs/lows, % above 50/200-day, cap- vs equal-weighted) with denominators; 11 sector funds over 1D/1W/1M/3M/YTD vs SPY; leaders/laggards (`marketintel.py`, tests by hand calculation). Rotation view: later
- [ ] "Market Opportunities & Alerts" centre built from watchlist, portfolio and filters, each item explained and linked
- [ ] Company research terminal: overview; 5-year annual/quarterly statements from SEC XBRL; margins, growth, ROE, ROIC, FCF, cash conversion; valuation multiples with history; earnings (actual vs estimate, clearly separated); dividends; structured data-grounded summary
- [x] Stock scanner: S&P 500 / Nasdaq-100 / both; valuation, trend and activity fields with per-field coverage; presets, range filters, sector, sort, columns, saved screens (this browser), CSV export (`scanner.py`). Multi-factor score: later, only with sufficient inputs
- [ ] Charting: candles/OHLC/line/area, 1D–MAX, indicators with settings, crosshair, levels, markers, interpretation panel from actual values
- [ ] Portfolio accounting: transactions (buy/sell/dividend/deposit/withdrawal/fee/split), FIFO lots, realised/unrealised P&L, cash, currency; documented methodology
- [ ] Performance analytics: cumulative return, benchmark, CAGR, volatility, Sharpe, Sortino, beta, alpha, max drawdown (only with enough history)
- [ ] Risk engine extension: long and short sizing, limits (per trade, portfolio, sector, single stock), concentration, correlation, unprotected positions, volatility-inconsistent stops

## Phase 3 · Analytical differentiation
- [ ] Backtesting lab: configurable entries/exits (RSI, MA, MACD, ATR), stops, targets, trailing, costs, slippage, next-bar execution (no look-ahead), equity/drawdown curves, monthly heatmap, benchmark
- [ ] Comparison of up to four companies, normalised charts
- [ ] ETF research (holdings, sectors, expense ratio where available)
- [ ] Correlation lab: matrix, rolling correlation, volatility, drawdown comparison
- [ ] Economic and earnings calendar (🔑 FRED / Finnhub for full coverage)
- [ ] Alerts: price, %, RSI, MA cross, volume, earnings, stop proximity; history; server-side monitoring only if a scheduler is available, otherwise stated as "while open"

## Phase 4 · Intelligence layer
- [ ] AI research assistant grounded in platform data, with sources, periods, facts vs estimates, a number validator, explicit consent before any private portfolio data leaves the server (🔑)
- [ ] Research report generator with PDF export
- [ ] News as a research layer: per company, portfolio and watchlist feeds, deduplication, machine-labelled sentiment

## Phase 5 · Launch quality
- [ ] Public landing page with real screenshots, methodology, demo with clearly marked sample data
- [ ] Privacy policy, terms, financial disclaimer, data sources and methodology page
- [ ] Metadata, favicon, social preview, robots rules (private pages not indexed)
- [ ] Performance (bundle, caching, chart rendering), accessibility (WCAG 2.2 AA targets), structured logging
- [ ] Full test pass (financial, security, responsive, failure states), production deploy, rollback procedure
- [ ] Final reports: features, data documentation, testing, known limitations, CV/LinkedIn description
