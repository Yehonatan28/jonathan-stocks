"""Breadth, period returns and the snapshot, checked against numbers worked out by hand."""
from datetime import date, timedelta

import marketintel as M


def _row(t, price, chg, cap=10, **kw):
    return {'ticker': t, 'name': t, 'sector': 'Technology', 'price': price, 'chg': chg, 'cap': cap, **kw}


def test_breadth_counts_and_denominators():
    rows = [
        _row('A', 110, 2.0, cap=30, dma50=100, dma200=90, hi52=111, lo52=60),   # near high (>= 108.78)
        _row('B', 50, -1.0, cap=10, dma50=55, dma200=40, hi52=80, lo52=49.5),   # near low (<= 50.49)
        _row('C', 20, 0.0, cap=10, dma50=19),                                   # no 200d, no 52w
        _row('D', 70, 1.0, cap=50),                                             # nothing but price
        {'ticker': 'E', 'price': None, 'chg': None},                            # unpriced
    ]
    b = M.breadth(rows)
    assert (b['members'], b['priced']) == (5, 4)
    assert (b['advancers'], b['decliners'], b['unchanged']) == (2, 1, 1)
    assert b['ad_ratio'] == 2.0
    # above 50d: A (110>100), C (20>19); B is below. 2 of 3 with the field
    assert b['above_50d'] == {'above': 2, 'of': 3, 'pct': 66.7}
    # above 200d: A and B (50>40); 2 of 2
    assert b['above_200d'] == {'above': 2, 'of': 2, 'pct': 100.0}
    assert b['near_52w_high'] == {'count': 1, 'of': 2}
    assert b['near_52w_low'] == {'count': 1, 'of': 2}
    # cap-weighted: (2*30 - 1*10 + 0*10 + 1*50) / 100 = 1.0 ; equal-weighted: (2-1+0+1)/4 = 0.5
    assert b['cap_weighted_chg'] == 1.0
    assert b['equal_weighted_chg'] == 0.5
    assert [r['ticker'] for r in b['leaders']][:2] == ['A', 'D']
    assert b['laggards'][0]['ticker'] == 'B'


def test_breadth_with_no_trend_fields_reports_none_not_zero():
    b = M.breadth([_row('A', 10, 1.0), _row('B', 10, -1.0)])
    assert b['above_50d'] == {'above': 0, 'of': 0, 'pct': None}
    assert b['near_52w_high'] == {'count': 0, 'of': 0}


def _series(closes, end=date(2026, 3, 20)):
    """closes on consecutive weekdays ending at `end`."""
    days, d = [], end
    while len(days) < len(closes):
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return list(zip(reversed(days), closes))


def test_returns_by_sessions_and_ytd():
    closes = [100 + i for i in range(80)]          # 100 .. 179
    pts = _series(closes)
    r = M.returns(pts)
    assert r['1D'] == round((179 / 178 - 1) * 100, 2)
    assert r['1W'] == round((179 / 174 - 1) * 100, 2)
    assert r['1M'] == round((179 / 158 - 1) * 100, 2)
    assert r['3M'] == round((179 / 116 - 1) * 100, 2)
    last_2025 = [c for d, c in pts if d.year == 2025][-1]
    assert r['YTD'] == round((179 / last_2025 - 1) * 100, 2)


def test_returns_short_history_is_none():
    r = M.returns(_series([10, 11, 12]))
    assert r['1D'] is not None and r['1M'] is None and r['3M'] is None and r['YTD'] is None


def test_sector_table_relative_to_benchmark():
    spy = _series([100] * 70 + [110])                    # +10% on the day
    xlk = _series([100] * 70 + [115])                    # +15%
    t = M.sector_table({'SPY': spy, 'XLK': xlk})
    tech = next(s for s in t['sectors'] if s['etf'] == 'XLK')
    assert tech['returns']['1D'] == 15.0 and tech['vs_benchmark']['1D'] == 5.0
    energy = next(s for s in t['sectors'] if s['etf'] == 'XLE')
    assert energy['returns']['1D'] is None and energy['vs_benchmark']['1D'] is None


def test_snapshot_lists_everything_and_marks_gaps():
    rows = M.snapshot({'^TNX': {'price': 4.25, 'prev_close': 4.31, 'chg': -1.39},
                       '^GSPC': {'price': 5000, 'prev_close': 4950, 'chg': 1.01}})
    assert len(rows) == len(M.SNAPSHOT)
    tnx = next(r for r in rows if r['symbol'] == '^TNX')
    assert tnx['chg_bp'] == -6.0 and 'chg' not in tnx          # yields move in basis points
    gold = next(r for r in rows if r['symbol'] == 'GC=F')
    assert gold['status'] == 'unavailable' and gold['price'] is None
