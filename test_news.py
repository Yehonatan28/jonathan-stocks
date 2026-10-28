"""Tests for the RSS aggregator.

Every feed the app uses is blocked from the sandbox this was written in, so the
parser is exercised against fixtures that reproduce what real outlets actually
send - CDATA, namespaces, Atom, broken dates, HTML in summaries, malformed XML:
    python3 test_news.py
"""

import news

CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


RSS = b'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Example Markets</title>
  <item>
    <title>Nvidia beats on earnings</title>
    <link>https://example.com/a</link>
    <pubDate>Tue, 16 Sep 2026 13:45:00 GMT</pubDate>
    <description>&lt;p&gt;Shares &lt;b&gt;jumped&lt;/b&gt; 6%.&lt;/p&gt;</description>
  </item>
  <item>
    <title><![CDATA[Fed holds rates & signals patience]]></title>
    <link>https://example.com/b</link>
    <pubDate>Mon, 15 Sep 2026 09:00:00 +0000</pubDate>
    <description><![CDATA[<div>Powell said <i>"we can wait"</i>.</div>]]></description>
  </item>
</channel></rss>'''

ATOM = b'''<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Example Atom</title>
  <entry>
    <title>Apple unveils new chip</title>
    <link rel="alternate" href="https://example.com/atom-1"/>
    <link rel="edit" href="https://example.com/edit"/>
    <updated>2026-09-17T08:30:00Z</updated>
    <summary type="html">&lt;p&gt;Faster and cooler.&lt;/p&gt;</summary>
  </entry>
