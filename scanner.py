"""Stock scanner rows: one flat record per index member, every derived field computed here
so the browser only filters and sorts. A field whose inputs are missing is None, and the UI
shows a dash; nothing is filled in or estimated.
"""

# (key, label, unit, description) — the order is the default column order.
FIELDS = [
    ('price', 'Price', '$', 'Last price'),
    ('chg', 'Change', '%', 'Change today'),
    ('cap', 'Market cap', '$B', 'Market capitalisation, billions of dollars'),
    ('pe', 'P/E', 'x', 'Price over trailing twelve-month earnings per share'),
    ('fpe', 'Fwd P/E', 'x', 'Price over the consensus estimate of next-year earnings (an estimate, not a result)'),
    ('pb', 'P/B', 'x', 'Price over book value per share'),
    ('div_yield', 'Yield', '%', 'Trailing twelve-month dividends over price'),
    ('vs50', 'vs 50d', '%', 'Distance of the price from its 50-day average'),
    ('vs200', 'vs 200d', '%', 'Distance of the price from its 200-day average'),
    ('off_high', 'From 52w high', '%', "Distance below the 52-week high (0 = at the high); the feed's range, or the year's highest close"),
    ('range_pos', '52w range', '%', 'Where the price sits in its 52-week range (0 = low, 100 = high)'),
    ('rel_vol', 'Rel. volume', 'x', "Today's volume over the 3-month daily average; early in the session it is a partial day"),
]


def _pct(a, b):
    return round((a / b - 1) * 100, 2) if a is not None and b else None


def row(member, q):
    """member: {ticker, name, sector, cap}; q: a batch quote (see market.batch_quotes)."""
    price = q.get('price')
    hi, lo = q.get('hi52'), q.get('lo52')
    vol, avg = q.get('volume'), q.get('avg_vol')
    pe = q.get('pe')
    return {
        'ticker': member['ticker'], 'name': q.get('name') or member.get('name'), 'sector': member.get('sector'),
        'price': price, 'chg': q.get('chg'),
        'cap': round(q.get('cap') or member.get('cap') or 0, 1) or None,
        # a negative trailing P/E means losses; it is not a cheap stock, so it is not reported as a P/E
        'pe': round(pe, 1) if pe is not None and pe > 0 else None,
        'fpe': round(q['fpe'], 1) if q.get('fpe') is not None and q['fpe'] > 0 else None,
        'pb': q.get('pb'),
        'div_yield': q.get('div_yield'),
        'vs50': _pct(price, q.get('dma50')),
        'vs200': _pct(price, q.get('dma200')),
        'off_high': _pct(price, hi),
        'range_pos': (round((price - lo) / (hi - lo) * 100, 1)
                      if price is not None and hi and lo and hi > lo else None),
        'rel_vol': round(vol / avg, 2) if vol and avg else None,
    }


def rows(members, quotes):
    out = []
    for m in members:
        q = quotes.get(m['ticker'])
        if q and q.get('price') is not None:
            out.append(row(m, q))
    return out


def coverage(rs):
    """How many rows have each field: shown next to every filter, so a screen over P/E is
    known to run over the names that have one."""
    return {k: sum(1 for r in rs if r.get(k) is not None) for k, *_ in FIELDS}
