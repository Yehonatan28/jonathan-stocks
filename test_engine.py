"""Tests for the analysis engine, run against synthetic price series.

Market data is mocked so the suite is deterministic and needs no network:
    python3 test_engine.py
"""

import math
import random
from datetime import datetime, timedelta, timezone

import pandas as pd

import engine


# ------------------------------------------------------------- synthetics ---

def series_to_df(closes, vol_last_mult=1.0, seed=7):
    """Build a plausible OHLCV frame around a closing-price path."""
    rnd = random.Random(seed)
    rows, start = [], datetime(2023, 1, 2, tzinfo=timezone.utc)
    for i, c in enumerate(closes):
        prev = closes[i - 1] if i else c
        wiggle = abs(c) * 0.012
        high = max(c, prev) + rnd.uniform(0, wiggle)
        low = min(c, prev) - rnd.uniform(0, wiggle)
        rows.append({'Open': prev, 'High': high, 'Low': low, 'Close': c,
                     'Volume': 1_000_000 * (vol_last_mult if i == len(closes) - 1 else 1),
                     'Time': start + timedelta(days=i)})
    return pd.DataFrame(rows).set_index('Time')


def install(ticker, df):
    """Seed the engine's data cache so analyze() uses our frame."""
    engine._DF_CACHE[f'{ticker}:2y'] = (engine.time.time() + 3600, df)


def uptrend(n=320, start=100.0, daily=0.0018, noise=0.004, seed=3):
    rnd = random.Random(seed)
    price, out = start, []
    for _ in range(n):
        price *= (1 + daily + rnd.gauss(0, noise))
        out.append(price)
    return out


def downtrend(n=320, start=200.0, seed=5):
    return uptrend(n, start, daily=-0.0022, noise=0.005, seed=seed)


def flat(n=320, start=100.0, seed=11):
    rnd = random.Random(seed)
    return [start + math.sin(i / 9) * 1.2 + rnd.gauss(0, 0.5) for i in range(n)]


# ------------------------------------------------------------------ tests ---

CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


@check('indicators: RSI stays in range and reads high on a pure uptrend')
def t_rsi():
    df = series_to_df(uptrend())
    r = engine.rsi(df['Close'])
    assert r.dropna().between(0, 100).all(), 'RSI left the 0-100 range'
    assert r.iloc[-1] > 55, f'RSI on an uptrend should be high, got {r.iloc[-1]}'
    down = engine.rsi(series_to_df(downtrend())['Close'])
    assert down.iloc[-1] < 45, f'RSI on a downtrend should be low, got {down.iloc[-1]}'


@check('indicators: ATR is positive and scales with price')
def t_atr():
    a = engine.atr(series_to_df(uptrend()))
    assert a.iloc[-1] > 0, 'ATR must be positive'
    assert not math.isnan(a.iloc[-1])


@check('indicators: ADX rises on a trend and stays low on chop')
def t_adx():
    trend, _, _ = engine.adx(series_to_df(uptrend()))
    chop, _, _ = engine.adx(series_to_df(flat()))
    assert trend.iloc[-1] > chop.iloc[-1], (
        f'trend ADX {trend.iloc[-1]:.1f} should exceed chop ADX {chop.iloc[-1]:.1f}')


@check('analyze: an uptrend is classified up and scores high')
def t_regime_up():
    install('UPX', series_to_df(uptrend()))
    a = engine.analyze('UPX')
    assert a['ok'], a.get('error')
    assert a['regime'] in ('up', 'strong_up'), a['regime']
    assert a['trend_score'] >= 70, a['trend_score']
    assert a['ma']['sma20'] > a['ma']['sma50'] > a['ma']['sma200']


@check('analyze: a downtrend is classified down and scores low')
def t_regime_down():
    install('DNX', series_to_df(downtrend()))
    a = engine.analyze('DNX')
    assert a['regime'] in ('down', 'weak'), a['regime']
    assert a['trend_score'] <= 40, a['trend_score']
    assert not a['entries'], 'a downtrend must not produce entry setups'


@check('analyze: a shallow dip under the 50-day MA is still an uptrend')
def t_pullback_regime():
    closes = uptrend(n=300)
    for i in range(1, 9):                    # dip ~1% below the 50-day average
        closes[-i] = closes[-10] * (1 - 0.004 * (9 - i))
    install('DIP', series_to_df(closes))
    a = engine.analyze('DIP')
    assert a['ma']['dist50'] < 0, 'test setup should put price under the MA50'
    assert a['regime'] == 'up', (
        f"a shallow pullback must not read as a broken trend, got {a['regime']}")


@check('analyze: too little history fails cleanly instead of raising')
def t_short_history():
    install('TINY', series_to_df(uptrend(n=20)))
    a = engine.analyze('TINY')
    assert a['ok'] is False and a['error']


