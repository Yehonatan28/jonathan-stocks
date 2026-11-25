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
- [x] "Your names today" on Market Overview: big moves, unusual volume, 52-week extremes, stops near or hit, below the 200-day, earnings within five days, for holdings and watchlist; each a fact with its number, linked to the stock (`digest.py`)
- [x] Company research: 5 fiscal years + 8 quarters from SEC XBRL company facts (restatements resolved by latest filing, derived Q4 marked), margins, growth, ROE, ROIC, FCF, cash conversion, debt/equity with formulas; charts; summary built only from reported figures; source and method shown (`fundamentals.py`). Needs `SEC_CONTACT` on the host (🔑). Valuation history and estimates vs actuals: later
- [x] Stock scanner: S&P 500 / Nasdaq-100 / both; valuation, trend and activity fields with per-field coverage; presets, range filters, sector, sort, columns, saved screens (this browser), CSV export (`scanner.py`). Multi-factor score: later, only with sufficient inputs
- [ ] Charting: candles/OHLC/line/area, 1D–MAX, indicators with settings, crosshair, levels, markers, interpretation panel from actual values
- [x] Portfolio accounting: transactions (buy/sell/dividend/deposit/withdrawal/fee/split), FIFO lots, realised/unrealised P&L, cash, per-currency totals without conversion, oversell rejected, history must balance on every write and delete; account or browser-only (guest, computed statelessly); CSV import/export; method on the page (`ledger.py`)
- [x] Performance analytics: time-weighted return against SPY (deposits/withdrawals neutral), CAGR from 252 days, volatility/Sharpe/Sortino/beta/alpha from 60 days, max drawdown with dates, best/worst day; risk-free = average 13-week bill yield or zero (stated); split-adjusted closes handled; one currency at a time (`performance.py`)
- [x] Risk engine extension: Portfolio Risk review against the user's limits (largest position, sector, risk per trade, total open risk), unprotected positions, stops under 1 or over 4 ATR, 60-day correlation matrix and high pairs; long/short position sizing capped by the position limit (`riskx.py`)

## Phase 3 · Analytical differentiation
- [x] Backtesting lab (Strategy Lab): entries/exits from RSI, MA, MA cross, MACD cross, breakout, time; ATR stop, target and trailing stop checked intrabar with gap fills; commission and slippage both sides; next-open fills with a no-look-ahead test; equity vs buy-and-hold, drawdown, monthly heatmap, trade list; presets (`strategylab.py`)
- [x] Comparison: up to eight symbols on shared days, indexed performance, period returns, volatility, drawdown, beta to SPY; filed fundamentals side by side for four (`relative.py`)
- [ ] ETF research (holdings, sectors, expense ratio where available)
- [x] Correlation: matrix of daily returns, 60-day rolling correlation for any pair, drawdown comparison (in Compare & Correlate)
- [x] Economic, earnings and dividend calendars from Nasdaq's public calendar (no key), ten trading days, holdings and watchlist marked, estimates labelled (`calendars.py`)
- [x] Alerts: price, day change, RSI, MA cross, relative volume, earnings within N days, distance to stop; evaluated by the server on daily bars while the app is open (stated), history and optional browser notifications (`alertrules.py`)

## Phase 4 · Intelligence layer
- [x] Research assistant (Gemini) grounded only in platform data: server-chosen context with source ids, citations, estimates kept apart, no recommendations, every number checked against the context and unverified ones marked, holdings only with per-question consent, 10 questions per 10 minutes (`assistant.py`)
- [ ] Research report generator with PDF export
- [x] News: per company feeds, deduplication, machine-labelled tone from finance word lists (English and Hebrew, negation aware) with the deciding words shown, tone filter and counts (`tone.py`)

## Phase 5 · Launch quality
- [ ] Public landing page with real screenshots, methodology, demo with clearly marked sample data
- [x] Privacy policy (what is stored where, third parties), terms, financial disclaimer, data sources & methodology page assembled from the modules' own method texts; account deletion with password (`pages.py`)
- [x] Metadata: favicon (SVG + PNG), app icons, social preview image (1200x630), Open Graph and Twitter tags, canonical URLs, robots rules (API not indexed), dark manifest
- [x] Accessibility: axe-core (WCAG 2 A/AA) clean on all 17 screens and 5 public pages (contrast-checked heatmap scale and muted text, labelled controls, tab semantics). Performance: content-hashed static URLs cached for a year (immutable), chart libraries moved out of the head so first paint is not blocked. Structured logging: one JSON line per API request (path, status, ms, dataset; no address, user, body or query values), request ids, unexpected errors logged with the failing frame and answered without internals.
- [ ] Full test pass (financial, security, responsive, failure states), production deploy, rollback procedure
- [x] Final reports: README (features, architecture, security, tests, run), docs/LIMITATIONS.md, docs/CV.md (CV, LinkedIn, Hebrew); methodology page for data documentation
