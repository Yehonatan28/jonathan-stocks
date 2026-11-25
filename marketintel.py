"""Market intelligence: breadth, sector performance and a cross-asset snapshot.

Pure functions over data the caller has already fetched, so every number here can be
tested against a hand calculation. Nothing is estimated: a statistic that lacks its inputs
is returned as None together with the number of names it was computed over.
"""
from datetime import date, datetime, timezone

# GICS sectors and the SPDR fund that tracks each one; SPY is the benchmark.
SECTOR_ETFS = [
    ('Technology', 'XLK'), ('Financials', 'XLF'), ('Health Care', 'XLV'),
    ('Consumer Discretionary', 'XLY'), ('Communication Services', 'XLC'),
    ('Industrials', 'XLI'), ('Consumer Staples', 'XLP'), ('Energy', 'XLE'),
    ('Utilities', 'XLU'), ('Materials', 'XLB'), ('Real Estate', 'XLRE'),
]
BENCHMARK = 'SPY'

# (group, symbol, label, kind). kind decides how the move is expressed:
#   'price' -> percent change; 'yield' -> change in basis points of the quoted yield.
SNAPSHOT = [
    ('US equities', '^GSPC', 'S&P 500', 'price'),
    ('US equities', '^IXIC', 'Nasdaq Composite', 'price'),
    ('US equities', '^DJI', 'Dow Jones', 'price'),
    ('US equities', '^RUT', 'Russell 2000', 'price'),
    ('US equities', '^VIX', 'VIX', 'price'),
    ('Israel', '^TA125.TA', 'TA-125', 'price'),
    ('Israel', 'TA35.TA', 'TA-35', 'price'),
    ('Rates', '^IRX', 'US 13-week bill', 'yield'),
    ('Rates', '^FVX', 'US 5-year', 'yield'),
    ('Rates', '^TNX', 'US 10-year', 'yield'),
    ('Rates', '^TYX', 'US 30-year', 'yield'),
    ('Currencies', 'DX-Y.NYB', 'US dollar index', 'price'),
    ('Currencies', 'EURUSD=X', 'EUR/USD', 'price'),
    ('Currencies', 'ILS=X', 'USD/ILS', 'price'),
    ('Currencies', 'JPY=X', 'USD/JPY', 'price'),
    ('Commodities', 'GC=F', 'Gold', 'price'),
    ('Commodities', 'SI=F', 'Silver', 'price'),
    ('Commodities', 'CL=F', 'WTI crude', 'price'),
    ('Commodities', 'NG=F', 'Natural gas', 'price'),
    ('Crypto', 'BTC-USD', 'Bitcoin', 'price'),
]


def _pct(a, b):
    return round((a / b - 1) * 100, 2) if a is not None and b else None


