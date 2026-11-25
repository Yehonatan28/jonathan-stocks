# Project descriptions for a CV and LinkedIn

## One line (CV)
**Jonathan Stocks** — financial intelligence and portfolio analytics web app (Python/Flask, JavaScript,
Turso, Vercel): market breadth, SEC-statement research, FIFO portfolio accounting, time-weighted
performance, risk limits and a no-look-ahead backtester, with data provenance on every screen.
jonathan-stocks.vercel.app

## Three bullets (CV)
- Built and deployed a full-stack financial analytics platform (Flask, vanilla JS, Turso/libSQL, Vercel)
  with five workspaces: market intelligence, equity research, portfolio, quant & risk, and news.
- Implemented the financial core as tested, pure modules: one indicator library (Wilder RSI/ATR, MACD,
  ADX), an SEC XBRL parser (restatements, derived Q4), FIFO ledger, time-weighted returns with
  Sharpe/Sortino/beta, risk limits with ATR-based stop checks, and a backtester verified free of look-ahead;
  calculations checked against hand-computed values (160+ automated tests).
- Engineered for trust and resilience: source/status/retrieval-time headers on every data response,
  CSP and session hardening, per-user isolation tests, and a fallback quote path that kept market breadth
  working after the primary data endpoint began refusing the host.

## LinkedIn (project section)
**Jonathan Stocks · Financial intelligence & portfolio analytics**
A web workstation for researching markets and managing a portfolio, built around one principle: every
number shows where it came from and how fresh it is.

- *Market Intelligence:* breadth across all S&P 500 members, sector funds against the index, rates,
  currencies and commodities.
- *Equity Research:* five years of statements parsed from SEC filings, a screener over the S&P 500 and
  Nasdaq-100, and comparison of up to eight symbols with correlation.
- *Portfolio:* transaction ledger with FIFO lots and time-weighted performance against the S&P 500.
- *Quant & Risk:* risk against personal limits, position sizing, and a strategy backtester with next-open
  fills and costs.

Stack: Python (Flask, pandas), vanilla JavaScript, Chart.js, Turso (libSQL), Vercel; data from Yahoo
Finance, SEC EDGAR, CNN and publishers' RSS. Information only, not investment advice.

## Hebrew (for an Israeli CV)
**Jonathan Stocks** — פלטפורמת אנליטיקה פיננסית ומעקב תיק השקעות (Python/Flask, JavaScript, Turso, Vercel):
רוחב שוק על כל מניות ה-S&P 500, מחקר חברות מדוחות ה-SEC, הנהלת חשבונות לתיק בשיטת FIFO, תשואה משוקללת-זמן
מול המדד, מגבלות סיכון ובדיקה לאחור (backtesting) ללא הצצה לעתיד. לכל נתון מוצגים המקור והעדכניות שלו,
וכל החישובים מכוסים בבדיקות אוטומטיות מול חישוב ידני.
