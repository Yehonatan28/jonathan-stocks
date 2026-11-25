"""Strategy Lab: test a user-defined long-only rule set on daily bars.

Method (shown to the user as written here):
- Signals are evaluated on the close of a bar using only that bar and earlier ones; the trade
  is filled at the next bar's open. Nothing from a later bar is used for an earlier decision.
- Entry: every chosen entry condition must hold on the same close. Exit: any chosen exit
  condition, checked on the close, exits at the next open.
- Protective stop (k x ATR below the fill), target (m x ATR above it) and trailing stop (k x ATR
  below the highest close since entry) are checked inside each bar from its high and low. A bar
  that opens beyond a level fills at the open (a gap); if a bar touches both the stop and the
  target, the stop is assumed to come first, which is the conservative reading.
- Costs: commission and slippage, each in basis points of the traded value, on both the
  entry and the exit. The whole account is invested in each trade; no leverage, no shorting.
- Indicators: RSI(14) and ATR(14) use Wilder's smoothing, moving averages are simple, MACD is
  12/26/9 on exponential averages, all from the platform's indicator library.
- Results are compared with buying and holding the same symbol over the same window.
- A backtest describes the past under these assumptions; it does not predict results.
"""
import math

from quant import indicators as qi

ENTRY = {
    'rsi_below': ('RSI(14) below', 'value'),
    'rsi_above': ('RSI(14) above', 'value'),
    'close_above_ma': ('Close above its moving average of', 'period'),
    'close_below_ma': ('Close below its moving average of', 'period'),
    'ma_cross_up': ('50-day average crosses above the 200-day', None),
    'macd_cross_up': ('MACD crosses above its signal line', None),
    'breakout': ('Close above the highest high of the previous', 'period'),
}
EXIT = {
    'rsi_above': ('RSI(14) above', 'value'),
    'close_below_ma': ('Close below its moving average of', 'period'),
    'ma_cross_down': ('50-day average crosses below the 200-day', None),
    'macd_cross_down': ('MACD crosses below its signal line', None),
    'bars_held': ('Held for (bars)', 'period'),
}


class StrategyError(ValueError):
    pass


def _conds(raw, table, kind):
    out = []
    for c in (raw or [])[:6]:
        k = (c or {}).get('type')
        if k not in table:
            raise StrategyError(f'unknown {kind} condition "{k}"')
        need = table[k][1]
        v = c.get(need) if need else None
        if need:
            try:
                v = float(v)
            except (TypeError, ValueError):
                raise StrategyError(f'{table[k][0]}: a number is needed') from None
            if need == 'period' and not 2 <= v <= 400:
                raise StrategyError(f'{table[k][0]}: the period must be between 2 and 400')
            if need == 'value' and not 0 < v < 100:
                raise StrategyError(f'{table[k][0]}: the RSI level must be between 0 and 100')
        out.append({'type': k, need: v} if need else {'type': k})
    return out


def clean(strategy):
    s = strategy or {}
    entry = _conds(s.get('entry'), ENTRY, 'entry')
    if not entry:
        raise StrategyError('choose at least one entry condition')
    exits = _conds(s.get('exit'), EXIT, 'exit')

    def opt(name, lo, hi):
        v = s.get(name)
        if v in (None, '', 0, '0'):
            return None
        try:
            v = float(v)
        except (TypeError, ValueError):
            raise StrategyError(f'{name} must be a number') from None
        if not lo <= v <= hi:
            raise StrategyError(f'{name} must be between {lo} and {hi}')
        return v
    out = {'entry': entry, 'exit': exits, 'stop_atr': opt('stop_atr', 0.2, 20), 'target_atr': opt('target_atr', 0.2, 50),
           'trail_atr': opt('trail_atr', 0.2, 20), 'commission_bps': opt('commission_bps', 0, 200) or 0.0,
           'slippage_bps': opt('slippage_bps', 0, 200) or 0.0}
    if not exits and not (out['stop_atr'] or out['target_atr'] or out['trail_atr']):
        raise StrategyError('choose an exit condition or a stop, target or trailing stop')
    return out


