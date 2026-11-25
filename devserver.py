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
    # Every other story carries art, as a real mix of feeds does, so both the
    # photo path and the drawn-art path are exercised.
    return ([{'title': t, 'link': 'https://example.com/' + str(i),
              'summary': 'An example summary for this story.',
              'image': ('https://img.example.com/%s.jpg' % i) if i % 2 == 0 else None,
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



# --- batch quotes and gaps, stubbed
import market as _mkt2
import random as _r2


def _fake_batch(tickers, per_ticker_fallback=None):
    out = {}
    for t in tickers:
        r = _r2.Random(t)
        px = round(r.uniform(15, 800), 2)
        # Extended-hours prints exist for most but not all names, which is what
        # the tooltip has to cope with.
        has_ext = r.random() > 0.2
        pre = r.random() > 0.45
        out[t] = {'price': px,
                  'chg': round(r.gauss(0.2, 2.4), 2),
                  'cap': None, 'open': None, 'prev_close': None,
                  'volume': None, 'name': None,
                  'state': 'PRE' if pre else 'POST',
                  'pre_price': round(px * (1 + r.gauss(0, .009)), 2) if has_ext and pre else None,
                  'pre_chg': round(r.gauss(0, .9), 2) if has_ext and pre else None,
                  'post_price': round(px * (1 + r.gauss(0, .009)), 2) if has_ext and not pre else None,
                  'post_chg': round(r.gauss(0, .9), 2) if has_ext and not pre else None,
                  'prev_close': round(px / (1 + r.gauss(0.2, 2.4) / 100), 2),
                  'dma50': round(px * r.uniform(0.9, 1.08), 2), 'dma200': round(px * r.uniform(0.82, 1.1), 2),
                  'hi52': round(px * r.uniform(1.0, 1.4), 2), 'lo52': round(px * r.uniform(0.55, 0.98), 2),
                  'pe': round(r.uniform(8, 60), 1) if r.random() > .1 else None,
                  'fpe': round(r.uniform(7, 45), 1) if r.random() > .15 else None,
                  'pb': round(r.uniform(0.8, 18), 2), 'eps': round(px / r.uniform(10, 40), 2),
                  'div_yield': round(r.uniform(0, 4.5), 2) if r.random() > .3 else None,
                  'volume': int(r.uniform(1e6, 4e7)), 'avg_vol': int(r.uniform(1e6, 3e7)),
                  'cap': round(r.uniform(15, 3000), 1), 'market_time': int(engine.time.time()) - 900}
    return out


_mkt2.batch_quotes = _fake_batch
A.market.batch_quotes = _fake_batch


def _fake_gap(ticker):
    r = _r2.Random('gap' + ticker)
    if r.random() > 0.45:
        return None
    pct = round(r.gauss(0, 3.2), 2)
    if abs(pct) < 0.75:
        return None
    prev = round(r.uniform(40, 500), 2)
    o = round(prev * (1 + pct / 100), 2)
    filled = r.random() > 0.6
    return {'ticker': ticker, 'direction': 'up' if pct > 0 else 'down',
            'gap_pct': pct, 'gap_atr': round(abs(pct) / 1.6, 2),
            'prev_close': prev, 'open': o, 'price': round(o * (1 + r.gauss(0, .01)), 2),
            'high': round(o * 1.01, 2), 'low': round(o * 0.99, 2),
            'fill_level': prev, 'filled': filled,
            'retrace_pct': 100.0 if filled else round(r.uniform(0, 80), 1),
            'held': r.random() > 0.4, 'from_open_pct': round(r.gauss(0, 1.2), 2),
            'vol_ratio': round(r.uniform(0.8, 4.0), 2), 'date': '2026-10-21'}


engine.detect_gap = _fake_gap

# --- SEC company facts, stubbed: six fiscal years and quarters, shaped like the real document
import fundamentals as _fund


def _fake_facts(ticker):
    r = _r2.Random('sec' + ticker)
    if ticker.upper() in ('SPY', 'QQQ', 'TEVA.TA'):
        return None, None
    rev0 = r.uniform(20e9, 300e9)
    g = [r.uniform(-0.04, 0.22) for _ in range(6)]
    years = list(range(2019, 2025))
    rows = {}
    rev = rev0
    for y, gr in zip(years, g):
        rev *= 1 + gr
        gm, om = r.uniform(0.38, 0.7), r.uniform(0.12, 0.38)
        ni = rev * om * 0.8
        rows[y] = dict(rev=rev, gp=rev * gm, oi=rev * om, pre=rev * om * 0.98, tax=rev * om * 0.98 * 0.18, ni=ni,
                       eps=ni / 15e9, cfo=ni * r.uniform(0.9, 1.35), capex=rev * r.uniform(0.03, 0.09),
                       eq=rev * r.uniform(0.4, 0.9), debt=rev * r.uniform(0.1, 0.4), cash=rev * r.uniform(0.08, 0.3),
                       assets=rev * r.uniform(1.2, 2.2), rnd=rev * r.uniform(0.05, 0.16), buy=ni * r.uniform(0.2, 0.8))
    def fy(y): return (f"{y - 1}-10-01", f"{y}-09-30")
    def e(start, end, val, form='10-K', filed=None):
        x = {'end': end, 'val': round(val), 'form': form, 'filed': filed or end[:4] + '-11-01', 'accn': 'x'}
        if start: x['start'] = start
        return x
    usd = lambda tag, f: {tag: {'units': {'USD': [e(*fy(y), f(v)) for y, v in rows.items()]}}}
    inst = lambda tag, f: {tag: {'units': {'USD': [e(None, fy(y)[1], f(v)) for y, v in rows.items()]}}}
    g_ = {}
    for t_, f_ in (('RevenueFromContractWithCustomerExcludingAssessedTax', lambda v: v['rev']), ('GrossProfit', lambda v: v['gp']),
                   ('OperatingIncomeLoss', lambda v: v['oi']), ('NetIncomeLoss', lambda v: v['ni']),
                   ('IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest', lambda v: v['pre']),
                   ('IncomeTaxExpenseBenefit', lambda v: v['tax']), ('ResearchAndDevelopmentExpense', lambda v: v['rnd']),
                   ('NetCashProvidedByUsedInOperatingActivities', lambda v: v['cfo']),
                   ('PaymentsToAcquirePropertyPlantAndEquipment', lambda v: v['capex']),
                   ('PaymentsForRepurchaseOfCommonStock', lambda v: v['buy'])):
        g_.update(usd(t_, f_))
    for t_, f_ in (('StockholdersEquity', lambda v: v['eq']), ('LongTermDebt', lambda v: v['debt']),
                   ('CashAndCashEquivalentsAtCarryingValue', lambda v: v['cash']), ('Assets', lambda v: v['assets']),
                   ('Liabilities', lambda v: v['assets'] - v['eq'])):
        g_.update(inst(t_, f_))
    g_['EarningsPerShareDiluted'] = {'units': {'USD/shares': [e(*fy(y), 0) | {'val': round(v['eps'], 2)} for y, v in rows.items()]}}
    # quarters of the last two fiscal years (Q1-Q3 filed, Q4 derived by the parser)
    for y in (2023, 2024):
        v = rows[y]
        qs = [(f"{y - 1}-10-01", f"{y - 1}-12-31"), (f"{y}-01-01", f"{y}-03-31"), (f"{y}-04-01", f"{y}-06-30")]
        for i, (s_, e_) in enumerate(qs):
            share = (0.23, 0.24, 0.25)[i]
            for tag, key in (('RevenueFromContractWithCustomerExcludingAssessedTax', 'rev'), ('GrossProfit', 'gp'),
                             ('OperatingIncomeLoss', 'oi'), ('NetIncomeLoss', 'ni')):
                g_[tag]['units']['USD'].append(e(s_, e_, v[key] * share, '10-Q', e_[:8] + '28'))
            g_['EarningsPerShareDiluted']['units']['USD/shares'].append(e(s_, e_, 0, '10-Q', e_[:8] + '28') | {'val': round(v['eps'] * share, 2)})
    return 1000 + r.randint(1, 9999), {'entityName': f'{ticker.upper()} Test Corp', 'facts': {'us-gaap': g_}}


_fund.company_facts = _fake_facts

# --- calendars, stubbed
import calendars as _cal


def _fake_cal(kind, day, get=None):
    r = _r2.Random(kind + day.isoformat())
    if kind == 'earnings':
        names = [('AAPL', 'Apple'), ('MSFT', 'Microsoft'), ('NVDA', 'NVIDIA'), ('CRM', 'Salesforce'), ('ZS', 'Zscaler'), ('LULU', 'Lululemon'), ('AVGO', 'Broadcom')]
        return [{'date': day.isoformat(), 'symbol': s, 'name': n, 'session': r.choice(['before the open', 'after the close', 'time not given']),
                 'market_cap': r.uniform(5e9, 3e12), 'quarter': 'Oct/2026', 'eps_estimate': round(r.uniform(-0.2, 3), 2),
                 'estimates': r.randint(2, 40), 'eps_last_year': round(r.uniform(-0.3, 2.8), 2), 'last_year_date': '12/01/2025'}
                for s, n in r.sample(names, 4)]
    if kind == 'economicevents':
        ev = ['GDP (QoQ)', 'Initial Jobless Claims', 'ISM Manufacturing PMI', 'Core PCE (MoM)', 'Consumer Confidence']
        return [{'date': day.isoformat(), 'time_gmt': f'{r.randint(12, 15)}:30', 'country': r.choice(['United States', 'Euro Zone', 'Japan']),
                 'event': e, 'actual': None, 'consensus': f'{r.uniform(0, 3):.1f}%', 'previous': f'{r.uniform(0, 3):.1f}%'} for e in r.sample(ev, 3)]
    return [{'date': day.isoformat(), 'symbol': s, 'name': s + ' Corp', 'ex_date': day.strftime('%m/%d/%Y'), 'record_date': day.strftime('%m/%d/%Y'),
             'pay_date': '12/20/2026', 'amount': round(r.uniform(0.1, 1.2), 2), 'annual': round(r.uniform(0.4, 4.8), 2)} for s in ('KO', 'PG', 'JPM')]


_cal.fetch = _fake_cal

# --- assistant: a stand-in model that writes from the context (and slips one wrong number in)
import assistant as _as


def _fake_model(question, context, key, post=None, models=None, timeout=25):
    ids = [k for k in context if k.startswith('SEC:')][-1:] or list(context)[:1]
    if not ids:
        return {'answer': 'The data does not contain an answer to that.', 'sources': [], 'model': 'dev-stand-in'}
    k = ids[0]
    row = context[k]
    om = row.get('operating_margin')
    text = (f"Operating margin was {om}% [{k}]. " if om is not None else '') + \
           (f"Revenue growth was {row.get('revenue_growth')}% [{k}]. " if row.get('revenue_growth') is not None else '') + \
           "Analysts expect 31.7% next year."
    return {'answer': text, 'sources': [k], 'model': 'dev-stand-in'}


_as.ask_model = _fake_model
os.environ.setdefault('GEMINI_API_KEY', 'dev-only')

if __name__ == '__main__':
    A.app.run(host='127.0.0.1', port=5055, debug=False, use_reloader=False)
