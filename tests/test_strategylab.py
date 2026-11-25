"""Strategy Lab: next-open fills, costs, gap fills at stops, no lookahead, validation."""
import pandas as pd
import pytest

import strategylab as L


def frame(closes, opens=None, highs=None, lows=None):
    idx = pd.bdate_range('2024-01-01', periods=len(closes))
    o = opens or closes
    return pd.DataFrame({'Open': o, 'High': highs or [max(a, b) for a, b in zip(o, closes)],
                         'Low': lows or [min(a, b) for a, b in zip(o, closes)], 'Close': closes, 'Volume': [1] * len(closes)},
                        index=idx)


def test_breakout_fills_next_open_and_exits_after_n_bars():
    closes = [10.0] * 30 + [11.0] + [12.0] * 10 + [13.0] * 30
    opens = [10.0] * 31 + [11.5] + [12.0] * 9 + [13.0] * 30
    r = L.run(frame(closes, opens), {'entry': [{'type': 'breakout', 'period': 20}], 'exit': [{'type': 'bars_held', 'period': 5}]})
    t = r['trades'][0]
    assert t['entry_date'] == r['curve'][31]['date'] and t['entry'] == 11.5      # signal on bar 30's close, fill at bar 31's open
    assert t['bars'] == 6 and t['reason'] == 'exit rule'                         # held 5 bars -> exit decided on close, filled next open
    assert t['return_pct'] == round((12.0 / 11.5 - 1) * 100, 2)


def test_costs_on_both_sides():
    closes = [10.0] * 30 + [11.0] + [12.0] * 40
    base = {'entry': [{'type': 'breakout', 'period': 20}], 'exit': [{'type': 'bars_held', 'period': 3}]}
    free = L.run(frame(closes), base)['trades'][0]['return_pct']
    cost = L.run(frame(closes), {**base, 'commission_bps': 10, 'slippage_bps': 15})['trades'][0]['return_pct']
    # fill = 12 * 1.0025 in, 12 * 0.9975 out
    assert cost == round((0.9975 / 1.0025 - 1) * 100, 2) and cost < free


def test_stop_gap_fills_at_the_open():
    closes = [10.0] * 30 + [11.0] + [11.0] * 5 + [8.0] * 30
    opens = [10.0] * 31 + [11.0] * 5 + [7.5] * 30                                  # gaps down below any stop
    lows = [min(a, b) - 0.01 for a, b in zip(opens, closes)]
    r = L.run(frame(closes, opens, lows=lows), {'entry': [{'type': 'breakout', 'period': 20}], 'stop_atr': 2})
    t = r['trades'][0]
    assert t['reason'] == 'stop' and t['exit'] == 7.5                             # filled at the gap open, not at the stop level


def test_no_lookahead_future_bars_do_not_change_past_trades():
    import random
    rnd = random.Random(3)
    closes = [100.0]
    for _ in range(400):
        closes.append(closes[-1] * (1 + rnd.gauss(0.0005, 0.02)))
    strat = {'entry': [{'type': 'rsi_below', 'value': 35}], 'exit': [{'type': 'rsi_above', 'value': 60}], 'stop_atr': 3}
    full = L.run(frame(closes), strat)
    cut = L.run(frame(closes[:300]), strat)
    done_before = [t for t in full['trades'] if t['exit_date'] < cut['end']]
    assert done_before == [t for t in cut['trades'] if t['exit_date'] < cut['end']][:len(done_before)]
    # changing every bar after 300 leaves the first 299 curve points unchanged
    other = L.run(frame(closes[:300] + [c * 3 for c in closes[300:]]), strat)
    assert full['curve'][:299] == other['curve'][:299]


def test_buy_hold_and_monthly():
    closes = [100.0 + i for i in range(80)]
    r = L.run(frame(closes), {'entry': [{'type': 'close_above_ma', 'period': 10}], 'exit': [{'type': 'close_below_ma', 'period': 10}]})
    assert r['stats']['buy_hold_return'] == round((179 / 100 - 1) * 100, 2)
    assert set(r['monthly']) == {'2024-01', '2024-02', '2024-03', '2024-04'}
    assert r['open_trade'] is not None                                            # still in at the end, reported apart


@pytest.mark.parametrize('bad,msg', [
    ({'entry': []}, 'at least one entry'),
    ({'entry': [{'type': 'moon'}]}, 'unknown entry'),
    ({'entry': [{'type': 'rsi_below', 'value': 150}], 'stop_atr': 2}, 'between 0 and 100'),
    ({'entry': [{'type': 'rsi_below', 'value': 30}]}, 'choose an exit'),
    ({'entry': [{'type': 'breakout', 'period': 1}], 'stop_atr': 2}, 'between 2 and 400'),
])
def test_validation(bad, msg):
    with pytest.raises(L.StrategyError, match=msg):
        L.clean(bad)
