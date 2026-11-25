"""Ledger: FIFO lots, fees, splits, dividends and currencies, against hand calculations."""
import pytest

import ledger as L


def tx(type_, date, **kw):
    return {'type': type_, 'date': date, **kw}


BASE = [
    tx('deposit', '2024-01-02', amount=10000),
    tx('buy', '2024-01-03', ticker='abc', qty=10, price=100, fee=5),     # lot 1: cost 1005 -> 100.5/sh
    tx('buy', '2024-02-01', ticker='ABC', qty=10, price=120, fee=5),     # lot 2: cost 1205 -> 120.5/sh
    tx('sell', '2024-03-01', ticker='ABC', qty=15, price=130, fee=10),   # closes lot 1 + 5 of lot 2
    tx('dividend', '2024-03-15', ticker='ABC', amount=12.5),
    tx('fee', '2024-03-31', amount=3),
]


def test_fifo_realised_and_cash():
    r = L.compute(BASE, {'ABC': 140})
    s = r['sales'][0]
    # proceeds 15*130-10 = 1940; cost 10*100.5 + 5*120.5 = 1607.5; gain 332.5
    assert (s['proceeds'], s['cost'], s['gain']) == (1940, 1607.5, 332.5)
    h = r['holdings'][0]
    assert h['ticker'] == 'ABC' and h['qty'] == 5 and h['avg_cost'] == 120.5 and h['cost'] == 602.5
    assert h['value'] == 700 and h['unrealised'] == 97.5 and h['realised'] == 332.5 and h['dividends'] == 12.5
    t = r['totals']['USD']
    # cash: 10000 - 1005 - 1205 + 1940 + 12.5 - 3 = 9739.5
    assert t['cash'] == 9739.5 and t['account_value'] == 10439.5
    assert t['fees'] == 23 and t['net_contributions'] == 10000
    # account value - contributions = realised + unrealised + dividends - standalone fees
    assert round(t['account_value'] - t['net_contributions'], 2) == round(332.5 + 97.5 + 12.5 - 3, 2)


def test_split_keeps_cost_and_changes_quantity():
    r = L.compute(BASE + [tx('split', '2024-04-01', ticker='ABC', ratio=4)], {'ABC': 35})
    h = r['holdings'][0]
    assert h['qty'] == 20 and h['avg_cost'] == round(120.5 / 4, 4) and h['cost'] == 602.5
    assert h['value'] == 700


def test_oversell_is_rejected_with_where():
    with pytest.raises(L.LedgerError, match='selling 25 but only 20 held'):
        L.compute(BASE[:3] + [tx('sell', '2024-03-01', ticker='ABC', qty=25, price=1)])


def test_order_same_day_follows_entry():
    # a sale entered after its buy on the same date is applied after it
    r = L.compute([tx('buy', '2024-01-03', ticker='X', qty=1, price=10), tx('sell', '2024-01-03', ticker='X', qty=1, price=11)])
    assert r['sales'][0]['gain'] == 1 and r['holdings'] == []


def test_currencies_are_never_added():
    r = L.compute([tx('deposit', '2024-01-01', amount=100), tx('deposit', '2024-01-01', amount=500, currency='ils'),
                   tx('buy', '2024-01-02', ticker='TEVA.TA', qty=1, price=50, currency='ILS')], {'TEVA.TA': 60})
    assert set(r['totals']) == {'USD', 'ILS'}
    assert r['totals']['USD']['account_value'] == 100
    assert r['totals']['ILS']['account_value'] == 510


def test_unpriced_position_has_no_value_rather_than_zero():
    r = L.compute([tx('buy', '2024-01-02', ticker='ZZZ', qty=2, price=10)])
    h = r['holdings'][0]
    assert h['value'] is None and h['unrealised'] is None
    assert r['totals']['USD']['account_value'] is None and r['totals']['USD']['unpriced'] == ['ZZZ']


@pytest.mark.parametrize('bad,msg', [
    (tx('buy', '2024-01-02', ticker='A', qty=0, price=1), 'quantity must be more than zero'),
    (tx('buy', '2024-13-02', ticker='A', qty=1, price=1), 'date must be'),
    (tx('swap', '2024-01-02'), 'unknown type'),
    (tx('buy', '2024-01-02', qty=1, price=1), 'symbol is required'),
    (tx('deposit', '2024-01-02', amount='nan'), 'must be a number'),
    (tx('split', '2024-01-02', ticker='A', ratio=2), 'no open position'),
])
def test_validation(bad, msg):
    with pytest.raises(L.LedgerError, match=msg):
        L.compute([bad])
