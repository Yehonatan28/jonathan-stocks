"""Compare and correlate a handful of symbols on their daily closes.

Method (shown to the user as written here):
- Series are aligned on the dates every symbol traded; a day missing for any of them is dropped,
  so every figure compares the same days.
- Performance is indexed to 100 on the first shared date. Period returns count 21, 63, 126 and
  252 shared sessions back; year-to-date runs from the last close of the previous year.
- Volatility is the standard deviation of daily returns x sqrt(252). Maximum drawdown is the
  largest fall from a running peak. Beta is the slope of the symbol's daily returns on the
  benchmark's (SPY) over the same days.
- Correlation is the Pearson correlation of daily returns over the whole window; the rolling
  view recomputes it over each trailing 60-day stretch.
"""
import math

ROLL = 60


def align(series):
    """series: {sym: [(date, close)]} -> (dates, {sym: [close]}) on the shared dates."""
    maps = {s: {d: c for d, c in pts if c} for s, pts in series.items() if pts}
    if not maps:
        return [], {}
    shared = sorted(set.intersection(*(set(m) for m in maps.values())))
    return shared, {s: [m[d] for d in shared] for s, m in maps.items()}


def _rets(c):
    return [c[i] / c[i - 1] - 1 for i in range(1, len(c))]


def _std(x):
    m = sum(x) / len(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1))


def _corr(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if not va or not vb:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb)


def _beta(a, b):
    mb, ma = sum(b) / len(b), sum(a) / len(a)
    vb = sum((y - mb) ** 2 for y in b)
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / vb if vb else None


def compare(series, benchmark='SPY'):
    dates, px = align(series)
    if len(dates) < 30:
        return {'ok': False, 'reason': 'Fewer than 30 shared trading days for these symbols.'}
    syms = [s for s in series if s in px and s != benchmark] or list(px)
    rets = {s: _rets(px[s]) for s in px}
    out = {'ok': True, 'start': dates[0].isoformat(), 'end': dates[-1].isoformat(), 'days': len(dates), 'symbols': syms}
    out['indexed'] = [{'date': d.isoformat(), **{s: round(px[s][i] / px[s][0] * 100, 3) for s in syms}}
                      for i, d in enumerate(dates)]
    year = dates[-1].year
    prior = max((i for i, d in enumerate(dates) if d.year < year), default=None)
    stats = {}
    for s in syms:
        c = px[s]
        per = {lab: (round((c[-1] / c[-1 - n] - 1) * 100, 2) if len(c) > n else None)
               for lab, n in (('1M', 21), ('3M', 63), ('6M', 126), ('1Y', 252))}
        per['YTD'] = round((c[-1] / c[prior] - 1) * 100, 2) if prior is not None else None
        peak, mdd, dd = c[0], 0.0, []
        for v in c:
            peak = max(peak, v)
            mdd = min(mdd, v / peak - 1)
            dd.append(round((v / peak - 1) * 100, 2))
        r = rets[s]
        stats[s] = {'returns': per, 'total': round((c[-1] / c[0] - 1) * 100, 2),
                    'volatility': round(_std(r) * math.sqrt(252) * 100, 2) if len(r) > 20 else None,
                    'max_drawdown': round(mdd * 100, 2),
                    'beta': round(_beta(r, rets[benchmark]), 2) if benchmark in rets and s != benchmark else None,
                    'drawdown': dd}
    out['stats'] = stats
    out['benchmark'] = benchmark if benchmark in px else None
    m = [[(1.0 if a == b else (round(_corr(rets[a], rets[b]), 2) if _corr(rets[a], rets[b]) is not None else None))
          for b in syms] for a in syms]
    out['correlation'] = m
    out['method'] = __doc__.split('Method (shown to the user as written here):')[1].strip()
    out['dates'] = [d.isoformat() for d in dates]
    return out


def rolling(series, a, b, window=ROLL):
    dates, px = align({a: series[a], b: series[b]})
    ra, rb = _rets(px[a]), _rets(px[b])
    out = []
    for i in range(window, len(ra) + 1):
        c = _corr(ra[i - window:i], rb[i - window:i])
        out.append({'date': dates[i].isoformat(), 'corr': round(c, 3) if c is not None else None})
    return out