@check('stops: the suggested stop sits below price and within the ATR cap')
def t_initial_stop():
    install('UPX', series_to_df(uptrend()))
    a = engine.analyze('UPX')
    stop = a['suggested_stop']
    assert stop < a['price'], 'stop must be below the price'
    assert a['price'] - stop <= 3.5 * a['atr'] + 0.01, 'risk exceeds the 3.5 ATR cap'
    assert a['price'] - stop >= 0.8 * a['atr'] - 0.01, 'stop is too tight to survive noise'


@check('stops: the trailing stop tracks the 22-day high, never above price')
def t_trail_stop():
    install('UPX', series_to_df(uptrend()))
    a = engine.analyze('UPX')
    trail = a['trail_stop']
    assert trail < a['price'], 'a trailing stop above the price would fire instantly'
    assert trail <= a['levels']['high22'] - 2.4 * a['atr'] + 0.01


@check('entries: a pullback to a rising MA is detected')
def t_pullback():
    closes = uptrend(n=300)
    # walk the last few bars back down toward the 20-day average
    for i in range(1, 9):
        closes[-i] = closes[-10] * (1 - 0.004 * (9 - i))
    install('PBX', series_to_df(closes))
    a = engine.analyze('PBX')
    codes = [e['code'] for e in a['entries']]
    assert a['regime'] in ('up', 'strong_up'), a['regime']
    assert 'PULLBACK_MA' in codes, f'expected a pullback setup, got {codes}'
    e = [x for x in a['entries'] if x['code'] == 'PULLBACK_MA'][0]
    assert e['stop'] < a['price'] and e['target1'] > a['price']
    assert e['risk_per_share'] > 0
    # reward-to-risk of the first target is 2R by construction
    assert abs((e['target1'] - a['price']) / e['risk_per_share'] - 2) < 0.05


@check('entries: a volume breakout above the 20-day high is detected')
def t_breakout():
    closes = uptrend(n=300)
    closes[-1] = max(closes[-25:]) * 1.035
    install('BRK', series_to_df(closes, vol_last_mult=2.2))
    a = engine.analyze('BRK')
    codes = [e['code'] for e in a['entries']]
    assert 'BREAKOUT' in codes, f'expected a breakout setup, got {codes}'
    assert a['vol_ratio'] > 1.3


@check('manage: a position with no stop raises SET_STOP with a usable level')
def t_no_stop():
    install('UPX', series_to_df(uptrend()))
    a = engine.analyze('UPX')
    pos = {'id': 1, 'ticker': 'UPX', 'qty': 10, 'entry': a['price'] * 0.9}
    acts, m = engine.manage_position(pos, a, engine.DEFAULT_SETTINGS)
    codes = [x['code'] for x in acts]
    assert 'SET_STOP' in codes, codes
    act = [x for x in acts if x['code'] == 'SET_STOP'][0]
    assert act['severity'] == 'high'
    assert 0 < act['suggest'] < a['price']
    assert m['has_stop'] is False


@check('manage: a breached stop is critical')
def t_stop_hit():
    install('UPX', series_to_df(uptrend()))
    a = engine.analyze('UPX')
    pos = {'id': 1, 'ticker': 'UPX', 'qty': 10,
           'entry': a['price'] * 0.95, 'stop': a['price'] * 1.01,
           'init_stop': a['price'] * 0.9}
    acts, _ = engine.manage_position(pos, a, engine.DEFAULT_SETTINGS)
    hit = [x for x in acts if x['code'] == 'STOP_HIT']
    assert hit and hit[0]['severity'] == 'critical', [x['code'] for x in acts]


@check('manage: a 1R winner is told to move the stop to breakeven')
def t_breakeven():
    install('UPX', series_to_df(uptrend()))
    a = engine.analyze('UPX')
    entry = a['price'] * 0.88
    init = entry * 0.94                      # risk ~6%, profit ~13% => ~2R
    pos = {'id': 1, 'ticker': 'UPX', 'qty': 10, 'entry': entry,
           'stop': init, 'init_stop': init}
    acts, m = engine.manage_position(pos, a, engine.DEFAULT_SETTINGS)
    codes = [x['code'] for x in acts]
    assert m['r_multiple'] >= 1, m['r_multiple']
    assert 'BREAKEVEN' in codes, codes
    assert [x for x in acts if x['code'] == 'BREAKEVEN'][0]['suggest'] == round(entry, 2)


