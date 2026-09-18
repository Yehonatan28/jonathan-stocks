"""אגרגטור חדשות פיננסיות מפידי RSS.

Yahoo's search endpoint rate-limits and silently returns nothing, which is why
the news tab kept coming up empty. RSS is the right transport instead: it is
published for machine consumption, needs no key, and every outlet has one.

The design assumption is that individual feeds break - they move, they rename,
they block a user agent, they return HTML on a bad day. So every feed is
fetched independently, a failure is recorded rather than raised, and the caller
still gets whatever the healthy feeds returned. `source_health()` exists to
report which ones are actually alive from wherever this is deployed.

parse_feed() is pure and takes bytes, so the whole parsing surface is testable
without a network.
"""

import html
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import requests

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
    'Accept': 'application/rss+xml, application/xml, text/xml, */*',
}

# (key, display name, url, language, scope)
GLOBAL_FEEDS = [
    ('cnbc-markets', 'CNBC', 'https://www.cnbc.com/id/20910258/device/rss/rss.html', 'en', 'us'),
    ('cnbc-top', 'CNBC', 'https://www.cnbc.com/id/100003114/device/rss/rss.html', 'en', 'us'),
    ('marketwatch', 'MarketWatch', 'https://feeds.content.dowjones.io/public/rss/mw_topstories', 'en', 'us'),
    ('investing', 'Investing.com', 'https://www.investing.com/rss/news_25.rss', 'en', 'us'),
    ('yahoo-market', 'Yahoo Finance', 'https://finance.yahoo.com/news/rssindex', 'en', 'us'),
    ('ft-markets', 'Financial Times', 'https://www.ft.com/markets?format=rss', 'en', 'us'),
]

# Hebrew outlets: this is an Israeli portfolio, and TA names are barely covered
# in the English press.
ISRAEL_FEEDS = [
    ('globes-capital', 'גלובס', 'https://www.globes.co.il/webservice/rss/rssfeeder.asmx?iID=2', 'he', 'il'),
    ('globes-main', 'גלובס', 'https://www.globes.co.il/webservice/rss/rssfeeder.asmx?iID=1725', 'he', 'il'),
    ('calcalist', 'כלכליסט', 'https://www.calcalist.co.il/GeneralRSS/0,16335,L-8,00.xml', 'he', 'il'),
    ('themarker', 'דה־מרקר', 'https://www.themarker.com/srv/themarker---markets', 'he', 'il'),
    ('bizportal', 'ביזפורטל', 'https://www.bizportal.co.il/rss', 'he', 'il'),
]

ALL_FEEDS = GLOBAL_FEEDS + ISRAEL_FEEDS


def ticker_feeds(ticker):
    """Per-symbol feeds. Yahoo's headline RSS is separate from its search API
    and has been the more dependable of the two."""
    t = ticker.strip().upper()
    if not re.fullmatch(r'[A-Z0-9.\-^]{1,12}', t):
        return []
    base = t.split('.')[0]
    return [
        (f'yahoo-{t}', 'Yahoo Finance',
         f'https://feeds.finance.yahoo.com/rss/2.0/headline?s={t}&region=US&lang=en-US', 'en', 'ticker'),
        (f'nasdaq-{base}', 'Nasdaq',
         f'https://www.nasdaq.com/feed/rssoutbound?symbol={base}', 'en', 'ticker'),
        (f'sa-{base}', 'Seeking Alpha',
         f'https://seekingalpha.com/api/sa/combined/{base}.xml', 'en', 'ticker'),
    ]


# ------------------------------------------------------------------ parse ---

_TAG_RE = re.compile(r'<[^>]+>')
_WS_RE = re.compile(r'\s+')


def _clean(text, limit=320):
    """Feed summaries arrive as HTML fragments; reduce to plain text."""
    if not text:
        return ''
    text = _TAG_RE.sub(' ', text)
    text = html.unescape(text)
    text = _WS_RE.sub(' ', text)
    # a removed inline tag leaves "word ." - close that gap back up
    text = re.sub(r'\s+([,.;:!?%)\]])', r'\1', text)
    text = re.sub(r'([(\[])\s+', r'\1', text).strip()
    return text[:limit].rstrip() + ('…' if len(text) > limit else '')


def _strip_ns(tag):
    return tag.split('}', 1)[1] if '}' in tag else tag


