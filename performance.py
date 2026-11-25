"""Portfolio performance from transactions and daily closes.

Method (shown to the user as written here):
- The account is valued at every close of the benchmark's trading calendar from the first
  transaction: shares held x that day's close (the latest close on or before the day) + cash.
  Transactions dated on a non-trading day count from the next trading day.
- Daily closes from the data source are split-adjusted, so holdings before a split recorded in
  the ledger are converted at the split ratio. A split that happened but was not recorded will
  distort the history before it.
- Return is time-weighted: each day's return is (value - that day's deposits + withdrawals) /
  previous value - 1, and the days are chained. Money moving in or out is not a gain or a loss.
  Days that start from a zero value (before the first deposit or purchase) are skipped.
- Only one currency is measured (the account currency); transactions in other currencies are
  left out and listed, since no exchange rate is applied.
- Statistics are reported only with enough history: annualised return from 252 trading days;
  volatility, Sharpe and Sortino from 60 daily returns; beta and alpha from 60 days that overlap
  the benchmark. Annualising uses 252 trading days. Sharpe and Sortino subtract the risk-free
  rate given (the 13-week US Treasury bill yield when it is available, otherwise zero, which is
  stated). Alpha is the annualised intercept of the daily regression on the benchmark.
- Maximum drawdown is the largest fall from a running peak of the time-weighted index.
"""
import math
from bisect import bisect_right
from collections import defaultdict
from datetime import date

import ledger

MIN_STATS = 60
MIN_ANNUAL = 252


def _d(s):
    return s if isinstance(s, date) else date.fromisoformat(str(s)[:10])


def _closes_at(points):
    """[(date, close)] -> function(day) giving the latest close on or before day, else None."""
    pts = sorted((_d(d), c) for d, c in points if c is not None)
    days = [d for d, _ in pts]

    def at(day):
        i = bisect_right(days, day)
        return pts[i - 1][1] if i else None
    return at


def _mean(xs):
    return sum(xs) / len(xs)


