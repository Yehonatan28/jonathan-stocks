"""מנוע ניתוח טכני וניהול סיכונים.

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


def _slope_pct(series, bars):
    """Percent change of a moving average over `bars` - its direction."""
    if len(series.dropna()) <= bars:
        return None
    now, then = series.iloc[-1], series.iloc[-1 - bars]
    if not then or math.isnan(now) or math.isnan(then):
        return None
    return round((now - then) / abs(then) * 100, 2)


# ------------------------------------------------------------- 3. analyze ---

# Regime codes and their Hebrew labels, used across the UI.
REGIMES = {
    'strong_up': 'מגמת עלייה חזקה',
    'up': 'מגמת עלייה',
    'recovering': 'התאוששות',
    'range': 'דשדוש',
    'weak': 'היחלשות',
    'down': 'מגמת ירידה',
}


def analyze(ticker):
    """Full technical picture for one ticker."""
    ticker = ticker.strip().upper()
    df = fetch_daily(ticker)
    if df is None or len(df) < 60:
        return {'ticker': ticker, 'ok': False,
                'error': 'אין מספיק נתונים היסטוריים לניתוח'}

    close, high, low, vol = df['Close'], df['High'], df['Low'], df['Volume']
    price = float(close.iloc[-1])
    prev = float(close.iloc[-2])

    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean() if len(close) >= 200 else close.rolling(len(close)).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()

    r = rsi(close)
    a = atr(df)
    adx_s, plus_di, minus_di = adx(df)
    macd_l, macd_s, macd_h = macd(close)

    atr_v = float(a.iloc[-1])
    atr_pct = atr_v / price * 100 if price else 0

    # channels & structure
    donch20_high = float(high.iloc[-21:-1].max())
    donch20_low = float(low.iloc[-21:-1].min())
    donch55_high = float(high.iloc[-56:-1].max()) if len(high) > 56 else donch20_high
    swing_low = float(low.iloc[-10:].min())
    swing_high = float(high.iloc[-10:].max())
    hh22 = float(high.iloc[-22:].max())
    wk52_high = float(high.iloc[-252:].max())
    wk52_low = float(low.iloc[-252:].min())

    vol_avg = float(vol.iloc[-20:].mean()) or 1.0
    vol_ratio = float(vol.iloc[-1]) / vol_avg

    v_sma20 = float(sma20.iloc[-1]) if not math.isnan(sma20.iloc[-1]) else price
    v_sma50 = float(sma50.iloc[-1]) if not math.isnan(sma50.iloc[-1]) else price
    v_sma200 = float(sma200.iloc[-1]) if not math.isnan(sma200.iloc[-1]) else price
    v_rsi = float(r.iloc[-1])
    v_adx = float(adx_s.iloc[-1])
    slope200 = _slope_pct(sma200, 20)
    slope50 = _slope_pct(sma50, 10)

    above200 = price > v_sma200
    above50 = price > v_sma50
    above20 = price > v_sma20
    golden = v_sma50 > v_sma200
    macd_up = float(macd_l.iloc[-1]) > float(macd_s.iloc[-1])

    # ----- regime
    # A pullback is not a broken trend: as long as the 50/200 structure holds
    # and price is above the 200, a dip of up to 4% under the 50 still counts
    # as an uptrend - that dip is exactly where the best entries live.
    pullback_ok = price >= v_sma50 * 0.96
    if above20 and above50 and golden and (slope200 or 0) > 0 and v_adx >= 20:
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

    # ----- trend score 0-100: how much the evidence agrees on "up"
    score = 0
    score += 20 if above200 else 0
    score += 15 if above50 else 0
    score += 10 if above20 else 0
    score += 15 if golden else 0
    score += 10 if (slope200 or 0) > 0 else 0
    score += 10 if macd_up else 0
    score += 10 if (v_adx >= 20 and float(plus_di.iloc[-1]) > float(minus_di.iloc[-1])) else 0
    score += 10 if 45 <= v_rsi <= 70 else (5 if 35 <= v_rsi < 45 else 0)
    score = min(100, score)

    # ----- crossover freshness (how many bars ago it happened)
    def _bars_since(cond_series, limit=30):
        tail = cond_series.iloc[-limit:]
        flips = tail.ne(tail.shift())
        idx = [i for i, v in enumerate(flips.tolist()) if v and i > 0]
        return (len(tail) - 1 - idx[-1]) if idx else None

    golden_cross_bars = None
    if len(sma200.dropna()) > 30:
        gc = (sma50 > sma200)
        if bool(gc.iloc[-1]):
            golden_cross_bars = _bars_since(gc)
    macd_cross_bars = None
    mc = macd_l > macd_s
    if bool(mc.iloc[-1]):
        macd_cross_bars = _bars_since(mc)

    out = {
        'ticker': ticker, 'ok': True,
        'price': _f(price), 'prev_close': _f(prev),
        'chg_pct': _f((price - prev) / prev * 100) if prev else None,
        'regime': regime, 'regime_he': REGIMES[regime], 'trend_score': score,
        'ma': {'sma20': _f(v_sma20), 'sma50': _f(v_sma50), 'sma200': _f(v_sma200),
               'ema21': _f(float(ema21.iloc[-1])),
               'slope50': slope50, 'slope200': slope200,
               'dist20': _f((price / v_sma20 - 1) * 100),
               'dist50': _f((price / v_sma50 - 1) * 100),
               'dist200': _f((price / v_sma200 - 1) * 100)},
        'rsi': _f(v_rsi, 1),
        'adx': _f(v_adx, 1),
        'macd_up': macd_up,
        'macd_hist': _f(float(macd_h.iloc[-1]), 3),
        'atr': _f(atr_v), 'atr_pct': _f(atr_pct),
        'vol_ratio': _f(vol_ratio),
        'levels': {'support': _f(donch20_low), 'resistance': _f(donch20_high),
                   'swing_low': _f(swing_low), 'swing_high': _f(swing_high),
                   'high22': _f(hh22), 'breakout55': _f(donch55_high),
                   'wk52_high': _f(wk52_high), 'wk52_low': _f(wk52_low),
                   'from_high_pct': _f((price / wk52_high - 1) * 100)},
        'golden_cross': golden,
        'golden_cross_bars': golden_cross_bars,
        'macd_cross_bars': macd_cross_bars,
        'history': [round(float(p), 2) for p in close.iloc[-120:].tolist()],
    }
    out['entries'] = _entry_setups(out)
    out['suggested_stop'] = suggest_initial_stop(out)
    out['trail_stop'] = suggest_trail_stop(out)
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
                f'תיקון לממוצע הנע {label}',
                [f'המגמה עולה ({an["regime_he"]}) והמחיר חזר לאזור {label} — '
                 f'נקודת כניסה עם סיכון מוגדר',
                 f'RSI {rsi_v} מעיד על תיקון בריא ולא על חולשה',
                 f'ממוצע 50 {"מעל" if an["golden_cross"] else "מתחת ל"}ממוצע 200'],
                62 + an['trend_score'] // 4 + (6 if near20 else 0),
                anchor * 0.995, max(price, anchor * 1.02))

    # 2. breakout of the 20-day range on volume
    if price >= lv['resistance'] and (an['vol_ratio'] or 0) >= 1.3 and healthy:
        add('BREAKOUT',
            'פריצת שיא 20 ימים',
            [f'המחיר פרץ את ההתנגדות ${lv["resistance"]} — השיא של 20 הימים האחרונים',
             f'נפח המסחר פי {an["vol_ratio"]} מהממוצע — הפריצה מגובה בכסף אמיתי',
             'הסטופ ממוקם מתחת לאזור הפריצה'],
            60 + an['trend_score'] // 3,
            lv['resistance'], price + 0.5 * atr_v,
            min(lv['resistance'] - 0.3 * atr_v, price - 1.5 * atr_v))

    # 3. fresh golden cross - a regime change worth acting on
    if an['golden_cross_bars'] is not None and an['golden_cross_bars'] <= 15:
        add('GOLDEN_CROSS',
            'צלב זהב טרי',
            [f'ממוצע 50 חצה מעל ממוצע 200 לפני {an["golden_cross_bars"]} ימי מסחר',
             'היסטורית זהו שינוי מגמה ארוך־טווח, לא רעש יומי',
             'עדיף להיכנס בתיקון הראשון ולא במרדף'],
            58 + an['trend_score'] // 3, ma['sma50'], price + 0.5 * atr_v)

    # 4. momentum turning up while the long-term trend is intact
    if (an['macd_cross_bars'] is not None and an['macd_cross_bars'] <= 5
            and healthy and rsi_v is not None and rsi_v < 68):
        add('MACD_CROSS',
            'היפוך מומנטום MACD',
            [f'קו ה־MACD חצה מעל קו האיתות לפני {an["macd_cross_bars"]} ימים',
             'המחיר מעל ממוצע 200 — המומנטום מתיישר עם המגמה הראשית',
             'איתות מוקדם יחסית, מתאים לכניסה חלקית'],
            52 + an['trend_score'] // 4, price - 0.5 * atr_v, price + atr_v)

    # 5. deep oversold inside a long-term uptrend
    if healthy and rsi_v is not None and rsi_v <= 34:
        add('OVERSOLD_UPTREND',
            'מכירת יתר במגמה עולה',
            [f'RSI {rsi_v} — מכירת יתר, אך המחיר עדיין מעל ממוצע 200',
             'תיקונים כאלה במגמה ראשית עולה נוטים להיות הזדמנות',
             'המתן לנר ירוק ראשון לאישור לפני כניסה'],
            48 + an['trend_score'] // 4, price - atr_v, price + 0.5 * atr_v)

    # 6. reclaiming the 200-day average after being below it
    if (ma['dist200'] is not None and 0 <= ma['dist200'] <= 3
            and not an['golden_cross']):
        add('RECLAIM_200',
            'חזרה מעל ממוצע 200',
            ['המחיר חזר לסגור מעל ממוצע 200 — סימן ראשון להתאוששות',
             'ממוצע 50 עדיין מתחת ל־200, לכן זו כניסה מוקדמת ולא מגמה מאושרת',
             'שמור על פוזיציה קטנה יותר מהרגיל'],
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
            'אין סטופ מוגדר לפוזיציה',
            f'הפוזיציה חשופה לכל ירידה. הסטופ המומלץ הוא ${suggested_initial} '
            f'(מתחת לשפל האחרון ו־2×ATR מהמחיר) — סיכון של '
            f'{_f((price / suggested_initial - 1) * 100)}% מהמחיר הנוכחי.',
            suggest=suggested_initial, stop_type='fixed'))
    else:
        # --- the stop has already been breached
        if price <= stop:
            actions.append(_action(
                'STOP_HIT', 'critical', ticker,
                'הסטופ נפרץ — יש לצאת',
                f'המחיר ${price} נמצא מתחת לסטופ שהגדרת ${_f(stop)}. '
                f'זו הנקודה שבה החלטת מראש לצאת — צא לפי התוכנית, לא לפי התחושה.',
                suggest=None))
        elif price <= stop * 1.02:
            actions.append(_action(
                'STOP_NEAR', 'high', ticker,
                'המחיר קרוב מאוד לסטופ',
                f'נותרו {_f((price / stop - 1) * 100)}% בלבד עד הסטופ ב־${_f(stop)}. '
                f'ודא שהפקודה אכן קיימת אצל הברוקר.',
                suggest=None))

        # --- profit is real: move the stop to entry and remove the risk
        if r_multiple is not None and r_multiple >= 1 and stop < entry and price > entry:
            actions.append(_action(
                'BREAKEVEN', 'high', ticker,
                'העלה סטופ לנקודת האיזון',
                f'הרווח הפתוח הוא {r_multiple}R — מעל הסיכון שלקחת. '
                f'העלאת הסטופ ל־${_f(entry)} הופכת את העסקה לחסרת סיכון.',
                suggest=_f(entry), stop_type='fixed'))
        # --- trend still running: ratchet the trailing stop up
        elif trail and stop is not None and trail > stop * 1.005 and price > entry:
            actions.append(_action(
                'TRAIL_UP', 'medium', ticker,
                'העלה את הטריילינג סטופ',
                f'הסטופ הנגרר (Chandelier) עלה ל־${trail} לפי השיא של 22 הימים '
                f'(${an["levels"]["high22"]}) פחות מכפלת ATR. '
                f'הסטופ הנוכחי ${_f(stop)} מיותר ומרוחק — נעל עוד רווח.',
                suggest=trail, stop_type='trail'))

    # --- the thesis itself is breaking down
    if an['ma']['dist50'] is not None and an['ma']['dist50'] < 0 and an['regime'] in ('weak', 'down'):
        actions.append(_action(
            'TREND_BREAK', 'high', ticker,
            'שבירת מגמה — המחיר מתחת לממוצע 50',
            f'המחיר ${price} נסגר מתחת לממוצע הנע 50 (${an["ma"]["sma50"]}) '
            f'והמגמה הוגדרה כ{an["regime_he"]}. שקול הקטנת פוזיציה או הידוק הסטופ.',
            suggest=trail))

    # --- extended move: take something off the table
    if r_multiple is not None and r_multiple >= 3 and (an['rsi'] or 0) >= 72:
        actions.append(_action(
            'TAKE_PARTIAL', 'medium', ticker,
            'שקול מימוש חלקי',
            f'רווח של {r_multiple}R ו־RSI {an["rsi"]} — המהלך מתוח. '
            f'מימוש שליש עד חצי מהפוזיציה והשארת היתר עם טריילינג סטופ '
            f'מקבע רווח בלי לוותר על המשך המגמה.',
            suggest=trail, stop_type='trail'))

    # --- position size is out of line with the risk budget
    equity = settings.get('equity') or 0
    risk_pct = settings.get('risk_pct') or 1.0
    if equity and open_risk and open_risk > equity * (risk_pct / 100) * 1.6:
        actions.append(_action(
            'RISK_OVERSIZE', 'medium', ticker,
            'הסיכון בפוזיציה חורג מהמדיניות',
            f'הסיכון הפתוח ${open_risk} הוא '
            f'{_f(open_risk / equity * 100)}% מהתיק, לעומת מדיניות של {risk_pct}% לעסקה. '
            f'הקטן כמות או הדק את הסטופ.',
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
            'חשיפת הסיכון הכוללת גבוהה',
            f'סך הסיכון הפתוח (מרחק מהסטופים) הוא {risk["heat_pct"]}% מהתיק. '
            f'מקובל להחזיק את המספר הזה מתחת ל־6%. הדק סטופים או הקטן פוזיציות.'))

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
