"""Calendar parsing on payloads shaped like the source's."""
from datetime import date

import calendars as C


def test_numbers():
    assert C._num('$1.23') == 1.23 and C._num('($0.40)') == -0.4 and C._num('$3,412,000,000') == 3412000000.0
    assert C._num('N/A') is None and C._num('') is None and C._num(None) is None


def test_earnings_sorted_by_cap_and_labelled():
    p = {'data': {'rows': [
        {'time': 'time-after-hours', 'symbol': 'small', 'name': 'Small Co', 'marketCap': '$1,000,000', 'fiscalQuarterEnding': 'Oct/2026',
         'epsForecast': '($0.05)', 'noOfEsts': '2', 'lastYearRptDt': '11/30/2025', 'lastYearEPS': '($0.10)'},
        {'time': 'time-pre-market', 'symbol': 'BIG', 'name': 'Big Co', 'marketCap': '$900,000,000,000', 'fiscalQuarterEnding': 'Oct/2026',
         'epsForecast': '$2.10', 'noOfEsts': '30', 'lastYearRptDt': '12/01/2025', 'lastYearEPS': '$1.90'},
        {'symbol': '', 'name': 'blank'}]}}
    rows = C.parse('earnings', p, '2026-12-01')
    assert [r['symbol'] for r in rows] == ['BIG', 'SMALL']
    assert rows[0]['session'] == 'before the open' and rows[0]['eps_estimate'] == 2.1 and rows[0]['estimates'] == 30
    assert rows[1]['eps_estimate'] == -0.05 and rows[1]['session'] == 'after the close'


def test_economic_and_dividends():
    e = C.parse('economicevents', {'data': {'rows': [{'gmt': '13:30', 'country': 'United States', 'eventName': 'GDP (QoQ)',
                                                       'actual': '&nbsp;', 'consensus': '2.1%', 'previous': '1.8%'}]}}, '2026-12-01')
    assert e == [{'date': '2026-12-01', 'time_gmt': '13:30', 'country': 'United States', 'event': 'GDP (QoQ)',
                  'actual': None, 'consensus': '2.1%', 'previous': '1.8%'}]
    d = C.parse('dividends', {'data': {'calendar': {'rows': [{'symbol': 'ko', 'companyName': 'Coca-Cola', 'dividend_Ex_Date': '12/01/2026',
                 'payment_Date': '12/15/2026', 'record_Date': '12/01/2026', 'dividend_Rate': 0.51, 'indicated_Annual_Dividend': 2.04}]}}}, '2026-12-01')
    assert d[0]['symbol'] == 'KO' and d[0]['amount'] == 0.51 and d[0]['annual'] == 2.04


def test_fetch_errors_and_days():
    class R:
        ok, status_code = False, 403
    try:
        C.fetch('earnings', date(2026, 12, 1), get=lambda *a, **k: R())
    except C.Unavailable as exc:
        assert 'HTTP 403' in str(exc)
    else:
        raise AssertionError
    assert C.trading_days(date(2026, 11, 27), 3) == [date(2026, 11, 27), date(2026, 11, 30), date(2026, 12, 1)]