def _std(xs):
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def compute(transactions, closes, benchmark, currency='USD', rf_annual=None):
    """transactions: ledger transactions; closes: {ticker: [(date, close)]}; benchmark:
    [(date, close)] of the index fund, which also gives the trading calendar."""
    txs, skipped = [], []
    for i, t in enumerate(transactions):
        c = ledger.clean(t)
        c['_seq'] = i
        if c['currency'] != currency:
            skipped.append(c)
            continue
        txs.append(c)
    if not txs:
        return {'ok': False, 'reason': f'No {currency} transactions to measure.', 'skipped': len(skipped)}
    ledger.compute(txs)                        # raises LedgerError if the history does not balance
    txs.sort(key=lambda x: (x['date'], x['_seq']))
    start = _d(txs[0]['date'])
    cal = sorted({_d(d) for d, c in benchmark if c is not None and _d(d) >= start})
    if len(cal) < 2:
        return {'ok': False, 'reason': 'Not enough trading days since the first transaction.', 'skipped': len(skipped)}
    bench_at = _closes_at(benchmark)
    price_at = {s: _closes_at(p) for s, p in closes.items()}
    splits = defaultdict(list)                 # ticker -> [(date, ratio)]
    for t in txs:
        if t['type'] == 'split':
            splits[t['ticker']].append((_d(t['date']), t['ratio']))

    def factor_after(sym, day):
        f = 1.0
        for d, r in splits.get(sym, []):
            if d > day:
                f *= r
        return f

    qty, cash = defaultdict(float), 0.0
    k, series, missing = 0, [], set()
    for day in cal:
        flow = 0.0
        while k < len(txs) and _d(txs[k]['date']) <= day:
            t = txs[k]
            ty = t['type']
            if ty == 'deposit':
                cash += t['amount']; flow += t['amount']
            elif ty == 'withdrawal':
                cash -= t['amount']; flow -= t['amount']
            elif ty == 'fee':
                cash -= t['amount']
            elif ty == 'dividend':
                cash += t['amount']
            elif ty == 'buy':
                qty[t['ticker']] += t['qty']; cash -= t['qty'] * t['price'] + t['fee']
            elif ty == 'sell':
                qty[t['ticker']] -= t['qty']; cash += t['qty'] * t['price'] - t['fee']
            elif ty == 'split':
                qty[t['ticker']] *= t['ratio']
            k += 1
        value = cash
        for sym, q in qty.items():
            if abs(q) < 1e-9:
                continue
            px = price_at[sym](day) if sym in price_at else None
            if px is None:
                missing.add(sym)
                continue
            value += q * factor_after(sym, day) * px
        series.append({'date': day.isoformat(), 'value': round(value, 2), 'flow': round(flow, 2),
                       'bench': bench_at(day)})

    # time-weighted daily returns
    rets, idx, b_idx = [], [], []
    level, b0 = 100.0, None
    for prev, cur in zip(series, series[1:]):
        if prev['value'] <= 0:
            continue
        r = (cur['value'] - cur['flow']) / prev['value'] - 1
        level *= 1 + r
        rets.append((cur['date'], r, (cur['bench'] / prev['bench'] - 1) if cur['bench'] and prev['bench'] else None))
        if b0 is None:
            b0 = prev['bench']
            idx.append({'date': prev['date'], 'portfolio': 100.0, 'benchmark': 100.0})
        idx.append({'date': cur['date'], 'portfolio': round(level, 4),
                    'benchmark': round(cur['bench'] / b0 * 100, 4) if cur['bench'] and b0 else None})

    out = {'ok': True, 'currency': currency, 'start': series[0]['date'], 'end': series[-1]['date'],
           'days': len(rets), 'series': idx, 'values': [{'date': s['date'], 'value': s['value']} for s in series],
           'skipped_other_currency': len(skipped), 'unpriced': sorted(missing),
           'rf_annual': rf_annual, 'method': __doc__.split('Method (shown to the user as written here):')[1].strip()}
    stats = {'total_return': None, 'benchmark_return': None, 'cagr': None, 'volatility': None, 'sharpe': None,
             'sortino': None, 'beta': None, 'alpha': None, 'max_drawdown': None, 'max_drawdown_peak': None,
             'max_drawdown_trough': None, 'best_day': None, 'worst_day': None}
    out['stats'] = stats
    if not rets:
        return out
    stats['total_return'] = round((level / 100 - 1) * 100, 2)
    if idx and idx[-1]['benchmark'] is not None:
        stats['benchmark_return'] = round(idx[-1]['benchmark'] - 100, 2)
    peak, peak_d, worst, wpk, wtr = idx[0]['portfolio'], idx[0]['date'], 0.0, None, None
    for p in idx:
        if p['portfolio'] > peak:
            peak, peak_d = p['portfolio'], p['date']
        dd = p['portfolio'] / peak - 1
        if dd < worst:
            worst, wpk, wtr = dd, peak_d, p['date']
    stats['max_drawdown'] = round(worst * 100, 2)
    stats['max_drawdown_peak'], stats['max_drawdown_trough'] = wpk, wtr
    best = max(rets, key=lambda x: x[1]); worst_day = min(rets, key=lambda x: x[1])
    stats['best_day'] = {'date': best[0], 'return': round(best[1] * 100, 2)}
    stats['worst_day'] = {'date': worst_day[0], 'return': round(worst_day[1] * 100, 2)}
    n = len(rets)
    if n >= MIN_ANNUAL:
        stats['cagr'] = round(((level / 100) ** (252 / n) - 1) * 100, 2)
    if n >= MIN_STATS:
        r = [x[1] for x in rets]
        rf_d = (rf_annual or 0) / 100 / 252
        sd = _std(r)
        stats['volatility'] = round(sd * math.sqrt(252) * 100, 2)
        ex = [x - rf_d for x in r]
        if sd > 0:
            stats['sharpe'] = round(_mean(ex) / sd * math.sqrt(252), 2)
        downside = [min(0.0, x) for x in ex]
        dd_dev = math.sqrt(sum(x * x for x in downside) / len(downside))
        if dd_dev > 0:
            stats['sortino'] = round(_mean(ex) / dd_dev * math.sqrt(252), 2)
        pairs = [(x[1], x[2]) for x in rets if x[2] is not None]
        if len(pairs) >= MIN_STATS:
            ps, bs = [p for p, _ in pairs], [b for _, b in pairs]
            mb, mp = _mean(bs), _mean(ps)
            var_b = sum((b - mb) ** 2 for b in bs) / (len(bs) - 1)
            if var_b > 0:
                cov = sum((p - mp) * (b - mb) for p, b in pairs) / (len(pairs) - 1)
                beta = cov / var_b
                stats['beta'] = round(beta, 2)
                stats['alpha'] = round((mp - beta * mb) * 252 * 100, 2)
    return out
