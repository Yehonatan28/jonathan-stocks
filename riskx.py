"""Portfolio risk review and position sizing.

Method (shown to the user as written here):
- Exposure of a position = quantity x last price; its weight = exposure / account equity. Account
  equity is the figure in the risk settings; when none is set, the sum of the positions' values
  is used instead, and the page says so.
- Open risk of a position = quantity x (last price - stop): what is lost from here if the stop
  is hit. A stop at or above the price has no open risk left (gains are locked). A position with
  no stop has no defined risk and is listed as unprotected.
- Stop distance is also measured in ATR(14) (Wilder's average true range of the last 14 daily
  bars). Under 1 ATR, ordinary daily noise can hit the stop; over 4 ATR, the stop allows a large
  loss before acting. Both are flagged, neither is a rule.
- Sectors are the index's GICS sectors; a symbol outside the index is "Other".
- Correlation is the Pearson correlation of the last 60 daily returns (at least 40 shared days);
  pairs at 0.80 or above are listed, since they tend to move together and add up as one bet.
- Limits are the user's own: largest position, largest sector, risk per trade and total open
  risk, all as a percentage of equity. Nothing here is a recommendation to buy or sell.
"""
import math

DEFAULT_LIMITS = {'max_position_pct': 20.0, 'max_sector_pct': 35.0, 'max_trade_risk_pct': 1.0,
                  'max_portfolio_risk_pct': 6.0}
CORR_DAYS, CORR_MIN, CORR_HIGH = 60, 40, 0.80


def limits_from(d):
    out = dict(DEFAULT_LIMITS)
    for k, (lo, hi) in {'max_position_pct': (1, 100), 'max_sector_pct': (5, 100),
                        'max_trade_risk_pct': (0.1, 10), 'max_portfolio_risk_pct': (0.5, 50)}.items():
        try:
            v = float((d or {}).get(k))
            if lo <= v <= hi:
                out[k] = v
        except (TypeError, ValueError):
            pass
    return out


def _corr(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va == 0 or vb == 0:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb)


def correlation(closes):
    """closes: {ticker: [(date, close)]} -> (tickers, matrix, high pairs)."""
    rets = {}
    for t, pts in closes.items():
        pts = sorted(pts)[-(CORR_DAYS + 1):]
        rets[t] = {pts[i][0]: pts[i][1] / pts[i - 1][1] - 1 for i in range(1, len(pts)) if pts[i - 1][1]}
    tickers = sorted(t for t in rets if len(rets[t]) >= CORR_MIN)
    m, pairs = {}, []
    for i, a in enumerate(tickers):
        for b in tickers[i:]:
            if a == b:
                m[(a, b)] = 1.0
                continue
            shared = sorted(set(rets[a]) & set(rets[b]))
            c = _corr([rets[a][d] for d in shared], [rets[b][d] for d in shared]) if len(shared) >= CORR_MIN else None
            c = round(c, 2) if c is not None else None
            m[(a, b)] = m[(b, a)] = c
            if c is not None and c >= CORR_HIGH:
                pairs.append({'a': a, 'b': b, 'corr': c, 'days': len(shared)})
    matrix = [[m.get((a, b)) for b in tickers] for a in tickers]
    return tickers, matrix, sorted(pairs, key=lambda p: -p['corr'])


