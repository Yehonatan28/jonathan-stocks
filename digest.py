"""Today for your names: facts worth a look in your holdings and watchlist.

Method (shown to the user as written here):
- Covers the symbols in your holdings and watchlist (up to 40), using the same delayed quotes and
  daily bars as the rest of the site.
- A name is listed when: it moved 3% or more today; its volume is at least twice its 63-session
  average; it is within 2% of its 52-week high or low; a holding is within 3% of its stop or below
  it; a holding closed below its 200-day average; or it reports earnings within five trading days.
- Each line is a fact with its number. None of it is a recommendation to buy or sell.
"""

BIG_MOVE, RELVOL, NEAR_RANGE, NEAR_STOP, EARN_DAYS = 3.0, 2.0, 2.0, 3.0, 5
ORDER = {'stop': 0, 'earnings': 1, 'move': 2, 'volume': 3, 'range': 4, 'trend': 5}


def build(symbols, quotes, holdings, earnings):
    """symbols: [ticker]; quotes: {t: quote fields}; holdings: {t: {'stop': float|None}};
    earnings: {t: trading days until the report}. Returns items sorted by kind, then size."""
    items = []

    def add(kind, t, text, value, level='info'):
        items.append({'kind': kind, 'ticker': t, 'text': text, 'value': value, 'level': level,
                      'held': t in holdings})

    for t in symbols:
        q = quotes.get(t) or {}
        px, chg = q.get('price'), q.get('chg')
        if px is None:
            continue
        if chg is not None and abs(chg) >= BIG_MOVE:
            add('move', t, f"{'up' if chg > 0 else 'down'} {abs(chg):.2f}% today", chg, 'high' if abs(chg) >= 2 * BIG_MOVE else 'medium')
        if q.get('volume') and q.get('avg_vol'):
            rv = q['volume'] / q['avg_vol']
            if rv >= RELVOL:
                add('volume', t, f'volume {rv:.1f}x its 3-month average', round(rv, 2), 'medium')
        hi, lo = q.get('hi52'), q.get('lo52')
        if hi and px >= hi * (1 - NEAR_RANGE / 100):
            add('range', t, f'{(px / hi - 1) * 100:+.1f}% from its 52-week high {hi:.2f}', round((px / hi - 1) * 100, 2))
        elif lo and px <= lo * (1 + NEAR_RANGE / 100):
            add('range', t, f'{(px / lo - 1) * 100:+.1f}% from its 52-week low {lo:.2f}', round((px / lo - 1) * 100, 2), 'medium')
        h = holdings.get(t)
        if h is not None:
            stop = h.get('stop')
            if stop:
                gap = round((px / stop - 1) * 100, 6)
                if gap <= 0:
                    add('stop', t, f'at or below its stop {stop:.2f} (price {px:.2f})', gap, 'high')
                elif gap <= NEAR_STOP:
                    add('stop', t, f'{gap:.2f}% above its stop {stop:.2f}', gap, 'high')
            if q.get('dma200') and px < q['dma200']:
                add('trend', t, f'below its 200-day average {q["dma200"]:.2f} ({(px / q["dma200"] - 1) * 100:+.1f}%)',
                    round((px / q['dma200'] - 1) * 100, 2))
        n = earnings.get(t)
        if n is not None and 0 <= n <= EARN_DAYS:
            add('earnings', t, 'reports earnings today' if n == 0 else f'reports earnings in {n} trading day{"s" if n != 1 else ""}', n, 'medium')
    items.sort(key=lambda x: (ORDER[x['kind']], -abs(x['value'] or 0)))
    return items