</feed>'''

HEBREW = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>טבע מזנקת 8% אחרי אישור FDA</title>
    <link>https://example.co.il/1</link>
    <pubDate>Wed, 17 Sep 2026 07:15:00 +0300</pubDate>
    <description>המניה עלתה בחדות במסחר בתל אביב.</description>
  </item>
</channel></rss>""".encode('utf-8')


@check('parse: RSS 2.0 items, dates and HTML-stripped summaries')
def t_rss():
    items = news.parse_feed(RSS)
    assert len(items) == 2, len(items)
    a = items[0]
    assert a['title'] == 'Nvidia beats on earnings'
    assert a['link'] == 'https://example.com/a'
    assert a['time'] == 1789566300, a['time']
    assert a['summary'] == 'Shares jumped 6%.', repr(a['summary'])
    assert '<' not in a['summary'] and '&lt;' not in a['summary']


@check('parse: CDATA titles and entities survive intact')
def t_cdata():
    b = news.parse_feed(RSS)[1]
    assert b['title'] == 'Fed holds rates & signals patience', repr(b['title'])
    assert b['summary'] == 'Powell said "we can wait".', repr(b['summary'])


@check('parse: Atom entries, picking the alternate link not the edit link')
def t_atom():
    items = news.parse_feed(ATOM)
    assert len(items) == 1
    it = items[0]
    assert it['link'] == 'https://example.com/atom-1', it['link']
    assert it['title'] == 'Apple unveils new chip'
    assert it['time'] == 1789633800, it['time']
    assert it['summary'] == 'Faster and cooler.'


@check('parse: Hebrew headlines and a non-UTC offset')
def t_hebrew():
    it = news.parse_feed(HEBREW)[0]
    assert it['title'].startswith('טבע מזנקת'), it['title']
    assert it['time'] == 1789618500, it['time']   # 07:15 +03:00 == 04:15 UTC


@check('parse: malformed XML returns nothing instead of raising')
def t_broken():
    assert news.parse_feed(b'<rss><channel><item>oops') == []
    assert news.parse_feed(b'') == []
    assert news.parse_feed(b'<html><body>blocked</body></html>') == []


@check('parse: items missing a title or link are dropped')
def t_incomplete():
    feed = b'''<rss><channel>
      <item><title>No link here</title></item>
      <item><link>https://example.com/x</link></item>
      <item><title>Good</title><link>https://example.com/ok</link></item>
    </channel></rss>'''
    items = news.parse_feed(feed)
    assert len(items) == 1 and items[0]['title'] == 'Good', items


@check('parse: an unparsable date leaves time null rather than guessing')
def t_bad_date():
    feed = b'''<rss><channel><item>
      <title>T</title><link>https://e.com/1</link><pubDate>yesterday-ish</pubDate>
    </item></channel></rss>'''
    assert news.parse_feed(feed)[0]['time'] is None


@check('dedupe: the same story from three wires collapses to one')
def t_dedupe():
    items = [
        {'title': 'Fed holds rates steady', 'time': 3},
        {'title': 'FED HOLDS RATES STEADY!', 'time': 2},
        {'title': 'Fed  holds   rates steady.', 'time': 1},
        {'title': 'Apple ships a new chip', 'time': 4},
    ]
    out = news._dedupe(items)
    assert len(out) == 2, [i['title'] for i in out]
    assert out[0]['time'] == 3, 'the first occurrence should win'


@check('dedupe: Hebrew headlines are not collapsed into one another')
def t_dedupe_hebrew():
    items = [{'title': 'טבע מזנקת אחרי אישור', 'time': 2},
             {'title': 'בנק לאומי מדווח על רווח', 'time': 1}]
    assert len(news._dedupe(items)) == 2, 'Hebrew letters must survive normalising'


@check('ticker feeds: symbols are validated before reaching a URL')
def t_ticker_validation():
    assert news.ticker_feeds('AAPL'), 'a plain symbol should produce feeds'
    assert news.ticker_feeds('TEVA.TA'), 'a TASE symbol should produce feeds'
    for bad in ('', '   ', 'A B', 'x/../y', 'a' * 20, '<script>'):
        assert news.ticker_feeds(bad) == [], f'{bad!r} should be rejected'
    urls = [f[2] for f in news.ticker_feeds('TEVA.TA')]
    assert any('s=TEVA.TA' in u for u in urls), urls
    assert any('symbol=TEVA' in u for u in urls), 'the suffix is stripped for US feeds'


@check('fetch: a failing feed yields an error rather than raising')
def t_fetch_failure():
    feed = ('dead', 'Nowhere', 'https://127.0.0.1:1/nope.xml', 'en', 'us')
    items, err = news.fetch_feed(feed, timeout=2)
    assert items == [] and err, (items, err)


@check('get_news: one dead feed does not sink the healthy ones')
def t_resilient(monkey=None):
    good = [{'title': 'Alive', 'link': 'https://e.com/1', 'time': 100,
             'summary': '', 'source': 'X', 'lang': 'en', 'scope': 'us'}]
    orig = news.fetch_feed
    try:
        news.fetch_feed = lambda f, timeout=9: (
            (good, None) if f[0].startswith('cnbc') else ([], 'HTTP 403'))
        out = news.get_news(scope='us')
        assert out['items'], 'healthy feeds should still deliver'
        assert out['failed'], 'the dead ones should be reported'
        assert all(f['error'] for f in out['failed'])
    finally:
        news.fetch_feed = orig


@check('get_news: results are newest first and undated items sink')
def t_ordering():
    rows = [
        ('a', 'A', 'u', 'en', 'us'),
    ]
    orig, feeds = news.fetch_feed, news.GLOBAL_FEEDS
    try:
        news.GLOBAL_FEEDS = rows
        news.fetch_feed = lambda f, timeout=9: ([
            {'title': 'old', 'link': 'l1', 'time': 100, 'summary': '', 'source': 'A', 'lang': 'en', 'scope': 'us'},
            {'title': 'undated', 'link': 'l2', 'time': None, 'summary': '', 'source': 'A', 'lang': 'en', 'scope': 'us'},
            {'title': 'new', 'link': 'l3', 'time': 900, 'summary': '', 'source': 'A', 'lang': 'en', 'scope': 'us'},
        ], None)
        titles = [i['title'] for i in news.get_news(scope='us')['items']]
        assert titles == ['new', 'old', 'undated'], titles
    finally:
        news.fetch_feed, news.GLOBAL_FEEDS = orig, feeds


@check('get_news: scope selects the right set of outlets')
def t_scope():
    seen = []
    orig = news.fetch_feed
    try:
        news.fetch_feed = lambda f, timeout=9: (seen.append(f[4]) or ([], 'skip'))
        seen.clear(); news.get_news(scope='il'); assert set(seen) == {'il'}, seen
        seen.clear(); news.get_news(scope='us'); assert set(seen) == {'us'}, seen
        seen.clear(); news.get_news(scope='all'); assert {'us', 'il'} <= set(seen), seen
        seen.clear(); news.get_news(ticker='AAPL', scope='us')
        assert 'ticker' in seen, seen
    finally:
        news.fetch_feed = orig


IMAGES = b'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel>
  <item>
    <title>Media RSS thumbnail, widest wins</title>
    <link>https://example.com/i1</link>
    <media:thumbnail url="https://img.example.com/small.jpg" width="80"/>
    <media:thumbnail url="https://img.example.com/wide.jpg" width="900"/>
    <media:thumbnail url="https://img.example.com/mid.jpg" width="400"/>
  </item>
  <item>
    <title>Enclosure image</title>
    <link>https://example.com/i2</link>
    <enclosure url="https://img.example.com/enc.jpg" type="image/jpeg" length="21"/>
  </item>
  <item>
    <title>Image inside the description</title>
    <link>https://example.com/i3</link>
    <description>&lt;p&gt;&lt;img src="https://img.example.com/inline.jpg"/&gt;Story text.&lt;/p&gt;</description>
  </item>
  <item>
    <title>Tracking pixel only</title>
    <link>https://example.com/i4</link>
    <description>&lt;img src="https://stats.example.com/beacon.gif?1x1"/&gt;Text.</description>
  </item>
</channel></rss>'''


