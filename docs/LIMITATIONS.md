# Known limitations

Stated plainly, so nothing on the site implies more than it does.

## Data
- **Delayed, not real time.** Quotes come from Yahoo Finance's public endpoints and may lag the exchange by
  15 minutes or more; analysis uses daily bars. No screen is labelled live.
- **Valuation multiples.** Yahoo's batch quote endpoint refuses the production host (HTTP 429 on its crumb),
  so the screener's P/E is price over the **last full calendar year's diluted EPS** and the yield is that
  year's **dividends declared** over price, both from the SEC's cross-company frames (about 450 of 506 names
  have a P/E; loss-makers have none). These are not trailing-twelve-month figures. Forward P/E and P/B have no
  source that answers from the host and are hidden. Trend and range fields come from daily bars.
- **Market value** is last price × common shares outstanding from the latest filing's cover page (SEC frames).
  Companies with several share classes, foreign filers, and any figure that disagrees with the index table by more
  than a factor of 2.5 fall back to the static index-table estimate (Oct 2026), marked **est.** in the cell, counted
  above the table and in the heatmap's coverage line. Heatmap block sizes are this computed value, not the official
  index weight.
- **Same asset, same numbers:** every screen reads Yahoo daily bars or the same quote path, but the screener and
  heatmap are cached for 2 to 5 minutes and a company page for 1, so two screens opened a few minutes apart can
  show different last prices. Each screen's provenance panel gives its retrieval time.
- **SEC filings** cover US filers. Funds, foreign private issuers (20-F) and Tel Aviv listings have no 10-K
  statements; the page says so. Quarterly cash flow is not shown (10-Qs report it year-to-date).
- **News** depends on publishers' RSS feeds; Calcalist refuses automated clients and Bizportal has no feed.

## Portfolio
- Performance is measured in **one currency at a time**; no exchange rates are applied anywhere. Holdings totals
  are per currency; Tel Aviv prices are agorot (ILA) and shown as such, converted to shekels only for the total
  (÷100, no exchange rate).
- **Holdings and Transactions are two records**: Holdings carry stops (Daily check, Risk, Alerts), Transactions
  carry history (P&L, performance). They are compared per symbol on both screens and never added together; the
  only migration offered adds opening buys after confirmation and never edits or deletes.
- The ledger records **long positions only**; selling more than is held is rejected.
- A split that happened but was not recorded will distort performance before it (the source's closes are
  split-adjusted).

## Backtests
- **Long-only, fully invested** in each trade; no position sizing, leverage or shorting in the Strategy Lab.
- Fills at the next open with the costs entered; no partial fills, no taxes, no borrow costs.
- A backtest describes the past under its assumptions; it does not predict results.

## Interface
- **Hebrew** covers the shell (navigation, page headers, top bar, search, display menu, sign-in) and the home
  screen. Tables, forms and method notes inside the tools are still English.
- **Accessibility**: axe-core reports no WCAG 2.0/2.1/2.2 A or AA rule violations on 18 screens in both themes.
  That is an automated check only; it has not been tested with a screen reader by a person, and the heatmap's
  map view is not keyboard-navigable (its Table view is the accessible equivalent).
- The **light theme** recolours canvas charts when the theme changes on the home screen, heatmap, chart window and
  research; other open charts take the new colours when next drawn.

## Not built (yet)
- ETF holdings research (needs a holdings source that answers from the host).
- Server-side alert monitoring (alerts are checked while the app is open).