def review(positions, prices, atrs, sectors, equity, limits, closes=None):
    """positions: [{ticker, qty, entry, stop}]; prices/atrs: {ticker: float}; sectors: {ticker: name}."""
    lim = limits_from(limits)
    rows = []
    for p in positions:
        t = p['ticker']
        px = prices.get(t)
        qty = float(p['qty'])
        stop = p.get('stop')
        value = qty * px if px is not None else None
        risk = None
        if px is not None and stop:
            risk = max(0.0, qty * (px - float(stop)))
        atr = atrs.get(t)
        dist_atr = round((px - float(stop)) / atr, 2) if px is not None and stop and atr else None
        rows.append({'ticker': t, 'sector': sectors.get(t) or 'Other', 'qty': qty, 'entry': p.get('entry'),
                     'price': px, 'stop': stop, 'value': round(value, 2) if value is not None else None,
                     'open_risk': round(risk, 2) if risk is not None else None, 'atr': atr, 'stop_atr': dist_atr})
    total_value = sum(r['value'] for r in rows if r['value'] is not None)
    eq = float(equity) if equity and float(equity) > 0 else total_value
    basis = 'settings' if equity and float(equity) > 0 else 'positions'
    warnings = []

    def warn(level, kind, msg, ticker=None):
        warnings.append({'level': level, 'kind': kind, 'message': msg, 'ticker': ticker})

    for r in rows:
        r['weight'] = round(r['value'] / eq * 100, 2) if r['value'] is not None and eq else None
        r['risk_pct'] = round(r['open_risk'] / eq * 100, 2) if r['open_risk'] is not None and eq else None
        if r['price'] is None:
            warn('info', 'unpriced', f"{r['ticker']}: no current price, so it is left out of the totals", r['ticker'])
            continue
        if not r['stop']:
            warn('high', 'unprotected', f"{r['ticker']} has no stop: its possible loss is not defined", r['ticker'])
        if r['weight'] is not None and r['weight'] > lim['max_position_pct']:
            warn('high', 'position', f"{r['ticker']} is {r['weight']:.1f}% of equity, above your {lim['max_position_pct']:g}% limit", r['ticker'])
        if r['risk_pct'] is not None and r['risk_pct'] > lim['max_trade_risk_pct']:
            warn('medium', 'trade_risk', f"{r['ticker']} risks {r['risk_pct']:.2f}% of equity to its stop, above your {lim['max_trade_risk_pct']:g}% per trade", r['ticker'])
        if r['stop_atr'] is not None and 0 < r['stop_atr'] < 1:
            warn('medium', 'tight_stop', f"{r['ticker']}'s stop is {r['stop_atr']:.2f} ATR away: a normal day's range can reach it", r['ticker'])
        if r['stop_atr'] is not None and r['stop_atr'] > 4:
            warn('info', 'wide_stop', f"{r['ticker']}'s stop is {r['stop_atr']:.1f} ATR away: a large move before it acts", r['ticker'])

    sectors_out = {}
    for r in rows:
        if r['value'] is None:
            continue
        s = sectors_out.setdefault(r['sector'], {'sector': r['sector'], 'value': 0.0, 'tickers': []})
        s['value'] += r['value']
        s['tickers'].append(r['ticker'])
    sector_list = []
    for s in sectors_out.values():
        s['weight'] = round(s['value'] / eq * 100, 2) if eq else None
        s['value'] = round(s['value'], 2)
        sector_list.append(s)
        if s['weight'] is not None and s['weight'] > lim['max_sector_pct'] and s['sector'] != 'Other':
            warn('medium', 'sector', f"{s['sector']} is {s['weight']:.1f}% of equity, above your {lim['max_sector_pct']:g}% sector limit")
    sector_list.sort(key=lambda s: -s['value'])

    total_risk = sum(r['open_risk'] for r in rows if r['open_risk'] is not None)
    total_risk_pct = round(total_risk / eq * 100, 2) if eq else None
    if total_risk_pct is not None and total_risk_pct > lim['max_portfolio_risk_pct']:
        warn('high', 'portfolio_risk', f"Open risk to all stops is {total_risk_pct:.2f}% of equity, above your {lim['max_portfolio_risk_pct']:g}% limit")

    corr = {'tickers': [], 'matrix': [], 'pairs': []}
    if closes:
        t_, m_, p_ = correlation(closes)
        corr = {'tickers': t_, 'matrix': m_, 'pairs': p_}
        for p in p_:
            warn('info', 'correlation', f"{p['a']} and {p['b']} moved together (correlation {p['corr']:.2f} over {p['days']} days)")

    order = {'high': 0, 'medium': 1, 'info': 2}
    warnings.sort(key=lambda w: order[w['level']])
    top = max((r['weight'] for r in rows if r['weight'] is not None), default=None)
    return {
        'equity': round(eq, 2), 'equity_basis': basis, 'limits': lim,
        'positions': sorted(rows, key=lambda r: -(r['value'] or 0)), 'sectors': sector_list,
        'totals': {'value': round(total_value, 2), 'invested_pct': round(total_value / eq * 100, 2) if eq else None,
                   'open_risk': round(total_risk, 2), 'open_risk_pct': total_risk_pct, 'largest_weight': top,
                   'unprotected': sum(1 for r in rows if not r['stop'] and r['price'] is not None)},
        'correlation': corr, 'warnings': warnings,
        'method': __doc__.split('Method (shown to the user as written here):')[1].strip(),
    }


def size(equity, risk_pct, entry, stop, max_position_pct=None, side='long'):
    """Shares such that hitting the stop loses risk_pct of equity, capped by the position limit."""
    equity, risk_pct, entry, stop = float(equity), float(risk_pct), float(entry), float(stop)
    if equity <= 0 or risk_pct <= 0 or entry <= 0 or stop <= 0:
        raise ValueError('equity, risk, entry and stop must all be above zero')
    if side == 'long' and stop >= entry:
        raise ValueError('for a long position the stop must be below the entry')
    if side == 'short' and stop <= entry:
        raise ValueError('for a short position the stop must be above the entry')
    per_share = abs(entry - stop)
    budget = equity * risk_pct / 100
    qty = math.floor(budget / per_share)
    capped = False
    if max_position_pct:
        cap = math.floor(equity * float(max_position_pct) / 100 / entry)
        if qty > cap:
            qty, capped = cap, True
    return {'side': side, 'qty': qty, 'risk_budget': round(budget, 2), 'risk_per_share': round(per_share, 4),
            'risk': round(qty * per_share, 2), 'risk_pct': round(qty * per_share / equity * 100, 3),
            'position_value': round(qty * entry, 2), 'position_pct': round(qty * entry / equity * 100, 2),
            'capped_by_position_limit': capped,
            'stop_pct': round(per_share / entry * 100, 2)}