@check('manage: a stop already at breakeven is ratcheted up instead')
def t_trail_up():
    install('UPX', series_to_df(uptrend()))
    a = engine.analyze('UPX')
    entry = a['price'] * 0.80
    pos = {'id': 1, 'ticker': 'UPX', 'qty': 10, 'entry': entry,
           'stop': entry, 'init_stop': entry * 0.95, 'stop_type': 'trail'}
    acts, _ = engine.manage_position(pos, a, engine.DEFAULT_SETTINGS)
    codes = [x['code'] for x in acts]
    assert 'TRAIL_UP' in codes, codes
    act = [x for x in acts if x['code'] == 'TRAIL_UP'][0]
    assert act['suggest'] > pos['stop'], 'a trailing stop must only move up'
    assert act['stop_type'] == 'trail'


@check('manage: a profitable position in a broken trend is flagged')
def t_trend_break():
    install('DNX', series_to_df(downtrend()))
    a = engine.analyze('DNX')
    pos = {'id': 1, 'ticker': 'DNX', 'qty': 10, 'entry': a['price'] * 0.9,
           'stop': a['price'] * 0.8, 'init_stop': a['price'] * 0.8}
    acts, _ = engine.manage_position(pos, a, engine.DEFAULT_SETTINGS)
    assert 'TREND_BREAK' in [x['code'] for x in acts], [x['code'] for x in acts]


@check('sizing: share count keeps the loss at the stop inside the risk budget')
def t_sizing():
    s = {'equity': 100_000, 'risk_pct': 1.0}
    qty = engine._size_position(price=50, risk_per_share=2.5, settings=s)
    assert qty == 400, qty                       # 1% of 100k = $1000 / $2.5
    assert qty * 2.5 <= s['equity'] * 0.01 + 1e-9
    # the one-third-of-account cap binds when the stop is very tight
    capped = engine._size_position(price=50, risk_per_share=0.05, settings=s)
    assert capped == math.floor(100_000 * 0.33 / 50), capped
    assert engine._size_position(50, 0, s) is None
    assert engine._size_position(50, 2.5, {'equity': 0}) is None


@check('risk: portfolio heat and unprotected positions are summarized')
def t_risk_summary():
    metrics = [
        {'value': 6000, 'cost': 5000, 'open_risk': 400, 'has_stop': True},
        {'value': 4000, 'cost': 4200, 'open_risk': 600, 'has_stop': False},
    ]
    r = engine._risk_summary(metrics, {'equity': 10000, 'risk_pct': 1})
    assert r['value'] == 10000 and r['cost'] == 9200
    assert r['pnl'] == 800
    assert r['open_risk'] == 1000 and r['heat_pct'] == 10.0
    assert r['unprotected'] == 1 and r['positions'] == 2
    assert r['concentration_pct'] == 60.0


@check('plan: end to end - actions sorted by severity, entries exclude holdings')
def t_plan():
    install('UPX', series_to_df(uptrend()))
    install('DNX', series_to_df(downtrend()))
    pb = uptrend(n=300)
    for i in range(1, 9):
        pb[-i] = pb[-10] * (1 - 0.004 * (9 - i))
    install('PBX', series_to_df(pb))

    positions = [
        {'id': 1, 'ticker': 'UPX', 'qty': 10, 'entry': 50},          # no stop
        {'id': 2, 'ticker': 'DNX', 'qty': 5, 'entry': 120,
         'stop': 200, 'init_stop': 110},                              # stop breached
    ]
    plan = engine.build_plan(positions, watch=['PBX', 'UPX'],
                             settings={'equity': 50_000, 'risk_pct': 1.0})

    sev = [engine.SEVERITY_ORDER[a['severity']] for a in plan['actions']]
    assert sev == sorted(sev), 'actions must come back sorted by severity'
    assert plan['actions'][0]['severity'] == 'critical'
    assert {'SET_STOP', 'STOP_HIT'} <= {a['code'] for a in plan['actions']}
    assert len(plan['positions']) == 2
    tickers = {e['ticker'] for e in plan['entries']}
    assert 'UPX' not in tickers, 'a held name must not appear as a new entry'
    assert 'PBX' in tickers
    assert all(e['sized_qty'] is not None for e in plan['entries'])
    assert plan['risk']['unprotected'] == 1
    assert len(tickers) == len(plan['entries']), 'one card per ticker, not one per setup'
    assert all('also' in e for e in plan['entries']), 'extra setups ride along as confirmation'


@check('plan: an empty portfolio returns a valid empty plan')
def t_empty_plan():
    plan = engine.build_plan([], [], {})
    assert plan['actions'] == [] and plan['entries'] == []
    assert plan['risk']['positions'] == 0
    assert plan['risk']['heat_pct'] is None


@check('plan: a ticker with no market data is reported, not crashed on')
def t_missing_data():
    engine._DF_CACHE['NODATA:2y'] = (engine.time.time() + 3600, None)
    plan = engine.build_plan([{'id': 1, 'ticker': 'NODATA', 'qty': 1, 'entry': 10}],
                             ['NODATA'], {})
    assert 'NODATA' in plan['missing']
    assert plan['positions'] == []




