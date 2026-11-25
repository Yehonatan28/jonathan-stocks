"""Alert rules and their evaluation on current data.

Method (shown to the user as written here):
- Alerts are checked when the app asks (on opening the screen and every two minutes while it is
  open). There is no server running in the background, so an alert does not fire while the app is
  closed, and nothing is sent by email or message.
- Price and daily change use the latest delayed quote. RSI(14), moving averages and volume use
  daily bars, so they reflect the last completed session plus today's bar so far.
- A cross means the last close is on the new side of the average and the close before it was not.
- Relative volume is today's volume over the average of the previous 63 sessions; early in the
  session today's volume is partial.
- "Earnings within N days" uses the reporting dates in the earnings calendar.
- "Near the stop" compares the price with the stop of a position in your holdings.
"""

KINDS = {
    'above': ('Price rises above', 'price'),
    'below': ('Price falls below', 'price'),
    'chg_above': ('Day change above (%)', 'pct'),
    'chg_below': ('Day change below (%)', 'pct'),
    'rsi_above': ('RSI(14) above', 'level'),
    'rsi_below': ('RSI(14) below', 'level'),
    'cross_above_ma': ('Close crosses above its moving average of', 'period'),
    'cross_below_ma': ('Close crosses below its moving average of', 'period'),
    'relvol_above': ('Relative volume above (x)', 'ratio'),
    'earnings_within': ('Earnings within (days)', 'days'),
    'near_stop': ('Within this % of my stop', 'pct'),
}


class RuleError(ValueError):
    pass


def parse(condition, value):
    """'cross_above_ma:50' style conditions; returns (kind, param, threshold)."""
    kind, _, param = str(condition or '').partition(':')
    if kind not in KINDS:
        raise RuleError(f'unknown alert type "{kind}"')
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise RuleError('a number is needed') from None
    unit = KINDS[kind][1]
    if kind in ('cross_above_ma', 'cross_below_ma'):
        try:
            p = int(param or v)
        except ValueError:
            raise RuleError('the moving average needs a period') from None
        if not 5 <= p <= 250:
            raise RuleError('the moving average period must be between 5 and 250')
        return kind, p, float(p)
    if unit == 'price' and v <= 0:
        raise RuleError('the price must be above zero')
    if unit == 'level' and not 0 < v < 100:
        raise RuleError('the RSI level must be between 0 and 100')
    if unit in ('ratio', 'days') and v <= 0:
        raise RuleError('the value must be above zero')
    return kind, None, v


def evaluate(alert, d):
    """alert: {ticker, condition, price}; d: current data for the ticker:
    price, chg, rsi, closes (last two), ma {period: [prev, last]}, rel_vol, earnings_in_days, stop.
    Returns {met: bool|None, value, detail}; met is None when the data needed is missing."""
    kind, param, v = parse(alert['condition'], alert['price'])
    px = d.get('price')
    if kind in ('above', 'below'):
        if px is None:
            return {'met': None, 'value': None, 'detail': 'no price'}
        return {'met': px >= v if kind == 'above' else px <= v, 'value': px, 'detail': f'price {px:.2f}'}
    if kind in ('chg_above', 'chg_below'):
        c = d.get('chg')
        if c is None:
            return {'met': None, 'value': None, 'detail': 'no change'}
        return {'met': c >= v if kind == 'chg_above' else c <= v, 'value': c, 'detail': f'day {c:+.2f}%'}
    if kind in ('rsi_above', 'rsi_below'):
        r = d.get('rsi')
        if r is None:
            return {'met': None, 'value': None, 'detail': 'no RSI'}
        return {'met': r >= v if kind == 'rsi_above' else r <= v, 'value': round(r, 1), 'detail': f'RSI {r:.1f}'}
    if kind in ('cross_above_ma', 'cross_below_ma'):
        ma = (d.get('ma') or {}).get(param)
        cl = d.get('closes')
        if not ma or None in ma or not cl or len(cl) < 2:
            return {'met': None, 'value': None, 'detail': f'not enough history for MA{param}'}
        up = cl[-2] <= ma[0] and cl[-1] > ma[1]
        down = cl[-2] >= ma[0] and cl[-1] < ma[1]
        side = 'above' if cl[-1] > ma[1] else 'below'
        return {'met': up if kind == 'cross_above_ma' else down, 'value': round(ma[1], 2),
                'detail': f'close {cl[-1]:.2f} {side} MA{param} {ma[1]:.2f}'}
    if kind == 'relvol_above':
        rv = d.get('rel_vol')
        if rv is None:
            return {'met': None, 'value': None, 'detail': 'no volume'}
        return {'met': rv >= v, 'value': rv, 'detail': f'volume {rv:.2f}x average'}
    if kind == 'earnings_within':
        n = d.get('earnings_in_days')
        if n is None:
            return {'met': False, 'value': None, 'detail': 'no report in the calendar window'}
        when = 'reports today' if n == 0 else f'reports in {n} trading day{"s" if n != 1 else ""}'
        return {'met': 0 <= n <= v, 'value': n, 'detail': when}
    if kind == 'near_stop':
        stop = d.get('stop')
        if not stop or px is None:
            return {'met': None, 'value': None, 'detail': 'no position with a stop'}
        gap = round((px / stop - 1) * 100, 6)          # 103/100 is 3.0000000000000027 in floating point
        return {'met': gap <= v, 'value': round(gap, 2), 'detail': f'{gap:.2f}% above the stop {stop:.2f}'}
    return {'met': None, 'value': None, 'detail': ''}