def _series(df, s):
    c = df['Close']
    need = {'rsi': qi.rsi(c, 14), 'atr': qi.atr(df, 14)}
    periods = {x.get('period') for x in s['entry'] + s['exit'] if x['type'] in ('close_above_ma', 'close_below_ma')}
    for p in periods:
        need[f'ma{int(p)}'] = qi.sma(c, int(p))
    if any(x['type'] in ('ma_cross_up', 'ma_cross_down') for x in s['entry'] + s['exit']):
        need['ma50'], need['ma200'] = qi.sma(c, 50), qi.sma(c, 200)
    if any(x['type'] in ('macd_cross_up', 'macd_cross_down') for x in s['entry'] + s['exit']):
        m = qi.macd(c)
        need['macd'], need['macd_sig'] = m[0], m[1]
    for x in s['entry']:
        if x['type'] == 'breakout':
            need[f'hh{int(x["period"])}'] = df['High'].rolling(int(x['period'])).max().shift(1)
    return {k: [None if (v != v) else float(v) for v in ser.tolist()] for k, ser in need.items()}


def _cross(a, b, i, up):
    if i < 1 or None in (a[i], b[i], a[i - 1], b[i - 1]):
        return False
    return (a[i - 1] <= b[i - 1] and a[i] > b[i]) if up else (a[i - 1] >= b[i - 1] and a[i] < b[i])


def _holds(c, ind, close, high, i, held=0):
    t = c['type']
    if t == 'rsi_below':
        return ind['rsi'][i] is not None and ind['rsi'][i] < c['value']
    if t == 'rsi_above':
        return ind['rsi'][i] is not None and ind['rsi'][i] > c['value']
    if t in ('close_above_ma', 'close_below_ma'):
        m = ind[f'ma{int(c["period"])}'][i]
        return m is not None and (close[i] > m if t == 'close_above_ma' else close[i] < m)
    if t == 'ma_cross_up':
        return _cross(ind['ma50'], ind['ma200'], i, True)
    if t == 'ma_cross_down':
        return _cross(ind['ma50'], ind['ma200'], i, False)
    if t == 'macd_cross_up':
        return _cross(ind['macd'], ind['macd_sig'], i, True)
    if t == 'macd_cross_down':
        return _cross(ind['macd'], ind['macd_sig'], i, False)
    if t == 'breakout':
        h = ind[f'hh{int(c["period"])}'][i]
        return h is not None and close[i] > h
    if t == 'bars_held':
        return held >= c['period']
    return False


def run(df, strategy, start_index=None):
    """df: daily OHLC frame (oldest first, DatetimeIndex). Returns trades, curves and statistics."""
    s = clean(strategy)
    n = len(df)
    if n < 60:
        raise StrategyError('not enough history (at least 60 daily bars)')
    ind = _series(df, s)
    o, h, l, c = (df[k].astype(float).tolist() for k in ('Open', 'High', 'Low', 'Close'))
    dates = [d.strftime('%Y-%m-%d') for d in df.index]
    cost = (s['commission_bps'] + s['slippage_bps']) / 10000
    first = start_index if start_index is not None else 0
    cash, shares, pos = 1.0, 0.0, None
    pending = None                     # 'enter' or 'exit', decided on the previous close
    trades, equity = [], []

    def close_pos(i, px, why):
        nonlocal cash, shares, pos
        fill = px * (1 - cost)
        cash = shares * fill
        trades.append({**pos, 'exit_date': dates[i], 'exit': round(px, 4), 'reason': why, 'bars': i - pos['bar'],
                       'return_pct': round((cash / pos['cash_in'] - 1) * 100, 2)})
        shares, pos = 0.0, None

    for i in range(first, n):
        # 1) orders decided on the previous close fill at this open
        if pending == 'enter' and pos is None:
            atr = ind['atr'][i - 1]
            fill = o[i] * (1 + cost)
            shares, cash_in, cash = cash / fill, cash, 0.0
            pos = {'entry_date': dates[i], 'entry': round(o[i], 4), 'bar': i, 'cash_in': cash_in, 'high_close': o[i],
                   'stop': o[i] - s['stop_atr'] * atr if s['stop_atr'] and atr else None,
                   'target': o[i] + s['target_atr'] * atr if s['target_atr'] and atr else None, 'atr': atr}
        elif pending == 'exit' and pos is not None:
            close_pos(i, o[i], 'exit rule')
        pending = None
        # 2) protective levels inside this bar
        if pos is not None:
            trail = (pos['high_close'] - s['trail_atr'] * pos['atr']) if s['trail_atr'] and pos['atr'] else None
            stop = max(x for x in (pos['stop'], trail) if x is not None) if (pos['stop'] or trail) else None
            if stop is not None and l[i] <= stop:
                close_pos(i, min(o[i], stop), 'trailing stop' if trail is not None and stop == trail and stop != pos['stop'] else 'stop')
            elif pos['target'] is not None and h[i] >= pos['target']:
                close_pos(i, max(o[i], pos['target']), 'target')
        # 3) mark to market and decide on this close
        if pos is not None:
            pos['high_close'] = max(pos['high_close'], c[i])
            equity.append(shares * c[i])
            if s['exit'] and i < n - 1 and any(_holds(x, ind, c, h, i, i - pos['bar']) for x in s['exit']):
                pending = 'exit'
        else:
            equity.append(cash)
            if i < n - 1 and all(_holds(x, ind, c, h, i) for x in s['entry']):
                pending = 'enter'
    open_trade = None
    if pos is not None:
        open_trade = {**{k: v for k, v in pos.items() if k in ('entry_date', 'entry')},
                      'unrealised_pct': round((shares * c[-1] / pos['cash_in'] - 1) * 100, 2)}
    for t in trades:
        for k in ('cash_in', 'high_close', 'stop', 'target', 'atr', 'bar'):
            t.pop(k, None)
    return _report(dates[first:], equity, c[first:], trades, open_trade, s)