@check('imagery: thumbnails, enclosures and inline images are found')
def t_images():
    items = news.parse_feed(IMAGES)
    by = {i['title']: i.get('image') for i in items}
    assert by['Media RSS thumbnail, widest wins'] == 'https://img.example.com/wide.jpg', by
    assert by['Enclosure image'] == 'https://img.example.com/enc.jpg', by
    assert by['Image inside the description'] == 'https://img.example.com/inline.jpg', by


@check('imagery: tracking pixels are not treated as article art')
def t_no_pixels():
    items = news.parse_feed(IMAGES)
    px = [i for i in items if i['title'] == 'Tracking pixel only'][0]
    assert px.get('image') is None, px.get('image')


@check('imagery: a story with no picture reports none rather than guessing')
def t_no_image():
    items = news.parse_feed(RSS)
    assert all(i.get('image') is None for i in items), items


@check('classify: topic comes from the headline')
def t_topic():
    cases = [('Fed holds rates steady', 'rates'),
             ('CPI inflation cools to 2.4%', 'inflation'),
             ('Payrolls beat as unemployment falls', 'jobs'),
             ('Oil slips as OPEC lifts output', 'energy'),
             ('Bitcoin tops $90,000', 'crypto'),
             ('Chip demand lifts semiconductor names', 'chips'),
             ('Apple reports fourth-quarter earnings', 'earnings')]
    for title, want in cases:
        got = news.classify(title)['topic']
        assert got == want, f'{title!r} -> {got}, wanted {want}'


@check('classify: direction is read from the verb, not assumed')
def t_direction():
    assert news.classify('Nvidia surges on strong guidance')['direction'] == 'up'
    assert news.classify('Tesla plunges after a profit warning')['direction'] == 'down'
    # Nothing directional in the wording, and nothing invented either
    assert news.classify('Fed to meet next week')['direction'] == 'flat'


SYMS = {'NVDA', 'TSLA', 'AAPL'}
NAMES = {'nvidia': 'NVDA', 'tesla': 'TSLA', 'apple inc.': 'AAPL'}


@check('classify: a company in the headline resolves to its symbol')
def t_ticker():
    assert news.classify('Nvidia beats on earnings', '', SYMS, NAMES)['ticker'] == 'NVDA'
    assert news.classify('NVDA upgraded at Morgan Stanley', '', SYMS, NAMES)['ticker'] == 'NVDA'
    # Common uppercase words must not be mistaken for symbols
    for title in ('CEO steps down at a major bank', 'US stocks open higher',
                  'The FED and the ECB diverge'):
        assert news.classify(title, '', SYMS, NAMES)['ticker'] is None, title


@check('classify: the longest company-name match wins')
def t_longest_name():
    names = dict(NAMES, **{'apple': 'APLE', 'apple inc.': 'AAPL'})
    got = news.classify('Apple Inc. lifts its dividend', '', SYMS, names)['ticker']
    assert got == 'AAPL', got


@check('classify: every story gets artwork metadata, never a blank')
def t_art_always():
    for title in ('', 'Something entirely unclassifiable happened', 'x' * 300):
        art = news.classify(title)
        assert set(art) == {'topic', 'direction', 'ticker'}, art
        assert art['topic'], 'topic must always fall back to a usable default'


def main():
    failed = 0
    for name, fn in CHECKS:
        try:
            fn()
            print(f'  \033[32mPASS\033[0m  {name}')
        except AssertionError as e:
            failed += 1
            print(f'  \033[31mFAIL\033[0m  {name}\n          {e}')
        except Exception as e:
            failed += 1
            print(f'  \033[31mERROR\033[0m {name}\n          {type(e).__name__}: {e}')
    print(f'\n{len(CHECKS) - failed}/{len(CHECKS)} passed')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
