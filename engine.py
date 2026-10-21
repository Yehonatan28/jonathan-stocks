"""Technical analysis and risk-management engine.

The module is deliberately stateless: every function takes prices (or a
position dict) and returns plain JSON-ready structures, so the same code
serves logged-in users and guest (localStorage) users alike.

Sections:
  1. data      - daily OHLCV fetch + cache
  2. indicators- Wilder-smoothed RSI / ATR / ADX, MACD, MAs, channels
  3. analyze   - one ticker -> trend regime, levels, entry setups
  4. manage    - one held position -> stop/trailing actions
  5. plan      - whole portfolio -> prioritized action feed + risk summary
"""

import math
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pandas as pd
import requests

HEADERS = {'User-Agent': 'Mozilla/5.0'}

# ---------------------------------------------------------------- 1. data ---

_DF_CACHE = {}
DF_TTL = 600


def fetch_daily(ticker, range_='2y'):
    """Daily OHLCV as a DataFrame. Returns None when Yahoo has no data."""
    key = f'{ticker}:{range_}'
    hit = _DF_CACHE.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    try:
        r = requests.get(
            f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}',
            headers=HEADERS,
            params={'interval': '1d', 'range': range_},
            timeout=12)
        r.raise_for_status()
        result = r.json()['chart']['result'][0]
        q = result['indicators']['quote'][0]
        df = pd.DataFrame({
            'Open': q['open'], 'High': q['high'], 'Low': q['low'],
            'Close': q['close'], 'Volume': q['volume'],
            'Time': [datetime.fromtimestamp(t, tz=timezone.utc)
                     for t in result['timestamp']],
        }).dropna(subset=['Close', 'High', 'Low']).set_index('Time')
    except Exception:
        return None
    if df.empty:
        return None
    _DF_CACHE[key] = (time.time() + DF_TTL, df)
    return df


# ---------------------------------------------------------- 2. indicators ---

def _wilder(series, n):
    """Wilder's smoothing - the averaging RSI/ATR/ADX are defined with."""
    return series.ewm(alpha=1.0 / n, adjust=False).mean()


def rsi(close, n=14):
    delta = close.diff()
    gain = _wilder(delta.clip(lower=0), n)
    loss = _wilder((-delta).clip(lower=0), n)
    return 100 - 100 / (1 + gain / loss.replace(0, 1e-10))


def true_range(df):
    prev_close = df['Close'].shift()
    return pd.concat([
        df['High'] - df['Low'],
        (df['High'] - prev_close).abs(),
        (df['Low'] - prev_close).abs(),
    ], axis=1).max(axis=1)


def atr(df, n=14):
    return _wilder(true_range(df), n)


def adx(df, n=14):
    up = df['High'].diff()
    down = -df['Low'].diff()
    plus_dm = ((up > down) & (up > 0)) * up.clip(lower=0)
    minus_dm = ((down > up) & (down > 0)) * down.clip(lower=0)
    tr_n = _wilder(true_range(df), n).replace(0, 1e-10)
    plus_di = 100 * _wilder(plus_dm, n) / tr_n
    minus_di = 100 * _wilder(minus_dm, n) / tr_n
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-10)
    return _wilder(dx, n), plus_di, minus_di


def macd(close, fast=12, slow=26, sig=9):
    line = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    signal = line.ewm(span=sig, adjust=False).mean()
    return line, signal, line - signal


