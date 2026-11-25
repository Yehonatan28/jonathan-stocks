"""Risk review and sizing, against hand calculations."""
from datetime import date, timedelta

import pytest

import riskx as R


def test_review_weights_risk_and_warnings():
    pos = [{'ticker': 'AAA', 'qty': 100, 'entry': 50, 'stop': 45},   # value 6000, risk 100*(60-45)=1500
           {'ticker': 'BBB', 'qty': 10, 'entry': 100, 'stop': None},  # unprotected, value 1000
           {'ticker': 'CCC', 'qty': 20, 'entry': 10, 'stop': 12}]     # stop above price: risk 0
    r = R.review(pos, {'AAA': 60, 'BBB': 100, 'CCC': 11}, {'AAA': 2.0, 'CCC': 0.5},
                 {'AAA': 'Technology', 'BBB': 'Technology'}, equity=20000, limits={'max_position_pct': 25})
    a = next(p for p in r['positions'] if p['ticker'] == 'AAA')
    assert a['value'] == 6000 and a['weight'] == 30.0 and a['open_risk'] == 1500 and a['risk_pct'] == 7.5
    assert a['stop_atr'] == 7.5                                  # (60-45)/2
    c = next(p for p in r['positions'] if p['ticker'] == 'CCC')
    assert c['open_risk'] == 0.0 and c['sector'] == 'Other'
    t = r['totals']
    assert t['value'] == 7220 and t['open_risk'] == 1500 and t['open_risk_pct'] == 7.5 and t['unprotected'] == 1
    kinds = {w['kind'] for w in r['warnings']}
    assert {'unprotected', 'position', 'trade_risk', 'wide_stop', 'portfolio_risk'} <= kinds
    tech = next(s for s in r['sectors'] if s['sector'] == 'Technology')
    assert tech['weight'] == 35.0                                # (6000+1000)/20000: at the 35% limit, not above it
    assert 'sector' not in kinds
    r2 = R.review(pos, {'AAA': 60, 'BBB': 100, 'CCC': 11}, {}, {'AAA': 'Technology', 'BBB': 'Technology'},
                  equity=20000, limits={'max_sector_pct': 30})
    assert any(w['kind'] == 'sector' for w in r2['warnings'])
    assert r['warnings'][0]['level'] == 'high'


def test_equity_falls_back_to_positions():
    r = R.review([{'ticker': 'A', 'qty': 1, 'stop': None}], {'A': 100}, {}, {}, equity=0, limits={})
    assert r['equity'] == 100 and r['equity_basis'] == 'positions' and r['positions'][0]['weight'] == 100.0


def test_tight_stop_flagged():
    r = R.review([{'ticker': 'A', 'qty': 1, 'stop': 99.5}], {'A': 100}, {'A': 2.0}, {}, equity=1000, limits={})
    assert any(w['kind'] == 'tight_stop' for w in r['warnings'])


def _series(rets, start=100.0):
    d, px, out = date(2024, 1, 1), start, []
    out.append((d, px))
    for x in rets:
        d += timedelta(days=1)
        px *= 1 + x
        out.append((d, px))
    return out


def test_correlation_identical_opposite_and_short_history():
    base = [0.01 * ((i * 7) % 5 - 2) for i in range(60)]
    t, m, pairs = R.correlation({'A': _series(base), 'B': _series(base, 50), 'C': _series([-x for x in base]), 'D': _series(base[:20])})
    assert t == ['A', 'B', 'C']                                  # D has too few days
    i = {k: n for n, k in enumerate(t)}
    assert m[i['A']][i['B']] == 1.0 and m[i['A']][i['C']] == -1.0
    assert pairs == [{'a': 'A', 'b': 'B', 'corr': 1.0, 'days': 60}]


def test_sizing_long_short_and_cap():
    s = R.size(10000, 1, 50, 48)                                 # 100 risk / 2 per share = 50 shares
    assert s['qty'] == 50 and s['risk'] == 100 and s['position_value'] == 2500 and not s['capped_by_position_limit']
    s = R.size(10000, 1, 50, 49.5, max_position_pct=20)          # 200 shares uncapped -> cap 40 (2000/50)
    assert s['qty'] == 40 and s['capped_by_position_limit'] and s['risk'] == 20
    s = R.size(10000, 2, 100, 105, side='short')
    assert s['qty'] == 40 and s['risk'] == 200
    with pytest.raises(ValueError, match='below the entry'):
        R.size(10000, 1, 50, 55)
    with pytest.raises(ValueError, match='above the entry'):
        R.size(10000, 1, 50, 45, side='short')


def test_limits_are_bounded():
    assert R.limits_from({'max_position_pct': 500, 'max_trade_risk_pct': '2'}) == {**R.DEFAULT_LIMITS, 'max_trade_risk_pct': 2.0}