def breadth(rows):
    """Breadth over index members. Each row: ticker, sector, price, chg, cap and, where the
    feed supplied them, dma50, dma200, hi52, lo52.

    Returns counts with their denominators, because a percentage over 300 names is not the
    same claim as one over 500.
    """
    priced = [r for r in rows if r.get('price') is not None and r.get('chg') is not None]
    adv = sum(1 for r in priced if r['chg'] > 0)
    dec = sum(1 for r in priced if r['chg'] < 0)
    unch = len(priced) - adv - dec

    def share(field):
        have = [r for r in priced if r.get(field)]
        above = sum(1 for r in have if r['price'] > r[field])
        return {'above': above, 'of': len(have),
                'pct': round(above / len(have) * 100, 1) if have else None}

    hl = [r for r in priced if r.get('hi52') and r.get('lo52')]
    near_hi = sum(1 for r in hl if r['price'] >= r['hi52'] * 0.98)
    near_lo = sum(1 for r in hl if r['price'] <= r['lo52'] * 1.02)

    capped = [r for r in priced if r.get('cap')]
    cap_total = sum(r['cap'] for r in capped)
    cap_w = round(sum(r['chg'] * r['cap'] for r in capped) / cap_total, 2) if cap_total else None
    eq_w = round(sum(r['chg'] for r in priced) / len(priced), 2) if priced else None

    by_chg = sorted(priced, key=lambda r: r['chg'])
    pick = lambda r: {k: r.get(k) for k in ('ticker', 'name', 'sector', 'price', 'chg', 'cap')}
    return {
        'members': len(rows), 'priced': len(priced),
        'advancers': adv, 'decliners': dec, 'unchanged': unch,
        'ad_ratio': round(adv / dec, 2) if dec else None,
        'above_50d': share('dma50'), 'above_200d': share('dma200'),
        'near_52w_high': {'count': near_hi, 'of': len(hl)},
        'near_52w_low': {'count': near_lo, 'of': len(hl)},
        'cap_weighted_chg': cap_w, 'equal_weighted_chg': eq_w,
        'leaders': [pick(r) for r in reversed(by_chg[-8:])],
        'laggards': [pick(r) for r in by_chg[:8]],
        'definitions': {
            'near_52w_high': 'within 2% of the 52-week high',
            'near_52w_low': 'within 2% of the 52-week low',
            'above_50d': 'last price above the 50-day average',
            'above_200d': 'last price above the 200-day average',
        },
    }


def returns(points, today=None):
    """Period returns from daily (date, close) points, oldest first.

    1D/1W/1M/3M count trading sessions back (1, 5, 21, 63); YTD runs from the last close of
    the previous calendar year. A period the history does not cover is None.
    """
    pts = [(d, c) for d, c in points if c is not None]
    if len(pts) < 2:
        return {k: None for k in ('1D', '1W', '1M', '3M', 'YTD')}
    last = pts[-1][1]
    out = {}
    for label, n in (('1D', 1), ('1W', 5), ('1M', 21), ('3M', 63)):
        out[label] = _pct(last, pts[-1 - n][1]) if len(pts) > n else None
    year = (today or pts[-1][0]).year
    prior = [c for d, c in pts if d.year < year]
    out['YTD'] = _pct(last, prior[-1]) if prior else None
    return out


def sector_table(series):
    """series: {symbol: [(date, close), ...]} for the sector funds and the benchmark.
    Each sector gets its returns and, per period, the difference to the benchmark in
    percentage points (positive = led the market)."""
    bench = returns(series.get(BENCHMARK, []))
    rows = []
    for name, sym in SECTOR_ETFS:
        pts = series.get(sym) or []
        r = returns(pts)
        rel = {k: (round(r[k] - bench[k], 2) if r[k] is not None and bench[k] is not None else None) for k in r}
        rows.append({'sector': name, 'etf': sym, 'returns': r, 'vs_benchmark': rel,
                     'as_of': pts[-1][0].isoformat() if pts else None})
    return {'benchmark': {'etf': BENCHMARK, 'returns': bench}, 'sectors': rows}


def snapshot(quotes):
    """quotes: {symbol: batch-quote dict}. Every instrument in SNAPSHOT is listed; one the
    feed did not return is marked unavailable rather than dropped."""
    out = []
    for group, sym, label, kind in SNAPSHOT:
        q = quotes.get(sym) or {}
        price, prev = q.get('price'), q.get('prev_close')
        row = {'group': group, 'symbol': sym, 'label': label, 'kind': kind, 'price': price,
               'status': 'delayed' if price is not None else 'unavailable',
               'market_time': (datetime.fromtimestamp(q['market_time'], timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
                               if q.get('market_time') else None)}
        if kind == 'yield':
            row['chg_bp'] = round((price - prev) * 100, 1) if price is not None and prev else None
        else:
            row['chg'] = q.get('chg')
        out.append(row)
    return out


def to_points(df):
    """A daily OHLC frame indexed by time -> [(date, close)], oldest first."""
    return [(ts.date() if hasattr(ts, 'date') else date.fromisoformat(str(ts)[:10]), float(c))
            for ts, c in zip(df.index, df['Close'])]