def _f(value, digits=2):
    """float() that survives NaN/None - returns None instead of a bad number."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return round(v, digits)


def _slope_pct(series, bars, i=-1):
    """Percent change of a moving average over `bars` - its direction."""
    idx = len(series) + i if i < 0 else i
    if idx - bars < 0:
        return None
    now, then = series.iloc[idx], series.iloc[idx - bars]
    if not then or math.isnan(now) or math.isnan(then):
        return None
    return round((now - then) / abs(then) * 100, 2)


def _bars_since_flip(flags, i, limit=30):
    """How many bars ago a boolean series last changed value, at bar i."""
    start = max(0, i - limit + 1)
    window = flags.iloc[start:i + 1].tolist()
    for back in range(len(window) - 1):
        if window[-1 - back] != window[-2 - back]:
            return back
    return None


# ------------------------------------------------------------- 3. analyze ---

# Regime codes and their Hebrew labels, used across the UI.
REGIMES = {
    'strong_up': 'Strong uptrend',
    'up': 'Uptrend',
    'recovering': 'Recovering',
    'range': 'Range-bound',
    'weak': 'Weakening',
    'down': 'Downtrend',
}


def _indicators(df):
    """Every indicator series at once.

    Each value at bar i depends only on bars <= i, which is what lets the
    backtest walk this frame forward without leaking future prices.
    """
    close, high, low, vol = df['Close'], df['High'], df['Low'], df['Volume']
    macd_line, macd_sig, macd_hist = macd(close)
    adx_s, plus_di, minus_di = adx(df)
    n = len(close)
    return {
        'close': close, 'high': high, 'low': low, 'volume': vol,
        'open': df['Open'],
        # 50/100/150/200 is the trend-template family; the 20 stays only
        # because Bollinger bands and the short-term pullback check use it.
        'sma20': close.rolling(20).mean(),
        'sma50': close.rolling(50).mean(),
        'sma100': close.rolling(100 if n >= 100 else n).mean(),
        'sma150': close.rolling(150 if n >= 150 else n).mean(),
        'sma200': close.rolling(200 if n >= 200 else n).mean(),
        'ema21': close.ewm(span=21, adjust=False).mean(),
        'rsi': rsi(close),
        'atr': atr(df),
        'adx': adx_s, 'plus_di': plus_di, 'minus_di': minus_di,
        'macd': macd_line, 'macd_sig': macd_sig, 'macd_hist': macd_hist,
        # shifted: the channel the current bar is measured against excludes it
        'donch20_high': high.rolling(20).max().shift(1),
        'donch20_low': low.rolling(20).min().shift(1),
        'donch55_high': high.rolling(55, min_periods=20).max().shift(1),
        'swing_low': low.rolling(10).min(),
        'swing_high': high.rolling(10).max(),
        'hh22': high.rolling(22).max(),
        'vol_avg': vol.rolling(20).mean(),
        'wk52_high': high.rolling(252, min_periods=20).max(),
        'wk52_low': low.rolling(252, min_periods=20).min(),
    }


def _snapshot(ticker, ind, i):
    """The technical picture as it stood at the close of bar i.

    analyze() is this at the last bar; the backtest is this at every bar.
    Sharing one builder is what makes the backtest a test of the live rules
    rather than of a second implementation that drifts from them.
    """
    def at(key, default=None):
        v = ind[key].iloc[i]
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return default
        return float(v)

    price = at('close')
    if price is None:
        return None
    prev = float(ind['close'].iloc[i - 1]) if i > 0 else price

    v_sma20 = at('sma20', price)
    v_sma50 = at('sma50', price)
    v_sma100 = at('sma100', price)
    v_sma150 = at('sma150', price)
    v_sma200 = at('sma200', price)
    v_rsi = at('rsi', 50.0)
    v_adx = at('adx', 0.0)
    atr_v = at('atr', 0.0) or 0.0
    vol_avg = at('vol_avg') or 1.0
    vol_ratio = (at('volume', 0.0) or 0.0) / vol_avg if vol_avg else 1.0

    slope200 = _slope_pct(ind['sma200'], 20, i)
    slope50 = _slope_pct(ind['sma50'], 10, i)

    above200, above50, above20 = price > v_sma200, price > v_sma50, price > v_sma20
    golden = v_sma50 > v_sma200
    macd_up = at('macd', 0.0) > at('macd_sig', 0.0)

    # A pullback is not a broken trend: as long as the 50/200 structure holds
    # and price is above the 200, a dip of up to 4% under the 50 still counts
    # as an uptrend - that dip is exactly where the best entries live.
    pullback_ok = price >= v_sma50 * 0.96
    stacked = v_sma50 > v_sma150 > v_sma200      # the classic trend template
    if above50 and stacked and (slope200 or 0) > 0 and v_adx >= 20:
        regime = 'strong_up'
    elif golden and above200 and pullback_ok:
        regime = 'up'
    elif above200 and not golden:
        regime = 'recovering'
    elif not above50 and not above200 and v_sma50 < v_sma200:
        regime = 'down'
    elif v_adx < 18 and abs(price - v_sma50) / price < 0.04:
        regime = 'range'
    else:
        regime = 'weak'

    score = 0
    score += 20 if above200 else 0
    score += 15 if above50 else 0
    score += 10 if above20 else 0
    score += 10 if golden else 0
    score += 5 if v_sma50 > v_sma150 > v_sma200 else 0
    score += 10 if (slope200 or 0) > 0 else 0
    score += 10 if macd_up else 0
    score += 10 if (v_adx >= 20 and at('plus_di', 0.0) > at('minus_di', 0.0)) else 0
    score += 10 if 45 <= v_rsi <= 70 else (5 if 35 <= v_rsi < 45 else 0)

    golden_cross_bars = None
    if golden and len(ind['sma200'].dropna()) > 30:
        golden_cross_bars = _bars_since_flip(ind['sma50'] > ind['sma200'], i)
    macd_cross_bars = _bars_since_flip(ind['macd'] > ind['macd_sig'], i) if macd_up else None

    snap = {
        'ticker': ticker, 'ok': True,
        'price': _f(price), 'prev_close': _f(prev),
        'chg_pct': _f((price - prev) / prev * 100) if prev else None,
        'regime': regime, 'regime_he': REGIMES[regime],
        'trend_score': min(100, score),
        'ma': {'sma20': _f(v_sma20), 'sma50': _f(v_sma50),
               'sma100': _f(v_sma100), 'sma150': _f(v_sma150),
               'sma200': _f(v_sma200), 'ema21': _f(at('ema21', price)),
               'slope50': slope50, 'slope200': slope200,
               'dist20': _f((price / v_sma20 - 1) * 100) if v_sma20 else None,
               'dist50': _f((price / v_sma50 - 1) * 100) if v_sma50 else None,
               'dist100': _f((price / v_sma100 - 1) * 100) if v_sma100 else None,
               'dist150': _f((price / v_sma150 - 1) * 100) if v_sma150 else None,
               'dist200': _f((price / v_sma200 - 1) * 100) if v_sma200 else None},
        'stacked': bool(v_sma50 > v_sma150 > v_sma200),
        'rsi': _f(v_rsi, 1), 'adx': _f(v_adx, 1),
        'macd_up': macd_up, 'macd_hist': _f(at('macd_hist', 0.0), 3),
        'atr': _f(atr_v), 'atr_pct': _f(atr_v / price * 100) if price else None,
        'vol_ratio': _f(vol_ratio),
        'levels': {
            'support': _f(at('donch20_low', price)),
            'resistance': _f(at('donch20_high', price)),
            'swing_low': _f(at('swing_low', price)),
            'swing_high': _f(at('swing_high', price)),
            'high22': _f(at('hh22', price)),
            'breakout55': _f(at('donch55_high', price)),
            'wk52_high': _f(at('wk52_high', price)),
            'wk52_low': _f(at('wk52_low', price)),
            'from_high_pct': _f((price / at('wk52_high', price) - 1) * 100),
        },
        'golden_cross': golden,
        'golden_cross_bars': golden_cross_bars,
        'macd_cross_bars': macd_cross_bars,
    }
    snap['suggested_stop'] = suggest_initial_stop(snap)
    snap['trail_stop'] = suggest_trail_stop(snap)
    return snap


def analyze(ticker):
    """Full technical picture for one ticker, as of the latest close."""
    ticker = ticker.strip().upper()
    df = fetch_daily(ticker)
    if df is None or len(df) < 60:
        return {'ticker': ticker, 'ok': False,
                'error': 'Not enough price history to analyse this symbol'}
    ind = _indicators(df)
    out = _snapshot(ticker, ind, len(df) - 1)
    if out is None:
        return {'ticker': ticker, 'ok': False, 'error': 'Price data for this symbol is unusable'}
    out['entries'] = _entry_setups(out)
    out['history'] = [round(float(p), 2) for p in df['Close'].iloc[-120:].tolist()]
    return out


def suggest_initial_stop(an, mult=2.0):
    """Structure-first stop: recent swing low, capped by volatility."""
    price, atr_v = an['price'], an['atr']
    if not price or not atr_v:
        return None
    structural = an['levels']['swing_low'] - 0.25 * atr_v
    volatility = price - mult * atr_v
    stop = min(structural, volatility)
    # never risk more than 3.5 ATR on a single entry
    if price - stop > 3.5 * atr_v:
        stop = price - 2.5 * atr_v
    # never sit so close it is noise
    stop = min(stop, price - 0.8 * atr_v)
    return _f(stop)


def suggest_trail_stop(an, mult=None):
    """Chandelier exit - anchored to the highest high of the last 22 bars."""
    atr_v, hh = an['atr'], an['levels']['high22']
    if not atr_v or not hh:
        return None
    if mult is None:
        # a tighter leash on strong, orderly trends; more room on choppy ones
        mult = 2.5 if an['regime'] == 'strong_up' and (an['adx'] or 0) >= 25 else 3.0
    chandelier = hh - mult * atr_v
    # a structural floor: don't trail above the 20-day average in a fast move
    return _f(min(chandelier, an['price'] - 0.8 * atr_v))


def _entry_setups(an):
    """Technical entry setups that are currently valid for this ticker."""
    setups = []
    price, atr_v, ma = an['price'], an['atr'], an['ma']
    rsi_v, lv = an['rsi'], an['levels']
    if not price or not atr_v:
        return setups

    stop = suggest_initial_stop(an)
    risk = price - stop if stop else atr_v * 2

    def add(code, title, why, quality, zone_low, zone_high, entry_stop=None):
        st = entry_stop if entry_stop is not None else stop
        rr = price - st
        setups.append({
            'code': code, 'title': title, 'why': why,
            'quality': max(20, min(97, quality)),
            'zone_low': _f(zone_low), 'zone_high': _f(zone_high),
            'stop': _f(st),
            'risk_per_share': _f(rr),
            'target1': _f(price + 2 * rr), 'target2': _f(price + 3 * rr),
        })

    up_trend = an['regime'] in ('strong_up', 'up')
    healthy = price > ma['sma200'] if ma['sma200'] else False

    # 1. pullback into a rising moving average - the bread-and-butter entry
    if up_trend and rsi_v is not None and 35 <= rsi_v <= 58:
        near20 = ma['dist20'] is not None and -4 <= ma['dist20'] <= 2.5
        near50 = ma['dist50'] is not None and -3 <= ma['dist50'] <= 3
        if near20 or near50:
            anchor = ma['sma20'] if near20 else ma['sma50']
            label = 'MA20' if near20 else 'MA50'
            add('PULLBACK_MA',
                f'Pullback to the {label}',
                [f'The trend is up ({an["regime_he"].lower()}) and price has come back '
                 f'to the {label} — an entry with clearly defined risk',
                 f'RSI {rsi_v} reads as a healthy pullback rather than weakness',
                 f'The 50-day average is {"above" if an["golden_cross"] else "below"} the 200-day'],
                62 + an['trend_score'] // 4 + (6 if near20 else 0),
                anchor * 0.995, max(price, anchor * 1.02))

    # 2. breakout of the 20-day range on volume
    if price >= lv['resistance'] and (an['vol_ratio'] or 0) >= 1.3 and healthy:
        add('BREAKOUT',
            '20-day breakout',
            [f'Price cleared ${lv["resistance"]} — the highest close of the last 20 days',
             f'Volume is {an["vol_ratio"]}x the average, so real money is behind the move',
             'The stop sits just under the breakout level'],
            60 + an['trend_score'] // 3,
            lv['resistance'], price + 0.5 * atr_v,
            min(lv['resistance'] - 0.3 * atr_v, price - 1.5 * atr_v))

    # 3. fresh golden cross - a regime change worth acting on
    if an['golden_cross_bars'] is not None and an['golden_cross_bars'] <= 15:
        add('GOLDEN_CROSS',
            'Fresh golden cross',
            [f'The 50-day average crossed above the 200-day {an["golden_cross_bars"]} sessions ago',
             'Historically this marks a change of long-term trend, not daily noise',
             'Better entered on the first pullback than chased'],
            58 + an['trend_score'] // 3, ma['sma50'], price + 0.5 * atr_v)

    # 4. momentum turning up while the long-term trend is intact
    if (an['macd_cross_bars'] is not None and an['macd_cross_bars'] <= 5
            and healthy and rsi_v is not None and rsi_v < 68):
        add('MACD_CROSS',
            'MACD momentum turn',
            [f'The MACD line crossed above its signal {an["macd_cross_bars"]} sessions ago',
             'Price is above the 200-day average, so momentum agrees with the main trend',
             'A relatively early signal — suits a partial position'],
            52 + an['trend_score'] // 4, price - 0.5 * atr_v, price + atr_v)

    # 5. deep oversold inside a long-term uptrend
    if healthy and rsi_v is not None and rsi_v <= 34:
        add('OVERSOLD_UPTREND',
            'Oversold inside an uptrend',
            [f'RSI {rsi_v} is oversold, yet price is still above the 200-day average',
             'Pullbacks like this inside a primary uptrend tend to be opportunities',
             'Wait for the first green close as confirmation before entering'],
            48 + an['trend_score'] // 4, price - atr_v, price + 0.5 * atr_v)

    # 6. reclaiming the 200-day average after being below it
    if (ma['dist200'] is not None and 0 <= ma['dist200'] <= 3
            and not an['golden_cross']):
        add('RECLAIM_200',
            'Reclaiming the 200-day',
            ['Price has closed back above the 200-day average — a first sign of recovery',
             'The 50-day is still below the 200-day, so this is early rather than confirmed',
             'Size this one smaller than usual'],
            44 + an['trend_score'] // 5, ma['sma200'], price + atr_v)

    setups.sort(key=lambda s: -s['quality'])
    return setups[:3]


# -------------------------------------------------------------- 4. manage ---

SEVERITY_ORDER = {'critical': 0, 'high': 1, 'medium': 2, 'info': 3}


def _action(code, severity, ticker, title, detail, **extra):
    a = {'code': code, 'severity': severity, 'ticker': ticker,
         'title': title, 'detail': detail}
    a.update(extra)
    return a


def manage_position(pos, an, settings):
    """Stop/exit actions for one held position. Returns (actions, metrics)."""
    ticker = pos['ticker']
    qty = float(pos.get('qty') or 0)
    entry = float(pos.get('entry') or 0)
    price = an['price']
    atr_v = an['atr'] or 0
    stop = pos.get('stop')
    stop = float(stop) if stop not in (None, '') else None
    init_stop = pos.get('init_stop')
    init_stop = float(init_stop) if init_stop not in (None, '') else stop
    stop_type = pos.get('stop_type') or 'fixed'

    suggested_initial = an['suggested_stop']
    # settings may pin the ATR multiple; None means "let the engine adapt it"
    trail = suggest_trail_stop(an, settings.get('trail_mult'))

    # R multiple: profit measured in units of the risk originally taken
    risk_per_share = (entry - init_stop) if init_stop and init_stop < entry else (atr_v * 2 or None)
    r_multiple = _f((price - entry) / risk_per_share, 2) if risk_per_share else None

    open_risk = _f(max(0.0, (price - stop) * qty)) if stop is not None else \
        _f(max(0.0, (price - (suggested_initial or price)) * qty))

    metrics = {
        'ticker': ticker, 'id': pos.get('id'), 'qty': qty, 'entry': _f(entry),
        'price': price, 'chg_pct': an['chg_pct'],
        'value': _f(price * qty), 'cost': _f(entry * qty),
        'pnl': _f((price - entry) * qty),
        'pnl_pct': _f((price / entry - 1) * 100) if entry else None,
        'stop': _f(stop) if stop is not None else None,
        'init_stop': _f(init_stop) if init_stop is not None else None,
        'stop_type': stop_type,
        'suggested_stop': suggested_initial,
        'trail_stop': trail,
        'stop_distance_pct': _f((price / stop - 1) * 100) if stop else None,
        'r_multiple': r_multiple,
        'open_risk': open_risk,
        'has_stop': stop is not None,
        'regime': an['regime'], 'regime_he': an['regime_he'],
        'trend_score': an['trend_score'], 'rsi': an['rsi'],
        'atr_pct': an['atr_pct'], 'ma': an['ma'],
        'history': an['history'],
    }

    actions = []

    # --- no protection at all: the single most important gap to close
    if stop is None:
        actions.append(_action(
            'SET_STOP', 'high', ticker,
            'No stop set on this position',
            f'The position is exposed to any decline. The suggested stop is '
            f'${suggested_initial} — below the recent swing low and 2x ATR from price, '
            f'which risks {_f((price / suggested_initial - 1) * 100)}% from here.',
            suggest=suggested_initial, stop_type='fixed'))
    else:
        # --- the stop has already been breached
        if price <= stop:
            actions.append(_action(
                'STOP_HIT', 'critical', ticker,
                'Stop breached — time to exit',
                f'Price ${price} is below the stop you set at ${_f(stop)}. '
                f'This is the point you decided in advance to exit — follow the plan, not the feeling.',
                suggest=None))
        elif price <= stop * 1.02:
            actions.append(_action(
                'STOP_NEAR', 'high', ticker,
                'Price is very close to the stop',
                f'Only {_f((price / stop - 1) * 100)}% is left to the stop at ${_f(stop)}. '
                f'Check the order is actually live with your broker.',
                suggest=None))

        # --- profit is real: move the stop to entry and remove the risk
        if r_multiple is not None and r_multiple >= 1 and stop < entry and price > entry:
            actions.append(_action(
                'BREAKEVEN', 'high', ticker,
                'Move the stop to breakeven',
                f'Open profit is {r_multiple}R — more than the risk you took. '
                f'Raising the stop to ${_f(entry)} makes this trade risk-free.',
                suggest=_f(entry), stop_type='fixed'))
        # --- trend still running: ratchet the trailing stop up
        elif trail and stop is not None and trail > stop * 1.005 and price > entry:
            actions.append(_action(
                'TRAIL_UP', 'medium', ticker,
                'Raise the trailing stop',
                f'The chandelier trail has risen to ${trail}, anchored to the 22-day high '
                f'(${an["levels"]["high22"]}) less an ATR multiple. '
                f'Your current stop at ${_f(stop)} is further away than it needs to be — lock in more.',
                suggest=trail, stop_type='trail'))

    # --- the thesis itself is breaking down
    if an['ma']['dist50'] is not None and an['ma']['dist50'] < 0 and an['regime'] in ('weak', 'down'):
        actions.append(_action(
            'TREND_BREAK', 'high', ticker,
            'Trend break — price is below the 50-day average',
            f'Price ${price} closed below the 50-day average (${an["ma"]["sma50"]}) '
            f'and the trend now reads as {an["regime_he"].lower()}. '
            f'Consider trimming the position or tightening the stop.',
            suggest=trail))

    # --- extended move: take something off the table
    if r_multiple is not None and r_multiple >= 3 and (an['rsi'] or 0) >= 72:
        actions.append(_action(
            'TAKE_PARTIAL', 'medium', ticker,
            'Consider taking partial profit',
            f'{r_multiple}R of profit with RSI at {an["rsi"]} — the move is extended. '
            f'Selling a third to a half and trailing the rest banks profit without '
            f'giving up the trend if it continues.',
            suggest=trail, stop_type='trail'))

    # --- position size is out of line with the risk budget
    equity = settings.get('equity') or 0
    risk_pct = settings.get('risk_pct') or 1.0
    if equity and open_risk and open_risk > equity * (risk_pct / 100) * 1.6:
        actions.append(_action(
            'RISK_OVERSIZE', 'medium', ticker,
            'Position risk exceeds your policy',
            f'Open risk of ${open_risk} is {_f(open_risk / equity * 100)}% of the account, '
            f'against your policy of {risk_pct}% per trade. '
            f'Reduce the size or tighten the stop.',
            suggest=None))

    return actions, metrics


# ---------------------------------------------------------------- 5. plan ---

# trail_mult None = adapt the ATR multiple to the trend instead of pinning it
DEFAULT_SETTINGS = {'equity': 0, 'risk_pct': 1.0, 'trail_mult': None}


def build_plan(positions, watch, settings=None):
    """The whole system in one call: actions, positions, entries, risk."""
    settings = {**DEFAULT_SETTINGS, **(settings or {})}
    positions = positions or []
    watch = watch or []

    held = {(p.get('ticker') or '').upper() for p in positions}
    tickers = sorted(held | {w.upper() for w in watch})[:40]
    if not tickers:
        return {'actions': [], 'positions': [], 'entries': [],
                'risk': _risk_summary([], settings), 'settings': settings,
                'generated_at': int(time.time())}

    with ThreadPoolExecutor(max_workers=10) as ex:
        analyses = list(ex.map(analyze, tickers))
    amap = {a['ticker']: a for a in analyses if a.get('ok')}

    actions, metrics = [], []
    for pos in positions:
        an = amap.get((pos.get('ticker') or '').upper())
        if not an:
            continue
        acts, m = manage_position(pos, an, settings)
        actions.extend(acts)
        metrics.append(m)

    risk = _risk_summary(metrics, settings)
    if risk['heat_pct'] is not None and risk['heat_pct'] > 8:
        actions.append(_action(
            'PORTFOLIO_HEAT', 'high', '—',
            'Total open risk is high',
            f'Open risk across the portfolio — the distance to every stop — is '
            f'{risk["heat_pct"]}% of the account. Keeping that under 6% is the usual '
            f'guidance. Tighten stops or reduce position sizes.'))

    # Entry candidates: watchlist names that are not already held. A ticker can
    # fire several setups at once; show its strongest one and list the rest as
    # confirmation rather than repeating near-identical cards.
    entries = []
    for t in watch:
        an = amap.get(t.upper())
        if not an or t.upper() in held or not an['entries']:
            continue
        best, others = an['entries'][0], an['entries'][1:]
        entries.append({**best, 'ticker': an['ticker'], 'price': an['price'],
                        'regime': an['regime'], 'regime_he': an['regime_he'],
                        'trend_score': an['trend_score'], 'rsi': an['rsi'],
                        'atr_pct': an['atr_pct'],
                        'also': [o['title'] for o in others],
                        'sized_qty': _size_position(an['price'], best['risk_per_share'], settings),
                        'history': an['history']})
    entries.sort(key=lambda e: -e['quality'])

    actions.sort(key=lambda a: (SEVERITY_ORDER.get(a['severity'], 9), a['ticker']))
    return {
        'actions': actions,
        'positions': metrics,
        'entries': entries[:12],
        'risk': risk,
        'settings': settings,
        'missing': [t for t in tickers if t not in amap],
        'generated_at': int(time.time()),
    }


def _size_position(price, risk_per_share, settings):
    """How many shares keep the loss at the stop within the risk budget."""
    equity = settings.get('equity') or 0
    risk_pct = settings.get('risk_pct') or 1.0
    if not equity or not risk_per_share or risk_per_share <= 0 or not price:
        return None
    budget = equity * (risk_pct / 100)
    qty = math.floor(budget / risk_per_share)
    # never let one position swallow more than a third of the account
    qty = min(qty, math.floor(equity * 0.33 / price)) if price else qty
    return max(0, qty)


def _risk_summary(metrics, settings):
    value = sum(m['value'] or 0 for m in metrics)
    cost = sum(m['cost'] or 0 for m in metrics)
    open_risk = sum(m['open_risk'] or 0 for m in metrics)
    equity = settings.get('equity') or value
    largest = max((m['value'] or 0 for m in metrics), default=0)
    return {
        'value': _f(value), 'cost': _f(cost),
        'pnl': _f(value - cost),
        'pnl_pct': _f((value / cost - 1) * 100) if cost else None,
        'open_risk': _f(open_risk),
        'heat_pct': _f(open_risk / equity * 100) if equity else None,
        'positions': len(metrics),
        'unprotected': sum(1 for m in metrics if not m['has_stop']),
        'concentration_pct': _f(largest / value * 100) if value else None,
        'equity': _f(equity),
    }


# ------------------------------------------------------------ 6. backtest ---

# Round-trip friction per side: commission plus the slippage a market order
# actually pays. Ignoring it is the most common way a backtest flatters itself.
COST_PCT = 0.05

WARMUP_BARS = 210          # the 200-day average needs history before it means anything


def _max_drawdown(curve):
    """Deepest peak-to-trough fall of an equity curve, as a positive percent."""
    peak, worst = None, 0.0
    for v in curve:
        peak = v if peak is None or v > peak else peak
        if peak:
            worst = max(worst, (peak - v) / peak * 100)
    return round(worst, 2)


def backtest(ticker, years=3, settings=None):
    """Replay the live rules bar by bar and report what they would have done.

    No lookahead: a setup detected on the close of bar i is entered at the
    open of bar i+1, and every stop decision uses only bars up to that point.
    """
    settings = {**DEFAULT_SETTINGS, **(settings or {})}
    risk_pct = settings.get('risk_pct') or 1.0
    ticker = ticker.strip().upper()

    df = fetch_daily(ticker, range_='5y')
    if df is None or len(df) < WARMUP_BARS + 60:
        return {'ticker': ticker, 'ok': False,
                'error': 'Not enough history for a meaningful backtest (about two years minimum)'}

    ind = _indicators(df)
    closes, opens, highs, lows = ind['close'], ind['open'], ind['high'], ind['low']
    dates = [d.strftime('%Y-%m-%d') for d in df.index]

    first = max(WARMUP_BARS, len(df) - int(years * 252))
    last = len(df) - 1
    if first >= last - 20:
        return {'ticker': ticker, 'ok': False, 'error': 'The requested window is too short to test'}

    equity = 100.0
    curve, trades = [], []
    pos = None                      # {entry, stop, init_stop, shares, bar, setup}
    pending = None                  # a setup fired on the previous close

    for i in range(first, last + 1):
        price = float(closes.iloc[i])

        # --- 1. an order queued yesterday fills at today's open
        if pending is not None and pos is None:
            fill = float(opens.iloc[i])
            stop = pending['stop']
            if stop < fill:                       # the gap may invalidate the setup
                risk_share = fill - stop
                budget = equity * (risk_pct / 100)
                shares = budget / risk_share
                cap = equity * 0.33 / fill        # one name may not become the portfolio
                shares = min(shares, cap)
                if shares > 0:
                    pos = {'entry': fill, 'stop': stop, 'init_stop': stop,
                           'shares': shares, 'bar': i, 'setup': pending['setup'],
                           'setup_he': pending['setup_he']}
            pending = None

        # --- 2. manage an open position against today's bar
        if pos is not None:
            low = float(lows.iloc[i])
            exit_price = None
            if float(opens.iloc[i]) <= pos['stop']:
                exit_price = float(opens.iloc[i])   # gapped through the stop
            elif low <= pos['stop']:
                exit_price = pos['stop']

            if exit_price is not None:
                gross = (exit_price - pos['entry']) * pos['shares']
                cost = (pos['entry'] + exit_price) * pos['shares'] * COST_PCT / 100
                equity += gross - cost
                risk_share = pos['entry'] - pos['init_stop']
                trades.append({
                    'ticker': ticker,
                    'setup': pos['setup'], 'setup_he': pos['setup_he'],
                    'entry_date': dates[pos['bar']], 'exit_date': dates[i],
                    'entry': _f(pos['entry']), 'exit': _f(exit_price),
                    'stop': _f(pos['init_stop']),
                    'bars': i - pos['bar'],
                    'return_pct': _f((exit_price / pos['entry'] - 1) * 100),
                    'r': _f((exit_price - pos['entry']) / risk_share, 2) if risk_share else None,
                    'pnl': _f(gross - cost),
                })
                pos = None
            else:
                snap = _snapshot(ticker, ind, i)
                if snap:
                    risk_share = pos['entry'] - pos['init_stop']
                    r_mult = (price - pos['entry']) / risk_share if risk_share else 0
                    # the same ladder the command center prescribes
                    if r_mult >= 1 and pos['stop'] < pos['entry']:
                        pos['stop'] = pos['entry']            # breakeven
                    trail = snap['trail_stop']
                    if trail and trail > pos['stop']:
                        pos['stop'] = trail                   # ratchet, never down

        # --- 3. flat: look for a setup to queue for tomorrow
        if pos is None and pending is None and i < last:
            snap = _snapshot(ticker, ind, i)
            if snap:
                setups = _entry_setups(snap)
                if setups:
                    best = setups[0]
                    pending = {'stop': best['stop'], 'setup': best['code'],
                               'setup_he': best['title']}

        open_value = (price - pos['entry']) * pos['shares'] if pos else 0
        curve.append(round(equity + open_value, 2))

    # --- buy and hold over the identical window, for an honest comparison
    base = float(closes.iloc[first])
    bh_curve = [round(100 * float(closes.iloc[i]) / base, 2) for i in range(first, last + 1)]

    wins = [t for t in trades if (t['r'] or 0) > 0]
    rs = [t['r'] for t in trades if t['r'] is not None]
    bars_held = sum(t['bars'] for t in trades)
    span = last - first + 1

    return {
        'ticker': ticker, 'ok': True,
        'from': dates[first], 'to': dates[last], 'years': round(span / 252, 1),
        'trades': trades[::-1],
        'stats': {
            'count': len(trades),
            'wins': len(wins),
            'win_rate': _f(len(wins) / len(trades) * 100, 1) if trades else None,
            'expectancy_r': _f(sum(rs) / len(rs), 2) if rs else None,
            'best_r': _f(max(rs), 2) if rs else None,
            'worst_r': _f(min(rs), 2) if rs else None,
            'avg_bars': round(bars_held / len(trades)) if trades else None,
            'exposure_pct': _f(bars_held / span * 100, 1) if span else None,
            'system_return': _f(curve[-1] - 100),
            'system_dd': _max_drawdown(curve),
            'hold_return': _f(bh_curve[-1] - 100),
            'hold_dd': _max_drawdown(bh_curve),
            'cost_pct': COST_PCT,
        },
        'curve': curve,
        'hold_curve': bh_curve,
        'dates': dates[first:last + 1],
    }


# ------------------------------------------------------------- 7. gaps ---

# Below this a gap is just the normal overnight drift of a liquid stock.
MIN_GAP_PCT = 0.75


def _gap_from_frame(ticker, df, ind=None):
    """Classify the most recent session's opening gap.

    A gap is the distance between today's open and yesterday's close. What
    matters for trading it is less the size than whether it has been filled:
    an unfilled gap leaves an untested price level above or below, while a
    filled one has already been rejected intraday.
    """
    if df is None or len(df) < 25:
        return None
    o = float(df['Open'].iloc[-1])
    h = float(df['High'].iloc[-1])
    low = float(df['Low'].iloc[-1])
    c = float(df['Close'].iloc[-1])
    prev_close = float(df['Close'].iloc[-2])
    if not prev_close or not o:
        return None

    gap_pct = (o - prev_close) / prev_close * 100
    if abs(gap_pct) < MIN_GAP_PCT:
        return None

    direction = 'up' if gap_pct > 0 else 'down'
    # The gap is filled once price trades back through yesterday's close.
    filled = low <= prev_close if direction == 'up' else h >= prev_close
    # How much of the gap has been retraced so far, 0 to 1.
    span = abs(o - prev_close)
    travelled = (o - low) if direction == 'up' else (h - o)
    retrace = max(0.0, min(1.0, travelled / span)) if span else 0.0

    vol = float(df['Volume'].iloc[-1])
    vol_avg = float(df['Volume'].iloc[-21:-1].mean()) or 1.0
    atr_v = float(atr(df).iloc[-1])

    return {
        'ticker': ticker,
        'direction': direction,
        'gap_pct': _f(gap_pct),
        # A gap worth noting is large relative to the stock's own daily range,
        # not merely large in percent: 2% is routine in one name and a shock
        # in another.
        'gap_atr': _f(span / atr_v, 2) if atr_v else None,
        'prev_close': _f(prev_close),
        'open': _f(o),
        'price': _f(c),
        'high': _f(h), 'low': _f(low),
        'fill_level': _f(prev_close),
        'filled': bool(filled),
        'retrace_pct': _f(retrace * 100, 1),
        # Held means price stayed on the gap's side of the open all session.
        'held': bool(c >= o) if direction == 'up' else bool(c <= o),
        'from_open_pct': _f((c - o) / o * 100),
        'vol_ratio': _f(vol / vol_avg),
        'date': df.index[-1].strftime('%Y-%m-%d'),
    }


def detect_gap(ticker):
    """The latest opening gap for one symbol, or None when there isn't one."""
    df = fetch_daily(ticker, range_='3mo')
    if df is None:
        return None
    try:
        return _gap_from_frame(ticker.strip().upper(), df)
    except Exception:
        return None


def scan_gaps(tickers, min_pct=MIN_GAP_PCT):
    """Gaps across a universe, biggest first."""
    tickers = list(dict.fromkeys(t.strip().upper() for t in tickers if t.strip()))[:120]
    if not tickers:
        return []
    with ThreadPoolExecutor(max_workers=12) as ex:
        found = list(ex.map(detect_gap, tickers))
    gaps = [g for g in found if g and abs(g['gap_pct'] or 0) >= min_pct]
    gaps.sort(key=lambda g: -abs(g['gap_pct'] or 0))
    return gaps
