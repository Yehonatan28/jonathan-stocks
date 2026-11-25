"""Where every dataset comes from, how fresh it is, and when this server retrieved it.

Each data route answers with four headers, so the page can label every screen without the
response bodies changing shape:

    X-Data-Set        a short id (quotes, chart, news, ...)
    X-Data-Source     who publishes the numbers
    X-Data-Status     delayed | eod | unavailable   (nothing here is a real-time feed)
    X-Data-Retrieved  when this server fetched it from the source (ISO 8601, UTC); a cached
                      answer carries the time of the original fetch, not the time of the request

The caches in app.py, market.py and news.py call note() with the time a hit was first fetched;
the oldest time seen while answering a request is the one reported.
"""
import time
from datetime import datetime, timezone

# (path prefix, id, label, source, status). The first matching prefix wins.
DATASETS = [
    ('/api/quote_full', 'quotes', 'Quotes', 'Yahoo Finance', 'delayed'),
    ('/api/quotes', 'quotes', 'Quotes', 'Yahoo Finance', 'delayed'),
    ('/api/heatmap', 'heatmap', 'Heatmap', 'Yahoo Finance quotes', 'delayed'),
    ('/api/treemap', 'treemap', 'Sector map', 'Yahoo Finance quotes', 'delayed'),
    ('/api/gaps', 'gaps', 'Gap scan', 'Yahoo Finance daily bars', 'delayed'),
    ('/api/chart', 'chart', 'Price history', 'Yahoo Finance', 'delayed'),
    ('/api/stock', 'stock', 'Trend analysis', 'Yahoo Finance daily bars', 'eod'),
    ('/api/engine', 'engine', 'Risk engine', 'Yahoo Finance daily bars', 'eod'),
    ('/api/feargreed', 'feargreed', 'Fear & Greed', 'CNN Business', 'delayed'),
    ('/api/earnings', 'earnings', 'Earnings', 'Yahoo Finance', 'eod'),
    ('/api/analyst', 'analyst', 'Analyst estimates', 'Yahoo Finance', 'eod'),
    ('/api/profile', 'profile', 'Company profile', 'Yahoo Finance', 'eod'),
    ('/api/market/breadth', 'breadth', 'Market breadth', 'Yahoo Finance quotes', 'delayed'),
    ('/api/market/sectors', 'sectors', 'Sector performance', 'Yahoo Finance daily bars (SPDR sector funds)', 'eod'),
    ('/api/market/snapshot', 'snapshot', 'Cross-asset snapshot', 'Yahoo Finance', 'delayed'),
    ('/api/scan', 'scan', 'Stock scanner', 'Yahoo Finance quotes', 'delayed'),
    ('/api/company', 'company', 'Company financials', 'SEC EDGAR filings (10-K, 10-Q)', 'reported'),
    ('/api/ledger', 'ledger', 'Portfolio valuation', 'Your transactions, valued at Yahoo Finance prices', 'delayed'),
    ('/api/performance', 'performance', 'Portfolio performance', 'Your transactions, Yahoo Finance daily closes', 'eod'),
    ('/api/risk/review', 'risk', 'Portfolio risk', 'Your holdings, Yahoo Finance daily bars', 'eod'),
    ('/api/lab', 'lab', 'Strategy backtest', 'Yahoo Finance daily bars', 'eod'),
    ('/api/relative', 'relative', 'Comparison', 'Yahoo Finance daily closes', 'eod'),
    ('/api/calendar', 'calendar', 'Calendar', 'Nasdaq calendars', 'delayed'),
    ('/api/alerts/evaluate', 'alerts', 'Alerts', 'Yahoo Finance daily bars, Nasdaq earnings calendar', 'delayed'),
    ('/api/digest', 'digest', 'Your names today', 'Yahoo Finance daily bars, Nasdaq earnings calendar', 'delayed'),
    ('/api/assistant', 'assistant', 'Research assistant', 'Platform data, written by Google Gemini', 'delayed'),
    ('/api/news', 'news', 'News', 'Publisher RSS feeds', 'delayed'),
    ('/api/search', 'search', 'Symbol search', 'Yahoo Finance', 'delayed'),
]

STATUS_TEXT = {
    'delayed': 'Delayed: quotes may lag the exchange by 15 minutes or more',
    'eod': 'End of day: computed from daily closing bars',
    'reported': 'As reported: figures from the company\'s filings with the SEC, for the periods shown',
    'unavailable': 'Unavailable: the source did not answer; nothing is shown in its place',
}


def match(path):
    for prefix, ds, label, source, status in DATASETS:
        if path == prefix or path.startswith(prefix + '/') or path.startswith(prefix + '?'):
            return {'id': ds, 'label': label, 'source': source, 'status': status}
    return None


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def note(fetched_at):
    """Record that part of this answer came from a cache filled at fetched_at."""
    try:
        from flask import g, has_request_context
    except ImportError:          # pragma: no cover
        return
    if has_request_context():
        prev = g.get('data_as_of')
        g.data_as_of = fetched_at if prev is None else min(prev, fetched_at)


def headers(path, status_code, body_json):
    ds = match(path)
    # a 4xx is about the request (an unknown symbol, a bad parameter), not about the source
    if not ds or 400 <= status_code < 500:
        return {}
    try:
        from flask import g
        as_of = g.get('data_as_of') or time.time()
    except Exception:            # noqa: BLE001
        as_of = time.time()
    status = ds['status']
    failed = status_code >= 500 or (
        isinstance(body_json, dict) and (body_json.get('ok') is False or (body_json.get('error') and len(body_json) <= 2)))
    if failed:
        status = 'unavailable'
    return {'X-Data-Set': ds['id'], 'X-Data-Source': ds['source'], 'X-Data-Status': status,
            'X-Data-Retrieved': iso(as_of)}


def catalogue():
    seen, out = set(), []
    for _p, ds, label, source, status in DATASETS:
        if ds in seen:
            continue
        seen.add(ds)
        out.append({'id': ds, 'label': label, 'source': source, 'status': status, 'meaning': STATUS_TEXT[status]})
    return out
