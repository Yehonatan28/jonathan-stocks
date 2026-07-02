from flask import Flask, render_template, jsonify, request, session
import os
import sqlite3
import hashlib
import pandas as pd
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'jonathan-stocks-secret-2024-xk9p')

HEADERS = {'User-Agent': 'Mozilla/5.0'}
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'stocks.db')


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
    ''')
    conn.commit()
    conn.close()


init_db()


def hash_pw(pw):
    return hashlib.sha256(('js-salt-' + pw).encode()).hexdigest()


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
        return jsonify({'error': 'שם משתמש קצר מדי'}), 400
    if '@' not in email:
        return jsonify({'error': 'אימייל לא תקין'}), 400
    if len(password) < 6:
        return jsonify({'error': 'סיסמה חייבת להיות לפחות 6 תווים'}), 400
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
        return jsonify({'error': 'משתמש או אימייל כבר קיימים'}), 409
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
        return jsonify({'error': 'אימייל או סיסמה שגויים'}), 401
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
    return jsonify({'error': 'לא מחובר'}), 401


# ---------- Portfolio ----------

@app.route('/api/portfolio', methods=['GET', 'POST'])
def portfolio():
    uid = current_user()
    if not uid:
        return jsonify({'error': 'לא מחובר'}), 401
    conn = db()
    if request.method == 'POST':
        d = request.get_json(silent=True) or {}
        ticker = (d.get('ticker') or '').strip().upper()
        try:
            qty = float(d.get('qty'))
            entry = float(d.get('entry'))
        except (TypeError, ValueError):
            conn.close()
            return jsonify({'error': 'כמות ומחיר חייבים להיות מספרים'}), 400
        if not ticker or qty <= 0 or entry <= 0:
            conn.close()
            return jsonify({'error': 'נתונים לא תקינים'}), 400
        cur = conn.execute(
            'INSERT INTO portfolio(user_id,ticker,qty,entry,notes) VALUES(?,?,?,?,?)',
            (uid, ticker, qty, entry, d.get('notes', '')))
        conn.commit()
        pid = cur.lastrowid
        conn.close()
        return jsonify({'ok': True, 'id': pid})
    rows = conn.execute('SELECT * FROM portfolio WHERE user_id=?', (uid,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/portfolio/<int:pos_id>', methods=['DELETE'])
def portfolio_delete(pos_id):
    uid = current_user()
    if not uid:
        return jsonify({'error': 'לא מחובר'}), 401
    conn = db()
    conn.execute('DELETE FROM portfolio WHERE id=? AND user_id=?', (pos_id, uid))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


# ---------- Watchlist ----------

@app.route('/api/watchlist', methods=['GET'])
def watchlist_get():
    uid = current_user()
    if not uid:
        return jsonify({'error': 'לא מחובר'}), 401
    conn = db()
    rows = conn.execute('SELECT ticker FROM watchlist WHERE user_id=?', (uid,)).fetchall()
    conn.close()
    return jsonify([r['ticker'] for r in rows])


@app.route('/api/watchlist/<ticker>', methods=['POST', 'DELETE'])
def watchlist_mod(ticker):
    uid = current_user()
    if not uid:
        return jsonify({'error': 'לא מחובר'}), 401
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
        return jsonify({'error': 'לא מחובר'}), 401
    conn = db()
    if request.method == 'POST':
        d = request.get_json(silent=True) or {}
        ticker = (d.get('ticker') or '').strip().upper()
        cond = d.get('condition')
        try:
            price = float(d.get('price'))
        except (TypeError, ValueError):
            conn.close()
            return jsonify({'error': 'מחיר לא תקין'}), 400
        if not ticker or cond not in ('above', 'below'):
            conn.close()
            return jsonify({'error': 'נתונים לא תקינים'}), 400
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
        return jsonify({'error': 'לא מחובר'}), 401
    conn = db()
    conn.execute('DELETE FROM alerts WHERE id=? AND user_id=?', (alert_id, uid))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


# ---------- Market data (Yahoo REST) ----------

def yf_chart(ticker, interval, range_):
    r = requests.get(
        f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}',
        headers=HEADERS,
        params={'interval': interval, 'range': range_},
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


def period_params(period):
    return {
        '1d': ('5m', '1d'), '5d': ('15m', '5d'), '1mo': ('1d', '1mo'),
        '3mo': ('1d', '3mo'), '6mo': ('1d', '6mo'), '1y': ('1wk', '1y'),
        '2y': ('1wk', '2y'), '5y': ('1mo', '5y'),
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
    tickers = [t.strip().upper() for t in request.args.get('tickers', '').split(',') if t.strip()][:20]
    if not tickers:
        return jsonify([])
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(quick_quote, tickers))
    return jsonify(results)


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


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/stock/<ticker>')
def get_stock(ticker):
    try:
        hist = yf_chart(ticker, '1d', '3mo')
        if hist.empty:
            return jsonify({'error': 'מניה לא נמצאה'}), 404
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
        try:
            r2 = requests.get(
                f'https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}',
                headers=HEADERS,
                params={'modules': 'assetProfile,summaryDetail,price'},
                timeout=10)
            if r2.ok:
                result = r2.json().get('quoteSummary', {}).get('result', [{}])[0]
                sector = result.get('assetProfile', {}).get('sector', '')
                name = result.get('price', {}).get('longName', ticker.upper()) or ticker.upper()
                summary = result.get('summaryDetail', {})
                dy = round(float(summary.get('dividendYield', {}).get('raw', 0) or 0), 4)
                ex = summary.get('exDividendDate', {}).get('fmt', None)
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
            'history': [round(float(p), 2) for p in close.tolist()],
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/chart/<ticker>')
def get_chart(ticker):
    try:
        period = request.args.get('period', '1mo')
        interval, range_ = period_params(period)
        hist = yf_chart(ticker, interval, range_)
        if hist.empty:
            return jsonify({'error': 'אין נתונים'}), 404
        candles = [{'t': idx.strftime('%Y-%m-%d'),
                    'ts': int(idx.timestamp()),
                    'o': round(float(r['Open']), 2), 'h': round(float(r['High']), 2),
                    'l': round(float(r['Low']), 2), 'c': round(float(r['Close']), 2),
                    'v': int(r['Volume'])}
                   for idx, r in hist.iterrows()]
        close = pd.Series([c['c'] for c in candles])
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(span=14).mean()
        loss = (-delta.clip(upper=0)).ewm(span=14).mean()

        def clean(series):
            return [None if pd.isna(v) else float(v) for v in series]

        rsi = clean((100 - (100 / (1 + gain / (loss + 1e-10)))).round(1))
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd_line = clean((ema12 - ema26).round(4))
        sig_line = clean((ema12 - ema26).ewm(span=9).mean().round(4))
        ma20 = clean(close.rolling(20).mean().round(2))
        return jsonify({'candles': candles, 'rsi': rsi, 'macd': macd_line,
                        'signal': sig_line, 'ma20': ma20})
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