def _parse_date(value):
    """Feeds disagree on date format; return a unix timestamp or None."""
    if not value:
        return None
    value = value.strip()
    try:                                  # RFC 822, the RSS 2.0 convention
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except (TypeError, ValueError, IndexError):
        pass
    try:                                  # ISO 8601, the Atom convention
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except ValueError:
        return None


def _first(node, names):
    """First non-empty child text among `names`, ignoring XML namespaces."""
    for child in node:
        if _strip_ns(child.tag) in names:
            if child.text and child.text.strip():
                return child.text.strip()
    return None


def _link_of(node):
    """RSS puts the url in <link> text; Atom puts it in a link's href."""
    for child in node:
        if _strip_ns(child.tag) != 'link':
            continue
        if child.text and child.text.strip():
            return child.text.strip()
        href = child.attrib.get('href')
        rel = child.attrib.get('rel', 'alternate')
        if href and rel == 'alternate':
            return href
    return None


def parse_feed(data):
    """RSS 2.0 or Atom bytes -> list of item dicts. Never raises on bad XML."""
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError:
        return []

    nodes = [n for n in root.iter() if _strip_ns(n.tag) in ('item', 'entry')]
    items = []
    for n in nodes:
        title = _clean(_first(n, ('title',)), 220)
        link = _link_of(n)
        if not title or not link:
            continue
        ts = _parse_date(_first(n, ('pubDate', 'published', 'updated', 'date')))
        items.append({
            'title': title,
            'link': link,
            'summary': _clean(_first(n, ('description', 'summary', 'content'))),
            'time': ts,
        })
    return items


# ------------------------------------------------------------------ fetch ---

_CACHE = {}
FEED_TTL = 420


def fetch_feed(feed, timeout=9):
    """One feed -> (items, error). An error is returned, never raised, so one
    dead outlet cannot take the news tab down with it."""
    key, source, url, lang, scope = feed
    hit = _CACHE.get(key)
    if hit and hit[0] > time.time():
        return hit[1], None
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if not r.ok:
            return [], f'HTTP {r.status_code}'
        items = parse_feed(r.content)
        if not items:
            return [], 'no items parsed'
        for it in items:
            it['source'] = source
            it['lang'] = lang
            it['scope'] = scope
        _CACHE[key] = (time.time() + FEED_TTL, items)
        return items, None
    except requests.Timeout:
        return [], 'timeout'
    except Exception as e:
        return [], type(e).__name__


def _dedupe(items):
    """The wires syndicate the same story; keep the first of each headline."""
    seen, out = set(), []
    for it in items:
        norm = re.sub(r'[^\w֐-׿]+', '', it['title'].lower())[:70]
        if norm in seen:
            continue
        seen.add(norm)
        out.append(it)
    return out


def get_news(ticker=None, scope='all', limit=40, extra_tickers=None):
    """Merged, deduped, newest-first headlines.

    scope: 'all' | 'us' | 'il'. A ticker adds its per-symbol feeds on top.
    """
    feeds = []
    if scope in ('all', 'us'):
        feeds += GLOBAL_FEEDS
    if scope in ('all', 'il'):
        feeds += ISRAEL_FEEDS
    if ticker:
        feeds = ticker_feeds(ticker) + feeds
    for t in (extra_tickers or [])[:6]:
        feeds = ticker_feeds(t) + feeds

    if not feeds:
        return {'items': [], 'failed': []}

    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(fetch_feed, feeds))

    items, failed = [], []
    for feed, (got, err) in zip(feeds, results):
        if err:
            failed.append({'source': feed[1], 'key': feed[0], 'error': err})
        items.extend(got)

    items = _dedupe(items)
    # undated items sink rather than floating to the top on a 0 timestamp
    items.sort(key=lambda i: i['time'] or 0, reverse=True)
    return {'items': items[:limit], 'failed': failed}


def source_health(ticker='AAPL'):
    """Which feeds actually answer from this deployment.

    The sandbox this was written in blocks every outlet, so this is how the
    list gets verified against the real world instead of by assumption.
    """
    feeds = ALL_FEEDS + ticker_feeds(ticker)
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda f: fetch_feed(f, timeout=12), feeds))
    out = []
    for (key, source, url, lang, scope), (items, err) in zip(feeds, results):
        newest = max((i['time'] or 0 for i in items), default=0)
        out.append({
            'key': key, 'source': source, 'scope': scope, 'lang': lang,
            'url': url,
            'ok': not err, 'error': err,
            'items': len(items),
            'newest': newest or None,
        })
    return {'sources': out,
            'alive': sum(1 for s in out if s['ok']),
            'total': len(out)}
