"""Alert rules: parsing, every kind's evaluation, and missing data reported as unknown, not as false."""
import pytest

import alertrules as A


def ev(cond, v, **d):
    return A.evaluate({'ticker': 'X', 'condition': cond, 'price': v}, d)


def test_price_change_rsi_volume():
    assert ev('above', 100, price=101)['met'] is True and ev('below', 100, price=101)['met'] is False
    assert ev('chg_below', -3, chg=-3.5)['met'] is True
    assert ev('rsi_above', 70, rsi=71.2)['met'] is True and ev('rsi_below', 30, rsi=31)['met'] is False
    assert ev('relvol_above', 2, rel_vol=2.4)['met'] is True


def test_cross_needs_the_previous_close_on_the_other_side():
    assert ev('cross_above_ma:50', 50, closes=[99, 101], ma={50: [100, 100.2]})['met'] is True
    assert ev('cross_above_ma:50', 50, closes=[101, 102], ma={50: [100, 100.2]})['met'] is False      # already above
    assert ev('cross_below_ma:20', 20, closes=[101, 99], ma={20: [100, 100]})['met'] is True
    assert ev('cross_above_ma:50', 50, closes=[99, 101], ma={})['met'] is None


def test_earnings_and_stop():
    assert ev('earnings_within', 5, earnings_in_days=3)['met'] is True
    assert ev('earnings_within', 5, earnings_in_days=None)['met'] is False
    r = ev('near_stop', 3, price=103, stop=100)
    assert r['met'] is True and r['value'] == 3.0
    assert ev('near_stop', 3, price=103)['met'] is None


def test_missing_data_is_unknown():
    assert ev('above', 1)['met'] is None and ev('rsi_above', 70)['met'] is None


@pytest.mark.parametrize('cond,v,msg', [('moon', 1, 'unknown'), ('above', 0, 'above zero'), ('rsi_above', 120, 'between 0 and 100'),
                                        ('cross_above_ma:3', 3, 'between 5 and 250'), ('above', 'x', 'a number')])
def test_parse_errors(cond, v, msg):
    with pytest.raises(A.RuleError, match=msg):
        A.parse(cond, v)
