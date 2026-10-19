"""Run the real app with synthetic data so the UI can be driven offline.

Every upstream the app uses - Yahoo, the RSS outlets, CNN - is blocked by this
sandbox's egress policy, so each one is replaced with a believable stand-in.
"""
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['SECRET_KEY'] = 'dev-key'

import engine
import test_engine as T

PATHS = {
    'NVDA': T.uptrend(n=320, start=60, seed=1),
    'MSFT': T.uptrend(n=320, start=300, daily=0.0009, seed=2),
    'TSLA': T.downtrend(n=320, start=380, seed=4),
    'AAPL': None,
    'AMD': None,
    'SPY': T.uptrend(n=320, start=400, daily=0.0006, seed=8),
    'QQQ': T.uptrend(n=320, start=380, daily=0.0008, seed=9),
}
pb = T.uptrend(n=320, start=180, seed=6)
for i in range(1, 9):
    pb[-i] = pb[-10] * (1 - 0.004 * (9 - i))
PATHS['AAPL'] = pb
bo = T.uptrend(n=320, start=120, seed=10)
bo[-1] = max(bo[-25:]) * 1.03
PATHS['AMD'] = bo

for sym, closes in PATHS.items():
    mult = 2.4 if sym == 'AMD' else 1.0
    engine._DF_CACHE[f'{sym}:2y'] = (engine.time.time() + 86400,
                                     T.series_to_df(closes, vol_last_mult=mult))
    long_closes = (T.downtrend(n=1100, start=closes[0], seed=22) if sym == 'TSLA'
                   else T.uptrend(n=1100, start=closes[0], seed=21))
    engine._DF_CACHE[f'{sym}:5y'] = (engine.time.time() + 86400,
                                     T.series_to_df(long_closes, vol_last_mult=mult))

import app as A
A.DB_PATH = tempfile.mktemp(suffix='.db')
A.init_db()


def fake_chart(ticker, interval, range_, prepost=False):
    closes = PATHS.get(ticker.upper()) or T.uptrend(n=240, start=100, seed=abs(hash(ticker)) % 97)
    return T.series_to_df(closes)


def fake_summary(ticker, modules):
    return {'price': {'longName': f'{ticker} Test Corp', 'shortName': ticker,
                      'marketState': 'REGULAR', 'currency': 'USD',
                      'regularMarketPrice': {'raw': 100.0},
                      'regularMarketChangePercent': {'raw': 0.012},
                      'marketCap': {'raw': 1.2e12}},
            'summaryDetail': {'fiftyTwoWeekLow': {'raw': 70.0},
                              'fiftyTwoWeekHigh': {'raw': 140.0},
                              'dividendYield': {'raw': 0.005}},
            'assetProfile': {'sector': 'Technology', 'industry': 'Software',
                             'longBusinessSummary': 'A test company used for local development.',
                             'companyOfficers': [{'title': 'CEO', 'name': 'Jane Doe'}],
                             'website': 'https://example.com',
                             'city': 'Tel Aviv', 'country': 'Israel',
                             'fullTimeEmployees': 1000}}


A.yf_chart = fake_chart
A.yf_summary = fake_summary


def fake_quote(t):
    r = random.Random(t)
    base = r.uniform(20, 600)
    return {'ticker': t, 'price': round(base, 2), 'chg': round(r.gauss(0.3, 2.2), 2),
            'spark': [round(base * (1 + r.gauss(0, .01)), 2) for _ in range(20)]}


A.quick_quote = fake_quote

# --- RSS
import news as _news
_HEAD = {
    'CNBC': ['Fed signals patience on rates', 'Chipmakers lead the tape higher',
             'Oil slips as inventories build'],
    'גלובס': ['Teva jumps after FDA approval', 'Tel Aviv closes higher'],
    'כלכליסט': ['Bank of Israel holds rates', 'Energean reports a discovery'],
    'Yahoo Finance': ['Nvidia extends its rally', 'Apple supplier raises guidance'],
    'MarketWatch': ['Small caps break out of a range'],
}


def _fake_feed(feed, timeout=9):
    key, source, url, lang, scope = feed
    heads = _HEAD.get(source)
    if heads is None:
        return [], 'HTTP 403'
    now = int(engine.time.time())
    return ([{'title': t, 'link': 'https://example.com/' + str(i),
              'summary': 'An example summary for this story.',
              'time': now - (i + 1) * 5400, 'source': source, 'lang': lang, 'scope': scope}
             for i, t in enumerate(heads)], None)


_news.fetch_feed = _fake_feed

# --- CNN Fear & Greed
import market as _mkt


def _fake_fg():
    rnd = random.Random(7)
    return {'ok': True, 'score': 38, 'rating': 'Fear', 'updated': None,
            'previous': {'close': 41, 'week': 55, 'month': 62, 'year': 48},
            'components': [{'key': k, 'label': l, 'blurb': b,
                            'score': rnd.randint(12, 88), 'rating': 'Fear'}
                           for k, l, b in _mkt.COMPONENTS],
            'history': [], 'source': 'CNN Business Fear & Greed Index'}


_mkt.fear_greed = _fake_fg
A.market.fear_greed = _fake_fg

if __name__ == '__main__':
    A.app.run(host='127.0.0.1', port=5055, debug=False, use_reloader=False)
