"""Where every dataset comes from, how fresh it is, and when this server retrieved it.

Each data route answers with four headers, so the page can label every screen without the
response bodies changing shape:

    X-Data-Set        a short id (quotes, chart, news, ...)
    X-Data-Source     who publishes the numbers
    X-Data-Status     delayed | eod | reported | estimated | published | scheduled | derived |
                      reference | unavailable   (nothing here is a real-time feed)
    X-Data-Observed   when the data itself is from, where the answer says so (the last session's date,
                      the latest filing period): not the same as when it was retrieved
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
    ('/api/feargreed', 'feargreed', 'Fear & Greed', 'CNN Business', 'published'),
    ('/api/earnings', 'earnings', 'Earnings', 'Yahoo Finance', 'scheduled'),
    ('/api/analyst', 'analyst', 'Analyst estimates', 'Yahoo Finance', 'estimated'),
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
    ('/api/calendar', 'calendar', 'Calendar', 'Nasdaq calendars', 'scheduled'),
    ('/api/alerts/evaluate', 'alerts', 'Alerts', 'Yahoo Finance daily bars, Nasdaq earnings calendar', 'delayed'),
    ('/api/digest', 'digest', 'Your names today', 'Yahoo Finance daily bars, Nasdaq earnings calendar', 'delayed'),
    ('/api/assistant', 'assistant', 'Research assistant', 'Platform data, written by Google Gemini', 'derived'),
    ('/api/news', 'news', 'News', 'Publisher RSS feeds', 'published'),
    ('/api/search', 'search', 'Symbol search', 'Index lists, SEC names, Yahoo Finance', 'reference'),
]

STATUS_TEXT = {
    'delayed': 'Delayed: quotes may lag the exchange by 15 minutes or more',
    'eod': 'End of day: computed from daily closing bars',
    'reported': 'As reported: figures from the company\'s filings with the SEC, for the periods shown',
    'estimated': 'Estimated: forecasts by analysts or a marked estimate, not reported results',
    'published': 'As published: headlines or an index as the publisher released them; not price quotes',
    'scheduled': 'Schedule: dates as announced; consensus figures in it are forecasts',
    'derived': 'Written from this site\'s data: each number is checked against that data',
    'reference': 'Reference list: symbols and names, no prices',
    'unavailable': 'Unavailable: the source did not answer; nothing is shown in its place',
}


def observed(body):
    """The date the data is from, when the answer carries one: 'as_of' or 'observed_at' at the top,
    in a list of rows, or in its 'sectors' / 'stocks' rows. The oldest date wins, so a mixed answer
    never looks fresher than its stalest part."""
    vals = []

    def take(d):
        if isinstance(d, dict):
            for k in ('observed_at', 'as_of'):
                v = d.get(k)
                if isinstance(v, str) and len(v) >= 10:
                    vals.append(v)
    if isinstance(body, list):
        for r in body[:200]:
            take(r)
    elif isinstance(body, dict):
        take(body)
        for k in ('sectors', 'stocks', 'rows', 'instruments'):
            if isinstance(body.get(k), list):
                for r in body[k][:600]:
                    take(r)
    return min(vals) if vals else None


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
    out = {'X-Data-Set': ds['id'], 'X-Data-Source': ds['source'], 'X-Data-Status': status,
           'X-Data-Retrieved': iso(as_of)}
    obs = observed(body_json) if not failed else None
    if obs:
        out['X-Data-Observed'] = obs[:20]
    return out


def catalogue():
    seen, out = set(), []
    for _p, ds, label, source, status in DATASETS:
        if ds in seen:
            continue
        seen.add(ds)
        out.append({'id': ds, 'label': label, 'source': source, 'status': status, 'meaning': STATUS_TEXT[status]})
    return out