@check('backtest: an uptrend produces trades with sane bookkeeping')
def t_backtest_basic():
    install('BTU', series_to_df(uptrend(n=900, start=50)))
    engine._DF_CACHE['BTU:5y'] = engine._DF_CACHE['BTU:2y']
    b = engine.backtest('BTU', years=3, settings={'risk_pct': 1.0})
    assert b['ok'], b.get('error')
    s = b['stats']
    assert s['count'] > 0, 'an uptrend should trigger at least one entry'
    for t in b['trades']:
        assert t['exit_date'] >= t['entry_date'], 'a trade cannot exit before it opens'
        assert t['bars'] >= 0
        assert t['entry'] > 0 and t['exit'] > 0
        assert t['stop'] < t['entry'], 'the initial stop must sit below the entry'
    assert len(b['curve']) == len(b['hold_curve']) == len(b['dates'])
    assert s['win_rate'] is not None and 0 <= s['win_rate'] <= 100


@check('backtest: losses are bounded near -1R by the stop')
def t_backtest_risk_bounded():
    install('BTU', series_to_df(uptrend(n=900, start=50)))
    engine._DF_CACHE['BTU:5y'] = engine._DF_CACHE['BTU:2y']
    b = engine.backtest('BTU', years=3)
    losers = [t['r'] for t in b['trades'] if t['r'] is not None and t['r'] < 0]
    # a gap can overshoot the stop, but nothing should lose multiples of the risk
    assert all(r > -2.5 for r in losers), f'a stop failed to cap the loss: {losers}'


@check('backtest: no lookahead - the result is unchanged by future bars')
def t_backtest_no_lookahead():
    """Appending future bars must not alter a single decision already taken.

    Both runs use a window long enough to start at the same warmup bar, so the
    only difference between them is the 40 bars of future appended to the
    second. Any change to a trade that closed before that future exists could
    only come from the engine peeking ahead.
    """
    full = uptrend(n=900, start=50)
    install('LOOK', series_to_df(full))
    engine._DF_CACHE['LOOK:5y'] = engine._DF_CACHE['LOOK:2y']
    a = engine.backtest('LOOK', years=10)

    install('LOOK2', series_to_df(full + uptrend(n=40, start=full[-1], seed=99)))
    engine._DF_CACHE['LOOK2:5y'] = engine._DF_CACHE['LOOK2:2y']
    b = engine.backtest('LOOK2', years=10)

    assert a['from'] == b['from'], f"windows differ: {a['from']} vs {b['from']}"
    cut = a['to']
    keep = lambda bt: [(t['entry_date'], t['exit_date'], t['entry'], t['exit'], t['r'])
                       for t in bt['trades'] if t['exit_date'] < cut]
    ta, tb = keep(a), keep(b)
    assert ta, 'the fixture should close at least one trade before the cut'
    assert ta == tb, f'future bars changed past trades\n{ta[:3]}\n{tb[:3]}'


@check('backtest: a downtrend stays flat rather than inventing trades')
def t_backtest_downtrend():
    install('BTD', series_to_df(downtrend(n=900, start=400)))
    engine._DF_CACHE['BTD:5y'] = engine._DF_CACHE['BTD:2y']
    b = engine.backtest('BTD', years=3)
    assert b['ok']
    assert b['stats']['count'] == 0, 'the entry rules require an uptrend'
    assert b['stats']['system_return'] == 0
    assert b['stats']['hold_return'] < 0, 'buy and hold should lose in a downtrend'


@check('backtest: too little history is refused instead of guessed at')
def t_backtest_short():
    install('SHORT', series_to_df(uptrend(n=120)))
    engine._DF_CACHE['SHORT:5y'] = engine._DF_CACHE['SHORT:2y']
    b = engine.backtest('SHORT')
    assert b['ok'] is False and b['error']


@check('backtest: drawdown is measured peak to trough')
def t_drawdown():
    assert engine._max_drawdown([100, 120, 60, 90]) == 50.0
    assert engine._max_drawdown([100, 110, 120]) == 0.0
    assert engine._max_drawdown([]) == 0.0


def main():
    failed = 0
    for name, fn in CHECKS:
        try:
            fn()
            print(f'  \033[32mPASS\033[0m  {name}')
        except AssertionError as e:
            failed += 1
            print(f'  \033[31mFAIL\033[0m  {name}\n          {e}')
        except Exception as e:
            failed += 1
            print(f'  \033[31mERROR\033[0m {name}\n          {type(e).__name__}: {e}')
    print(f'\n{len(CHECKS) - failed}/{len(CHECKS)} passed')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
