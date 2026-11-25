# Known limitations

Stated plainly, so nothing on the site implies more than it does.

## Data
- **Delayed, not real time.** Quotes come from Yahoo Finance's public endpoints and may lag the exchange by
  15 minutes or more; analysis uses daily bars. No screen is labelled live.
- **Valuation multiples.** P/E, forward P/E, P/B and dividend yield come from Yahoo's batch quote endpoint,
  which refuses the production host (HTTP 429 on its crumb). While that holds, those screener columns are
  hidden and marked unavailable. Trend and range fields are computed from daily bars instead and are present.
- **Market capitalisation** in the screener is the feed's figure when available, otherwise the index table's
  estimate, which can be weeks old (stated in the field's description).
- **SEC filings** cover US filers. Funds, foreign private issuers (20-F) and Tel Aviv listings have no 10-K
  statements; the page says so. Quarterly cash flow is not shown (10-Qs report it year-to-date).
- **News** depends on publishers' RSS feeds; Calcalist refuses automated clients and Bizportal has no feed.

## Portfolio
- Performance is measured in **one currency at a time**; no exchange rates are applied anywhere.
- The ledger records **long positions only**; selling more than is held is rejected.
- A split that happened but was not recorded will distort performance before it (the source's closes are
  split-adjusted).

## Backtests
- **Long-only, fully invested** in each trade; no position sizing, leverage or shorting in the Strategy Lab.
- Fills at the next open with the costs entered; no partial fills, no taxes, no borrow costs.
- A backtest describes the past under its assumptions; it does not predict results.

## Not built (yet)
- ETF holdings research (needs a holdings source that answers from the host).
- Economic and earnings calendars (needs a source that answers from the host or an API key).
- An AI research assistant (needs an API key and explicit consent before any portfolio data leaves the server).
- Server-side alert monitoring (alerts are checked while the app is open).
