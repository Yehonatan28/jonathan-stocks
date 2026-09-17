from flask import Flask, render_template, jsonify, request, session, Response
import os
import math
import time
import sqlite3
import hashlib
import secrets
import pandas as pd
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import engine

app = Flask(__name__)
# Session cookies are signed with this key. The fallback is random per process
# rather than a literal: a constant checked into a public repository lets anyone
# forge a session cookie and sign in as any user. Set SECRET_KEY in the host's
# environment so sessions survive a restart.
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)

HEADERS = {'User-Agent': 'Mozilla/5.0'}
# Serverless hosts (Vercel) mount a read-only filesystem with only /tmp
# writable, and that directory does not survive a cold start. Registered
# accounts therefore persist only on a host with a real disk; guest mode keeps
# everything in the browser and is unaffected.
DB_PATH = os.environ.get('DB_PATH') or (
    '/tmp/stocks.db' if os.environ.get('VERCEL')
    else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'stocks.db'))

# simple in-memory cache {key: (expires_at, data)}
_CACHE = {}


def cache_get(key):
    v = _CACHE.get(key)
    if v and v[0] > time.time():
        return v[1]
    return None


def cache_set(key, data, ttl=300):
    _CACHE[key] = (time.time() + ttl, data)


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS portfolio(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        ticker TEXT NOT NULL,
        qty REAL NOT NULL,
        entry REAL NOT NULL,
        notes TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS watchlist(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        ticker TEXT NOT NULL,
        UNIQUE(user_id, ticker));
    CREATE TABLE IF NOT EXISTS alerts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        ticker TEXT NOT NULL,
        condition TEXT NOT NULL,
        price REAL NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS pf_history(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        day TEXT NOT NULL,
        value REAL NOT NULL,
        UNIQUE(user_id, day));
    CREATE TABLE IF NOT EXISTS settings(
        user_id INTEGER PRIMARY KEY,
        equity REAL DEFAULT 0,
        risk_pct REAL DEFAULT 1.0,
        trail_mult REAL DEFAULT 3.0);
    ''')
    # risk-management columns, added to portfolios created before the engine
    existing = {r['name'] for r in conn.execute('PRAGMA table_info(portfolio)')}
    for col, decl in (('stop', 'REAL'), ('init_stop', 'REAL'),
                      ('stop_type', "TEXT DEFAULT 'fixed'"), ('target', 'REAL'),
                      ('opened_at', 'TEXT')):
        if col not in existing:
            conn.execute(f'ALTER TABLE portfolio ADD COLUMN {col} {decl}')
    conn.commit()
    conn.close()


init_db()


def hash_pw(pw):
    return hashlib.sha256(('js-salt-' + pw).encode()).hexdigest()


def _num(v):
    """Coerce user input to a float, or None when it is blank/unparsable."""
    if v is None or v == '':
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def current_user():
    return session.get('user_id')


# ---------- Auth ----------

@app.route('/api/auth/register', methods=['POST'])
def register():
    d = request.get_json(silent=True) or {}
    username = (d.get('username') or '').strip()
    email = (d.get('email') or '').strip().lower()
    password = d.get('password') or ''
    if len(username) < 2:
        return jsonify({'error': 'Username too short'}), 400
    if '@' not in email:
        return jsonify({'error': 'Invalid email'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400
    conn = db()
    try:
        cur = conn.execute(
            'INSERT INTO users(username,email,password_hash) VALUES(?,?,?)',
            (username, email, hash_pw(password)))
        conn.commit()
        session['user_id'] = cur.lastrowid
        session['username'] = username
        session.permanent = True
        return jsonify({'ok': True, 'username': username})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Username or email already exists'}), 409
    finally:
        conn.close()


@app.route('/api/auth/login', methods=['POST'])
def login():
    d = request.get_json(silent=True) or {}
    email = (d.get('email') or '').strip().lower()
    password = d.get('password') or ''
    conn = db()
    row = conn.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
    conn.close()
    if not row or row['password_hash'] != hash_pw(password):
        return jsonify({'error': 'Wrong email or password'}), 401
    session['user_id'] = row['id']
    session['username'] = row['username']
    session.permanent = True
    return jsonify({'ok': True, 'username': row['username']})


@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'ok': True})


@app.route('/api/auth/me')
def me():
    if current_user():
        return jsonify({'username': session.get('username')})
    return jsonify({'error': 'Not logged in'}), 401


# ---------- Portfolio ----------

@app.route('/api/portfolio', methods=['GET', 'POST'])
def portfolio():
    uid = current_user()
    if not uid:
        return jsonify({'error': 'Not logged in'}), 401
    conn = db()
    if request.method == 'POST':
        d = request.get_json(silent=True) or {}
        ticker = (d.get('ticker') or '').strip().upper()
        try:
            qty = float(d.get('qty'))
            entry = float(d.get('entry'))
        except (TypeError, ValueError):
            conn.close()
            return jsonify({'error': 'Quantity and price must be numbers'}), 400
        if not ticker or qty <= 0 or entry <= 0:
            conn.close()
            return jsonify({'error': 'Invalid data'}), 400
        stop = _num(d.get('stop'))
        cur = conn.execute(
            'INSERT INTO portfolio(user_id,ticker,qty,entry,notes,stop,init_stop,'
            'stop_type,target,opened_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
            (uid, ticker, qty, entry, d.get('notes', ''), stop, stop,
             d.get('stop_type') or 'fixed', _num(d.get('target')),
             datetime.utcnow().strftime('%Y-%m-%d')))
        conn.commit()
        pid = cur.lastrowid
        conn.close()
        return jsonify({'ok': True, 'id': pid})
    rows = conn.execute('SELECT * FROM portfolio WHERE user_id=?', (uid,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/portfolio/<int:pos_id>', methods=['DELETE', 'PATCH'])
def portfolio_delete(pos_id):
    uid = current_user()
    if not uid:
        return jsonify({'error': 'Not logged in'}), 401
    conn = db()
    if request.method == 'PATCH':
        d = request.get_json(silent=True) or {}
        row = conn.execute('SELECT * FROM portfolio WHERE id=? AND user_id=?',
                           (pos_id, uid)).fetchone()
        if not row:
            conn.close()
            return jsonify({'error': 'Position not found'}), 404
        fields, values = [], []
        for key in ('qty', 'entry', 'stop', 'target'):
            if key in d:
                fields.append(f'{key}=?')
                values.append(_num(d[key]))
        if 'stop_type' in d:
            fields.append('stop_type=?')
            values.append(d['stop_type'] if d['stop_type'] in ('fixed', 'trail') else 'fixed')
        if 'notes' in d:
            fields.append('notes=?')
            values.append(d['notes'])
        # the first stop ever set is the reference risk every R multiple uses
        if 'stop' in d and row['init_stop'] is None and _num(d['stop']) is not None:
            fields.append('init_stop=?')
            values.append(_num(d['stop']))
        if not fields:
            conn.close()
            return jsonify({'error': 'Nothing to update'}), 400
        values.extend([pos_id, uid])
        conn.execute(f'UPDATE portfolio SET {",".join(fields)} WHERE id=? AND user_id=?',
                     values)
        conn.commit()
        conn.close()
        return jsonify({'ok': True})
    conn.execute('DELETE FROM portfolio WHERE id=? AND user_id=?', (pos_id, uid))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@app.route('/api/settings', methods=['GET', 'POST'])
def settings_route():
    uid = current_user()
    if not uid:
        return jsonify({'error': 'Not logged in'}), 401
    conn = db()
    if request.method == 'POST':
        d = request.get_json(silent=True) or {}
        equity = max(0.0, _num(d.get('equity')) or 0)
        risk_pct = min(10.0, max(0.1, _num(d.get('risk_pct')) or 1.0))
        tm = _num(d.get('trail_mult'))
        trail_mult = min(6.0, max(1.0, tm)) if tm else None
        conn.execute(
            'INSERT INTO settings(user_id,equity,risk_pct,trail_mult) VALUES(?,?,?,?) '
            'ON CONFLICT(user_id) DO UPDATE SET equity=excluded.equity,'
            'risk_pct=excluded.risk_pct,trail_mult=excluded.trail_mult',
            (uid, equity, risk_pct, trail_mult))
        conn.commit()
        conn.close()
        return jsonify({'ok': True, 'equity': equity, 'risk_pct': risk_pct,
                        'trail_mult': trail_mult})
    row = conn.execute('SELECT equity,risk_pct,trail_mult FROM settings WHERE user_id=?',
                       (uid,)).fetchone()
    conn.close()
    return jsonify(dict(row) if row else dict(engine.DEFAULT_SETTINGS))


@app.route('/api/pf_history', methods=['GET', 'POST'])
def pf_history():
    uid = current_user()
    if not uid:
        return jsonify({'error': 'Not logged in'}), 401
    conn = db()
    if request.method == 'POST':
        d = request.get_json(silent=True) or {}
        try:
            value = float(d.get('value'))
        except (TypeError, ValueError):
            conn.close()
            return jsonify({'error': 'Invalid value'}), 400
        day = datetime.utcnow().strftime('%Y-%m-%d')
        conn.execute(
            'INSERT INTO pf_history(user_id,day,value) VALUES(?,?,?) '
            'ON CONFLICT(user_id,day) DO UPDATE SET value=excluded.value',
            (uid, day, value))
        conn.commit()
        conn.close()
        return jsonify({'ok': True})
    rows = conn.execute(
        'SELECT day,value FROM pf_history WHERE user_id=? ORDER BY day', (uid,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ---------- Watchlist ----------

@app.route('/api/watchlist', methods=['GET'])
def watchlist_get():
    uid = current_user()
    if not uid:
        return jsonify({'error': 'Not logged in'}), 401
    conn = db()
    rows = conn.execute('SELECT ticker FROM watchlist WHERE user_id=?', (uid,)).fetchall()
    conn.close()
    return jsonify([r['ticker'] for r in rows])


@app.route('/api/watchlist/<ticker>', methods=['POST', 'DELETE'])
def watchlist_mod(ticker):
    uid = current_user()
    if not uid:
        return jsonify({'error': 'Not logged in'}), 401
    ticker = ticker.strip().upper()
    conn = db()
    if request.method == 'POST':
        conn.execute('INSERT OR IGNORE INTO watchlist(user_id,ticker) VALUES(?,?)', (uid, ticker))
    else:
        conn.execute('DELETE FROM watchlist WHERE user_id=? AND ticker=?', (uid, ticker))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


# ---------- Alerts ----------

@app.route('/api/alerts', methods=['GET', 'POST'])
def alerts():
    uid = current_user()
    if not uid:
        return jsonify({'error': 'Not logged in'}), 401
    conn = db()
    if request.method == 'POST':
        d = request.get_json(silent=True) or {}
        ticker = (d.get('ticker') or '').strip().upper()
        cond = d.get('condition')
        try:
            price = float(d.get('price'))
        except (TypeError, ValueError):
            conn.close()
            return jsonify({'error': 'Invalid price'}), 400
        if not ticker or cond not in ('above', 'below'):
            conn.close()
            return jsonify({'error': 'Invalid data'}), 400
        cur = conn.execute(
            'INSERT INTO alerts(user_id,ticker,condition,price) VALUES(?,?,?,?)',
            (uid, ticker, cond, price))
        conn.commit()
        aid = cur.lastrowid
        conn.close()
        return jsonify({'ok': True, 'id': aid})
    rows = conn.execute('SELECT * FROM alerts WHERE user_id=?', (uid,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/alerts/<int:alert_id>', methods=['DELETE'])
def alerts_delete(alert_id):
    uid = current_user()
    if not uid:
        return jsonify({'error': 'Not logged in'}), 401
    conn = db()
    conn.execute('DELETE FROM alerts WHERE id=? AND user_id=?', (alert_id, uid))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


# ---------- Market data (Yahoo REST) ----------

def yf_chart(ticker, interval, range_, prepost=False):
    r = requests.get(
        f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}',
        headers=HEADERS,
        params={'interval': interval, 'range': range_,
                'includePrePost': 'true' if prepost else 'false'},
        timeout=10)
    r.raise_for_status()
    data = r.json()['chart']['result'][0]
    quotes = data['indicators']['quote'][0]
    timestamps = data['timestamp']
    df = pd.DataFrame({
        'Open': quotes['open'], 'High': quotes['high'], 'Low': quotes['low'],
        'Close': quotes['close'], 'Volume': quotes['volume'],
        'Time': [datetime.utcfromtimestamp(t) for t in timestamps]
    }).dropna().set_index('Time')
    return df


def yf_summary(ticker, modules):
    r = requests.get(
        f'https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}',
        headers=HEADERS, params={'modules': modules}, timeout=10)
    if not r.ok:
        return {}
    return r.json().get('quoteSummary', {}).get('result', [{}])[0] or {}


def raw(d, *keys):
    for k in keys:
        d = (d or {}).get(k, {})
    if isinstance(d, dict):
        return d.get('raw')
    return d if not isinstance(d, dict) else None


def period_params(period):
    return {
        '1d': ('5m', '1d'), '5d': ('15m', '5d'), '1mo': ('1d', '1mo'),
        '3mo': ('1d', '3mo'), '6mo': ('1d', '6mo'), '1y': ('1d', '1y'),
        '2y': ('1wk', '2y'), '5y': ('1wk', '5y'), 'max': ('1mo', 'max'),
    }.get(period, ('1d', '1mo'))


def quick_quote(ticker):
    try:
        hist = yf_chart(ticker, '1d', '5d')
        close = hist['Close']
        price = round(float(close.iloc[-1]), 2)
        prev = round(float(close.iloc[-2]), 2)
        return {'ticker': ticker, 'price': price,
                'chg': round((price - prev) / prev * 100, 2),
                'spark': [round(float(p), 2) for p in close.tolist()]}
    except Exception:
        return {'ticker': ticker, 'price': None, 'chg': None, 'spark': []}


@app.route('/api/quotes')
def quotes():
    tickers = [t.strip().upper() for t in request.args.get('tickers', '').split(',') if t.strip()][:30]
    if not tickers:
        return jsonify([])
    key = 'q:' + ','.join(sorted(tickers))
    hit = cache_get(key)
    if hit:
        return jsonify(hit)
    with ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(quick_quote, tickers))
    cache_set(key, results, 60)
    return jsonify(results)


@app.route('/api/quote_full/<ticker>')
def quote_full(ticker):
    """Regular + pre-market + after-hours prices, market state, 52w range."""
    key = 'qf:' + ticker.upper()
    hit = cache_get(key)
    if hit:
        return jsonify(hit)
    try:
        res = yf_summary(ticker, 'price,summaryDetail')
        pr = res.get('price', {})
        sd = res.get('summaryDetail', {})
        out = {
            'ticker': ticker.upper(),
            'name': pr.get('longName') or pr.get('shortName') or ticker.upper(),
            'state': pr.get('marketState', ''),  # PRE / REGULAR / POST / CLOSED
            'price': raw(pr, 'regularMarketPrice'),
            'chg_pct': raw(pr, 'regularMarketChangePercent'),
            'pre_price': raw(pr, 'preMarketPrice'),
            'pre_chg_pct': raw(pr, 'preMarketChangePercent'),
            'post_price': raw(pr, 'postMarketPrice'),
            'post_chg_pct': raw(pr, 'postMarketChangePercent'),
            'wk52_low': raw(sd, 'fiftyTwoWeekLow'),
            'wk52_high': raw(sd, 'fiftyTwoWeekHigh'),
            'currency': pr.get('currency', 'USD'),
        }
        if out['chg_pct'] is not None:
            out['chg_pct'] = round(out['chg_pct'] * 100, 2)
        if out['pre_chg_pct'] is not None:
            out['pre_chg_pct'] = round(out['pre_chg_pct'] * 100, 2)
        if out['post_chg_pct'] is not None:
            out['post_chg_pct'] = round(out['post_chg_pct'] * 100, 2)
        cache_set(key, out, 60)
        return jsonify(out)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/earnings/<ticker>')
def earnings(ticker):
    key = 'e:' + ticker.upper()
    hit = cache_get(key)
    if hit:
        return jsonify(hit)
    try:
        res = yf_summary(ticker, 'calendarEvents')
        ce = res.get('calendarEvents', {}).get('earnings', {})
        dates = ce.get('earningsDate', [])
        ts = dates[0].get('raw') if dates else None
        out = {'ticker': ticker.upper(), 'earnings_ts': ts,
               'eps_avg': raw(ce, 'earningsAverage')}
        cache_set(key, out, 3600)
        return jsonify(out)
    except Exception:
        return jsonify({'ticker': ticker.upper(), 'earnings_ts': None})


@app.route('/api/analyst/<ticker>')
def analyst(ticker):
    key = 'a:' + ticker.upper()
    hit = cache_get(key)
    if hit:
        return jsonify(hit)
    try:
        res = yf_summary(ticker, 'financialData,recommendationTrend')
        fd = res.get('financialData', {})
        trend = (res.get('recommendationTrend', {}).get('trend') or [{}])[0]
        out = {
            'ticker': ticker.upper(),
            'recommendation': fd.get('recommendationKey', ''),
            'target_mean': raw(fd, 'targetMeanPrice'),
            'target_high': raw(fd, 'targetHighPrice'),
            'target_low': raw(fd, 'targetLowPrice'),
            'analysts': raw(fd, 'numberOfAnalystOpinions'),
            'strong_buy': trend.get('strongBuy'), 'buy': trend.get('buy'),
            'hold': trend.get('hold'), 'sell': trend.get('sell'),
            'strong_sell': trend.get('strongSell'),
        }
        cache_set(key, out, 3600)
        return jsonify(out)
    except Exception:
        return jsonify({'ticker': ticker.upper()})


# ---------- Treemap: index constituents (top by market cap) ----------
# weights = approximate market caps in $B, used for square sizing.
SPX = [('NVDA', 4400), ('MSFT', 3800), ('AAPL', 3300), ('GOOGL', 2400), ('AMZN', 2300),
       ('META', 1800), ('AVGO', 1300), ('TSLA', 1100), ('BRK-B', 1050), ('JPM', 800),
       ('WMT', 780), ('LLY', 730), ('ORCL', 650), ('V', 640), ('MA', 530),
       ('NFLX', 520), ('XOM', 470), ('COST', 420), ('JNJ', 400), ('HD', 390),
       ('PG', 390), ('PLTR', 380), ('ABBV', 370), ('BAC', 360), ('CVX', 300),
       ('KO', 300), ('GE', 290), ('AMD', 290), ('TMUS', 280), ('CSCO', 270),
       ('WFC', 260), ('CRM', 260), ('PM', 250), ('IBM', 250), ('MS', 230),
       ('UNH', 230), ('ABT', 230), ('GS', 220), ('LIN', 220), ('INTU', 210),
       ('MCD', 210), ('AXP', 210), ('DIS', 200), ('RTX', 200), ('NOW', 190),
       ('MRK', 190), ('CAT', 190), ('T', 190), ('PEP', 180), ('UBER', 180),
       ('BKNG', 170), ('VZ', 170), ('TMO', 170), ('SCHW', 170), ('ISRG', 160),
       ('QCOM', 160), ('BLK', 150), ('TXN', 150), ('C', 150), ('BA', 150),
       ('SPGI', 150), ('AMGN', 140), ('BSX', 140), ('ADBE', 140), ('NEE', 140),
       ('HON', 130), ('AMAT', 130), ('PGR', 130), ('DHR', 130), ('GILD', 130),
       ('ETN', 120), ('PFE', 120), ('COF', 120), ('UNP', 120), ('CMCSA', 110),
       ('MU', 110), ('LOW', 110), ('APH', 110), ('LRCX', 110), ('ADP', 110),
       ('ANET', 100), ('KLAC', 100), ('VRTX', 100), ('MDT', 100), ('SBUX', 100),
       ('PANW', 100), ('CRWD', 95), ('INTC', 95), ('MMC', 90), ('ADI', 90),
       ('CB', 90), ('LMT', 85), ('DE', 85), ('BX', 85), ('SO', 85),
       ('ICE', 80), ('MO', 80), ('PLD', 80), ('DUK', 80), ('SHW', 75)]
NDX = [('NVDA', 4400), ('MSFT', 3800), ('AAPL', 3300), ('GOOGL', 2400), ('AMZN', 2300),
       ('META', 1800), ('AVGO', 1300), ('TSLA', 1100), ('NFLX', 520), ('COST', 420),
       ('PLTR', 380), ('AMD', 290), ('TMUS', 280), ('CSCO', 270), ('CRM', 260),
       ('INTU', 210), ('QCOM', 160), ('TXN', 150), ('ISRG', 160), ('BKNG', 170),
       ('AMGN', 140), ('ADBE', 140), ('AMAT', 130), ('PEP', 180), ('GILD', 130),
       ('MU', 110), ('LRCX', 110), ('ADP', 110), ('ANET', 100), ('KLAC', 100),
       ('VRTX', 100), ('SBUX', 100), ('PANW', 100), ('CRWD', 95), ('INTC', 95),
       ('ADI', 90), ('MELI', 90), ('CTAS', 85), ('ORLY', 80), ('CEG', 80),
       ('MDLZ', 80), ('ABNB', 75), ('MAR', 75), ('MRVL', 70), ('FTNT', 70),
       ('MNST', 60), ('ADSK', 60), ('WDAY', 60), ('AEP', 55), ('PYPL', 55),
       ('NXPI', 55), ('CPRT', 55), ('ROP', 55), ('PCAR', 55), ('DASH', 90),
       ('APP', 110), ('AXON', 55), ('CHTR', 40), ('PAYX', 50), ('KDP', 45),
       ('ROST', 45), ('FAST', 45), ('EXC', 45), ('CCEP', 40), ('DDOG', 45),
       ('TTD', 45), ('VRSK', 40), ('XEL', 40), ('EA', 40), ('CTSH', 35),
       ('KHC', 35), ('IDXX', 35), ('ZS', 35), ('TEAM', 40), ('CSGP', 30),
       ('ANSS', 30), ('DXCM', 30), ('CDW', 25), ('BIIB', 20), ('ON', 25)]


@app.route('/api/treemap/<idx>')
def treemap(idx):
    defs = SPX if idx.lower() == 'spx' else NDX
    key = 'tm:' + idx.lower()
    hit = cache_get(key)
    if hit:
        return jsonify(hit)
    tickers = [t for t, _ in defs]
    with ThreadPoolExecutor(max_workers=16) as ex:
        results = list(ex.map(quick_quote, tickers))
    qmap = {q['ticker']: q for q in results}
    out = [{'t': t, 'w': w,
            'p': qmap.get(t, {}).get('price'),
            'c': qmap.get(t, {}).get('chg')}
           for t, w in defs]
    cache_set(key, out, 180)
    return jsonify(out)


@app.route('/api/search')
def search():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    try:
        r = requests.get('https://query2.finance.yahoo.com/v1/finance/search',
                         headers=HEADERS,
                         params={'q': q, 'quotesCount': 8, 'newsCount': 0},
                         timeout=8)
        items = r.json().get('quotes', []) if r.ok else []
        return jsonify([{'symbol': i.get('symbol', ''),
                         'name': i.get('shortname') or i.get('longname') or '',
                         'exch': i.get('exchDisp', ''),
                         'type': i.get('typeDisp', '')}
                        for i in items if i.get('symbol')])
    except Exception:
        return jsonify([])


@app.route('/api/profile/<ticker>')
def profile(ticker):
    key = 'p:' + ticker.upper()
    hit = cache_get(key)
    if hit:
        return jsonify(hit)
    try:
        result = yf_summary(ticker, 'assetProfile,price,summaryDetail')
        ap = result.get('assetProfile', {})
        pr = result.get('price', {})
        ceo = ''
        for o in ap.get('companyOfficers', []):
            title = (o.get('title') or '').upper()
            if 'CEO' in title or 'CHIEF EXECUTIVE' in title:
                ceo = o.get('name', '')
                break
        out = {
            'ticker': ticker.upper(),
            'name': pr.get('longName') or pr.get('shortName') or ticker.upper(),
            'summary': ap.get('longBusinessSummary', ''),
            'sector': ap.get('sector', ''),
            'industry': ap.get('industry', ''),
            'ceo': ceo,
            'employees': ap.get('fullTimeEmployees'),
            'website': ap.get('website', ''),
            'city': ap.get('city', ''),
            'country': ap.get('country', ''),
            'market_cap': raw(pr, 'marketCap'),
            'dividend_yield': raw(result.get('summaryDetail', {}), 'dividendYield'),
            'currency': pr.get('currency', 'USD'),
        }
        cache_set(key, out, 3600)
        return jsonify(out)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------- Engine: technical analysis + risk management ----------

@app.route('/api/engine/analyze/<ticker>')
def engine_analyze(ticker):
    key = 'an:' + ticker.upper()
    hit = cache_get(key)
    if hit:
        return jsonify(hit)
    out = engine.analyze(ticker)
    cache_set(key, out, 300 if out.get('ok') else 60)
    return jsonify(out)


def _clean_positions(raw):
    """Accept positions posted by a guest browser, dropping anything unusable."""
    out = []
    for p in (raw or [])[:60]:
        if not isinstance(p, dict):
            continue
        ticker = (p.get('ticker') or '').strip().upper()
        qty, entry = _num(p.get('qty')), _num(p.get('entry'))
        if not ticker or not qty or not entry or qty <= 0 or entry <= 0:
            continue
        out.append({
            'id': p.get('id'), 'ticker': ticker, 'qty': qty, 'entry': entry,
            'stop': _num(p.get('stop')), 'init_stop': _num(p.get('init_stop')),
            'stop_type': p.get('stop_type') if p.get('stop_type') in ('fixed', 'trail') else 'fixed',
            'target': _num(p.get('target')),
        })
    return out


@app.route('/api/engine/backtest/<ticker>')
def engine_backtest(ticker):
    """Replay the live rules over history for one ticker."""
    try:
        years = min(5.0, max(1.0, float(request.args.get('years', 3))))
    except (TypeError, ValueError):
        years = 3.0
    risk_pct = min(10.0, max(0.1, _num(request.args.get('risk_pct')) or 1.0))
    key = f'bt:{ticker.upper()}:{years}:{risk_pct}'
    hit = cache_get(key)
    if hit:
        return jsonify(hit)
    try:
        out = engine.backtest(ticker, years=years, settings={'risk_pct': risk_pct})
    except Exception as e:
        return jsonify({'ticker': ticker.upper(), 'ok': False,
                        'error': f'שגיאה בבדיקה ההיסטורית: {e}'}), 500
    cache_set(key, out, 1800 if out.get('ok') else 60)
    return jsonify(out)


@app.route('/api/engine/plan', methods=['POST'])
def engine_plan():
    """The daily action plan. Logged-in users are read from the database;
    guests post their locally stored portfolio in the request body."""
    d = request.get_json(silent=True) or {}
    uid = current_user()
    if uid:
        conn = db()
        positions = [dict(r) for r in
                     conn.execute('SELECT * FROM portfolio WHERE user_id=?', (uid,))]
        watch = [r['ticker'] for r in
                 conn.execute('SELECT ticker FROM watchlist WHERE user_id=?', (uid,))]
        row = conn.execute(
            'SELECT equity,risk_pct,trail_mult FROM settings WHERE user_id=?',
            (uid,)).fetchone()
        conn.close()
        settings = dict(row) if row else {}
    else:
        positions = _clean_positions(d.get('positions'))
        watch = [str(t).strip().upper() for t in (d.get('watch') or [])[:40] if str(t).strip()]
        settings = d.get('settings') if isinstance(d.get('settings'), dict) else {}

    trail_mult = _num(settings.get('trail_mult'))
    settings = {
        'equity': max(0.0, _num(settings.get('equity')) or 0),
        'risk_pct': min(10.0, max(0.1, _num(settings.get('risk_pct')) or 1.0)),
        # None keeps the engine's adaptive multiple
        'trail_mult': min(6.0, max(1.0, trail_mult)) if trail_mult else None,
    }
    try:
        return jsonify(engine.build_plan(positions, watch, settings))
    except Exception as e:
        return jsonify({'error': f'שגיאה בחישוב התוכנית: {e}'}), 500


@app.route('/')
def index():
    return render_template('index.html')


# ---------- PWA ----------

@app.route('/manifest.json')
def manifest():
    icon = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
            "viewBox='0 0 100 100'%3E%3Crect width='100' height='100' rx='22' "
            "fill='%23f0b429'/%3E%3Ctext x='50' y='63' font-size='38' "
            "font-family='monospace' font-weight='bold' text-anchor='middle' "
            "fill='%23241800'%3EJS%3C/text%3E%3C/svg%3E")
    return jsonify({
        'name': 'Jonathan Stocks', 'short_name': 'JStocks',
        'start_url': '/', 'display': 'standalone',
        'background_color': '#f4f5fa', 'theme_color': '#f0b429',
        'icons': [{'src': icon, 'sizes': '512x512', 'type': 'image/svg+xml',
                   'purpose': 'any'}],
    })


@app.route('/sw.js')
def sw():
    js = ("self.addEventListener('install',e=>self.skipWaiting());"
          "self.addEventListener('activate',e=>self.clients.claim());"
          "self.addEventListener('fetch',e=>{});")
    return Response(js, mimetype='application/javascript')


@app.route('/api/stock/<ticker>')
def get_stock(ticker):
    try:
        hist = yf_chart(ticker, '1d', '3mo')
        if hist.empty:
            return jsonify({'error': 'Ticker not found'}), 404
        close = hist['Close']
        high = hist['High']
        low = hist['Low']
        vol = hist['Volume']
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(span=14).mean()
        loss = (-delta.clip(upper=0)).ewm(span=14).mean()
        rsi = round(float(100 - (100 / (1 + gain.iloc[-1] / (loss.iloc[-1] + 1e-10)))), 1)
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        macd_b = bool(macd.iloc[-1] > signal.iloc[-1])
        tr = (high - low).ewm(span=14).mean()
        atr_pct = round(float(tr.iloc[-1] / close.iloc[-1] * 100), 2)
        ma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        bb_u = ma20 + 2 * std20
        bb_l = ma20 - 2 * std20
        bb_pct = round(float((close.iloc[-1] - bb_l.iloc[-1]) / (bb_u.iloc[-1] - bb_l.iloc[-1] + 1e-10) * 100), 1)
        vol_ratio = round(float(vol.iloc[-1] / vol.mean()), 2)
        price = round(float(close.iloc[-1]), 2)
        prev = round(float(close.iloc[-2]), 2)
        chg = round((price - prev) / prev * 100, 2)
        atr_abs = price * atr_pct / 100
        sc = 0
        if rsi < 35: sc += 3
        elif rsi < 50: sc += 2
        elif rsi > 72: sc -= 3
        elif rsi > 65: sc -= 1
        if macd_b: sc += 2
        else: sc -= 2
        if bb_pct < 20: sc += 2
        elif bb_pct > 85: sc -= 2
        if vol_ratio > 1.4: sc += 1
        if sc >= 4: rec = 'BUY'
        elif sc <= -3: rec = 'SELL'
        else: rec = 'WAIT'
        conf = min(95, max(40, 55 + sc * 7))
        dy, ex, sector, name = 0, None, '', ticker.upper()
        w52l = w52h = None
        try:
            result = yf_summary(ticker, 'assetProfile,summaryDetail,price')
            sector = result.get('assetProfile', {}).get('sector', '')
            name = result.get('price', {}).get('longName', ticker.upper()) or ticker.upper()
            summary = result.get('summaryDetail', {})
            dy = round(float(raw(summary, 'dividendYield') or 0), 4)
            ex = (summary.get('exDividendDate') or {}).get('fmt')
            w52l = raw(summary, 'fiftyTwoWeekLow')
            w52h = raw(summary, 'fiftyTwoWeekHigh')
        except Exception:
            pass
        return jsonify({
            'ticker': ticker.upper(), 'name': name, 'sector': sector,
            'price': price, 'chg': chg, 'rsi': rsi,
            'macd': 'BULLISH' if macd_b else 'BEARISH',
            'atr_pct': atr_pct, 'bb_pct': bb_pct, 'vol_ratio': vol_ratio,
            'rec': rec, 'conf': conf, 'entry': price,
            'target': round(price + 2 * atr_abs, 2),
            'stop': round(price - 1.5 * atr_abs, 2),
            'support': round(float(low.rolling(20).min().iloc[-1]), 2),
            'resistance': round(float(high.rolling(20).max().iloc[-1]), 2),
            'dividend_yield': dy, 'ex_dividend_date': ex,
            'wk52_low': w52l, 'wk52_high': w52h,
            'history': [round(float(p), 2) for p in close.tolist()],
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/chart/<ticker>')
def get_chart(ticker):
    """Candles plus the indicator series the chart draws on top of them."""
    try:
        period = request.args.get('period', '1mo')
        interval, range_ = period_params(period)
        hist = yf_chart(ticker, interval, range_)
        if hist.empty:
            return jsonify({'error': 'No data'}), 404

        close = hist['Close']
        macd_line, macd_sig, _ = engine.macd(close)
        rsi_s = engine.rsi(close)

        def arr(series, digits=4):
            """JSON-safe list: NaN is not valid JSON, so warmup becomes null."""
            out = []
            for v in series.tolist():
                v = float(v)
                out.append(None if math.isnan(v) or math.isinf(v) else round(v, digits))
            return out

        candles = [{'t': idx.strftime('%Y-%m-%d'),
                    'ts': int(idx.timestamp()),
                    'o': round(float(r['Open']), 4), 'h': round(float(r['High']), 4),
                    'l': round(float(r['Low']), 4), 'c': round(float(r['Close']), 4),
                    'v': int(r['Volume'])}
                   for idx, r in hist.iterrows()]
        return jsonify({
            'candles': candles,
            'ma20': arr(close.rolling(20).mean()),
            'ma50': arr(close.rolling(50).mean()),
            'ma200': arr(close.rolling(200).mean()),
            'rsi': arr(rsi_s, 2),
            'macd': arr(macd_line), 'signal': arr(macd_sig),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/news/<ticker>')
def get_news(ticker):
    try:
        r = requests.get('https://query2.finance.yahoo.com/v1/finance/search',
                         headers=HEADERS,
                         params={'q': ticker, 'newsCount': 10},
                         timeout=10)
        news = r.json().get('news', []) if r.ok else []
        return jsonify([{'title': n.get('title', ''), 'link': n.get('link', ''),
                         'publisher': n.get('publisher', ''),
                         'time': n.get('providerPublishTime', 0)}
                        for n in news[:10]])
    except Exception:
        return jsonify([])


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
