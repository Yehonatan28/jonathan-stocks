"""Earnings, economic-event and dividend calendars from Nasdaq's public calendar service.

Method (shown to the user as written here):
- One request per day and calendar to api.nasdaq.com, cached for six hours.
- Earnings: the reporting date and session (before the open, after the close, or not given),
  the consensus EPS estimate and how many analysts it averages, and last year's EPS for the same
  quarter. The estimate is a forecast by analysts, not a result, and is labelled so.
- Economic events: time (GMT), country, event, and the actual, consensus and previous values as
  the source publishes them (often text with units, such as "2.1%" or "215K").
- Dividends: ex-dividend, record and payment dates, the amount per share and the annual rate.
- Rows the source does not fill are left empty. Nothing is estimated here.
"""
import re
from datetime import date, timedelta

import requests

BASE = 'https://api.nasdaq.com/api/calendar/{kind}?date={day}'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Origin': 'https://www.nasdaq.com', 'Referer': 'https://www.nasdaq.com/',
}
KINDS = ('earnings', 'economicevents', 'dividends')
SESSION = {'time-pre-market': 'before the open', 'time-after-hours': 'after the close', 'time-not-supplied': 'time not given'}


class Unavailable(Exception):
    pass


def _num(s):
    """'$1.23' -> 1.23, '($0.40)' -> -0.4, '$3,412,000,000' -> 3412000000.0, 'N/A' or '' -> None."""
    if s is None:
        return None
    t = str(s).strip()
    if not t or t.upper() in ('N/A', 'NA', '--', '-'):
        return None
    neg = t.startswith('(') and t.endswith(')')
    t = re.sub(r'[^0-9.\-]', '', t)
    try:
        v = float(t)
    except ValueError:
        return None
    return -abs(v) if neg else v


def _rows(payload, kind):
    d = (payload or {}).get('data') or {}
    if kind == 'dividends':
        d = d.get('calendar') or {}
    return d.get('rows') or []


def parse(kind, payload, day):
    out = []
    for r in _rows(payload, kind):
        if kind == 'earnings':
            sym = (r.get('symbol') or '').strip().upper()
            if not sym:
                continue
            out.append({'date': day, 'symbol': sym, 'name': (r.get('name') or '').strip(),
                        'session': SESSION.get(r.get('time'), 'time not given'),
                        'market_cap': _num(r.get('marketCap')), 'quarter': (r.get('fiscalQuarterEnding') or '').strip() or None,
                        'eps_estimate': _num(r.get('epsForecast')), 'estimates': int(_num(r.get('noOfEsts')) or 0) or None,
                        'eps_last_year': _num(r.get('lastYearEPS')), 'last_year_date': (r.get('lastYearRptDt') or '').strip() or None})
        elif kind == 'economicevents':
            name = (r.get('eventName') or '').strip()
            if not name:
                continue
            clean = lambda v: (str(v).strip() or None) if v not in (None, '&nbsp;') else None
            out.append({'date': day, 'time_gmt': clean(r.get('gmt')), 'country': clean(r.get('country')), 'event': name,
                        'actual': clean(r.get('actual')), 'consensus': clean(r.get('consensus')), 'previous': clean(r.get('previous'))})
        else:
            sym = (r.get('symbol') or '').strip().upper()
            if not sym:
                continue
            out.append({'date': day, 'symbol': sym, 'name': (r.get('companyName') or '').strip(),
                        'ex_date': r.get('dividend_Ex_Date'), 'record_date': r.get('record_Date'),
                        'pay_date': r.get('payment_Date'), 'amount': _num(r.get('dividend_Rate')),
                        'annual': _num(r.get('indicated_Annual_Dividend'))})
    if kind == 'earnings':
        out.sort(key=lambda x: -(x['market_cap'] or 0))
    return out


def fetch(kind, day, get=None):
    """Raises Unavailable when the source does not answer."""
    get = get or requests.get
    try:
        r = get(BASE.format(kind=kind, day=day.isoformat()), headers=HEADERS, timeout=12)
    except requests.RequestException as exc:
        raise Unavailable(type(exc).__name__) from exc
    if not r.ok:
        raise Unavailable(f'HTTP {r.status_code}')
    try:
        return parse(kind, r.json(), day.isoformat())
    except ValueError as exc:
        raise Unavailable('not JSON') from exc


def trading_days(start, n):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out
