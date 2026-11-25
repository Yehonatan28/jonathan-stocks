"""Compare & correlate: alignment, indexed performance, beta, correlation and rolling windows."""
from datetime import date, timedelta

import relative as R


def pts(closes, start=date(2024, 1, 1), skip=()):
    out, d, i = [], start, 0
    while i < len(closes):
        if d.weekday() < 5:
            if d not in skip:
                out.append((d, closes[i]))
            i += 1
        d += timedelta(days=1)
    return out


def walk(n, f, start=100.0):
    c = [start]
    for i in range(1, n):
        c.append(c[-1] * (1 + f(i)))
    return c


def test_alignment_drops_days_missing_anywhere():
    a = pts([1.0] * 10)
    b = pts([2.0] * 10, skip={date(2024, 1, 3)})
    dates, px = R.align({'A': a, 'B': b})
    assert date(2024, 1, 3) not in dates and len(dates) == 9 and len(px['A']) == len(px['B']) == 9


def test_compare_beta_two_and_perfect_correlation():
    spy = walk(300, lambda i: 0.01 * ((i * 7) % 5 - 2) / 2)
    lev = [100.0]
    for i in range(1, 300):
        lev.append(lev[-1] * (1 + 2 * (spy[i] / spy[i - 1] - 1)))          # twice the benchmark's daily move
    r = R.compare({'LEV': pts(lev), 'SPY': pts(spy)})
    assert r['ok'] and r['symbols'] == ['LEV']
    assert r['stats']['LEV']['beta'] == 2.0
    assert r['indexed'][0]['LEV'] == 100.0
    assert r['stats']['LEV']['returns']['1M'] == round((lev[-1] / lev[-22] - 1) * 100, 2)


def test_correlation_matrix_and_rolling():
    base = walk(200, lambda i: 0.01 * ((i * 3) % 7 - 3) / 3)
    inv = [100.0]
    for i in range(1, 200):
        inv.append(inv[-1] * (1 - (base[i] / base[i - 1] - 1)))
    s = {'A': pts(base), 'B': pts(inv), 'SPY': pts(base)}
    r = R.compare(s)
    assert r['symbols'] == ['A', 'B'] and r['correlation'] == [[1.0, -1.0], [-1.0, 1.0]]
    roll = R.rolling(s, 'A', 'B')
    assert len(roll) == 199 - 60 + 1 and all(x['corr'] == -1.0 for x in roll)


def test_short_overlap_is_refused():
    assert R.compare({'A': pts([1.0] * 10), 'SPY': pts([1.0] * 10)})['ok'] is False


def test_one_year_with_252_shared_days_is_not_a_dash():
    # a year of daily data holds 252 closes = 251 sessions of change; that is a 1Y figure, with its start shown
    c = walk(252, lambda i: 0.001)
    out = R.compare({'AAA': pts(c), 'SPY': pts(walk(252, lambda i: 0.0005))})
    st = out['stats']['AAA']
    assert st['returns']['1Y'] == round((c[-1] / c[0] - 1) * 100, 2)
    assert st['windows']['1Y']['sessions'] == 251 and st['windows']['1Y']['from'] == out['start']


def test_window_too_short_gives_a_reason():
    out = R.compare({'AAA': pts(walk(200, lambda i: 0.001)), 'SPY': pts(walk(200, lambda i: 0.0))})
    st = out['stats']['AAA']
    assert st['returns']['1Y'] is None and '252' in st['windows']['1Y']['reason']
    assert st['returns']['6M'] is not None and st['windows']['6M']['sessions'] == 126