def _dd(curve):
    peak, worst = curve[0], 0.0
    dd = []
    for v in curve:
        peak = max(peak, v)
        d = v / peak - 1
        dd.append(round(d * 100, 2))
        worst = min(worst, d)
    return round(worst * 100, 2), dd


def _report(dates, equity, closes, trades, open_trade, s):
    bh = [x / closes[0] for x in closes]
    total = (equity[-1] - 1) * 100
    days = len(equity)
    rets = [equity[i] / equity[i - 1] - 1 for i in range(1, days) if equity[i - 1]]
    sd = (sum((r - sum(rets) / len(rets)) ** 2 for r in rets) / (len(rets) - 1)) ** 0.5 if len(rets) > 1 else 0
    mdd, dd = _dd(equity)
    bh_mdd, _ = _dd(bh)
    wins = [t['return_pct'] for t in trades if t['return_pct'] > 0]
    losses = [t['return_pct'] for t in trades if t['return_pct'] <= 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    in_market = sum(1 for i in range(days) if i and equity[i] != equity[i - 1]) if trades or open_trade else 0
    monthly, last_val, month = {}, 1.0, None
    for d, v in zip(dates, equity):
        m = d[:7]
        if month and m != month:
            monthly[month] = round((prev / last_val - 1) * 100, 2)
            last_val = prev
        month, prev = m, v
    if month:
        monthly[month] = round((prev / last_val - 1) * 100, 2)
    years = days / 252
    return {
        'ok': True, 'strategy': s, 'start': dates[0], 'end': dates[-1], 'bars': days,
        'stats': {
            'total_return': round(total, 2), 'buy_hold_return': round((bh[-1] - 1) * 100, 2),
            'cagr': round((equity[-1] ** (1 / years) - 1) * 100, 2) if years >= 1 and equity[-1] > 0 else None,
            'max_drawdown': mdd, 'buy_hold_max_drawdown': bh_mdd,
            'sharpe': round(sum(rets) / len(rets) / sd * math.sqrt(252), 2) if sd and len(rets) >= 60 else None,
            'trades': len(trades), 'win_rate': round(len(wins) / len(trades) * 100, 1) if trades else None,
            'avg_win': round(gross_win / len(wins), 2) if wins else None,
            'avg_loss': round(-gross_loss / len(losses), 2) if losses else None,
            'profit_factor': round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
            'exposure_pct': round(in_market / days * 100, 1) if days else None,
            'avg_bars': round(sum(t['bars'] for t in trades) / len(trades), 1) if trades else None,
        },
        'curve': [{'date': d, 'strategy': round(e * 100, 3), 'buy_hold': round(b * 100, 3), 'drawdown': x}
                  for d, e, b, x in zip(dates, equity, bh, dd)],
        'monthly': monthly, 'trades': trades[-200:], 'open_trade': open_trade,
        'method': __doc__.split('Method (shown to the user as written here):')[1].strip(),
        'catalogue': {'entry': {k: v[0] for k, v in ENTRY.items()}, 'exit': {k: v[0] for k, v in EXIT.items()}},
    }
