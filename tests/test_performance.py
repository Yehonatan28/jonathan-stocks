"""Performance: time-weighted return ignores deposits, splits on adjusted closes, statistics gated
by history length, beta of a copy of the benchmark is 1."""
import math
from datetime import date, timedelta

import performance as P


def days(n, start=date(2024, 1, 1)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def tx(type_, d, **kw):
    return {'type': type_, 'date': d.isoformat() if isinstance(d, date) else d, **kw}


def test_twr_ignores_a_deposit():
    cal = days(4)
    bench = [(d, 100.0) for d in cal]
    # day0: deposit 1000 and buy 10 @ 100. day1: price 110 (+10%). day2: deposit 1100, price 110. day3: price 121 (+10% on the stock)
    px = [(cal[0], 100.0), (cal[1], 110.0), (cal[2], 110.0), (cal[3], 121.0)]
    txs = [tx('deposit', cal[0], amount=1000), tx('buy', cal[0], ticker='A', qty=10, price=100), tx('deposit', cal[2], amount=1100)]
    r = P.compute(txs, {'A': px}, bench)
    vals = [v['value'] for v in r['values']]
    assert vals == [1000.0, 1100.0, 2200.0, 2310.0]
    # chained: 1.10 x 1.00 x (2310/2200) = 1.155 -> +15.5%, although the account grew 131%
    assert r['stats']['total_return'] == 15.5
    assert r['stats']['cagr'] is None and r['stats']['volatility'] is None and r['stats']['beta'] is None


def test_split_with_adjusted_closes():
    cal = days(3)
    bench = [(d, 100.0) for d in cal]
    # a 2-for-1 split on day 2; the source's closes are already adjusted: 50, 50, 50 (was 100 before the split)
    txs = [tx('deposit', cal[0], amount=1000), tx('buy', cal[0], ticker='A', qty=10, price=100), tx('split', cal[2], ticker='A', ratio=2)]
    r = P.compute(txs, {'A': [(d, 50.0) for d in cal]}, bench)
    assert [v['value'] for v in r['values']] == [1000.0, 1000.0, 1000.0]
    assert r['stats']['total_return'] == 0.0


def test_drawdown_and_best_worst():
    cal = days(5)
    bench = [(d, 100.0) for d in cal]
    px = list(zip(cal, [100.0, 120.0, 90.0, 99.0, 130.0]))
    txs = [tx('buy', cal[0], ticker='A', qty=1, price=100), tx('deposit', cal[0], amount=100)]
    s = P.compute(txs, {'A': px}, bench)['stats']
    assert s['max_drawdown'] == -25.0 and s['max_drawdown_peak'] == cal[1].isoformat() and s['max_drawdown_trough'] == cal[2].isoformat()
    assert s['best_day']['return'] == round((130 / 99 - 1) * 100, 2) and s['worst_day']['return'] == -25.0


def test_statistics_with_enough_history_and_beta_one():
    cal = days(300)
    b = [100.0]
    for i in range(1, 300):
        b.append(b[-1] * (1 + 0.01 * math.sin(i * 1.3)))
    bench = list(zip(cal, b))
    txs = [tx('deposit', cal[0], amount=10000), tx('buy', cal[0], ticker='SPY', qty=100, price=100)]
    r = P.compute(txs, {'SPY': bench}, bench, rf_annual=0)
    s = r['stats']
    assert s['beta'] == 1.0 and abs(s['alpha']) < 0.01
    assert s['total_return'] == s['benchmark_return']
    assert s['cagr'] is not None and s['volatility'] > 0 and s['sharpe'] is not None and s['sortino'] is not None


def test_other_currency_left_out_and_counted():
    cal = days(3)
    txs = [tx('deposit', cal[0], amount=100), tx('deposit', cal[0], amount=500, currency='ILS')]
    r = P.compute(txs, {}, [(d, 1.0) for d in cal])
    assert r['skipped_other_currency'] == 1 and r['stats']['total_return'] == 0.0
