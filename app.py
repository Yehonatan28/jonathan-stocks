from flask import Flask, render_template, jsonify, request, session, Response
import os
import math
import time
import sqlite3
import hashlib
import secrets
import pandas as pd
import requests
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

import engine
import news as newsfeed
import market
import storage
import provenance
import marketintel
import scanner
import fundamentals
import ledger
import performance
import riskx
import strategylab
import relative
import pages
import calendars
import alertrules
from quant import indicators as _qi

import mimetypes
mimetypes.add_type('font/woff2', '.woff2')     # some hosts' tables lack it and serve octet-stream

app = Flask(__name__)

# The Render copy times out on the heatmap and keeps a separate SQLite file, so
# accounts made there are lost on every restart. It now forwards every visit,
# path and query included, to the one production site, so old links keep working.
CANONICAL = os.environ.get('CANONICAL_URL', 'https://jonathan-stocks.vercel.app')


@app.before_request
def _forward_retired_host():
    if os.environ.get('RENDER') and not os.environ.get('KEEP_RENDER'):
        from flask import redirect
        qs = request.query_string.decode()
        return redirect(CANONICAL + request.path + ('?' + qs if qs else ''), code=301)
    return None
# Session cookies are signed with this key. The fallback is random per process
# rather than a literal: a constant checked into a public repository lets anyone
# forge a session cookie and sign in as any user. Set SECRET_KEY in the host's
# environment so sessions survive a restart.
# On a serverless host every instance is a separate process, so a random
# fallback would give each one a different key and sign users out at random.
# When SECRET_KEY is absent, derive a stable key from the database token, which
# is already a deployment secret; only with neither is the key random.
def _session_key():
    if os.environ.get('SECRET_KEY'):
        return os.environ['SECRET_KEY'], 'env'
    if os.environ.get('TURSO_AUTH_TOKEN'):
        return hashlib.sha256(b'jonathan-stocks/session/v1:' + os.environ['TURSO_AUTH_TOKEN'].encode()).hexdigest(), 'derived'
    return secrets.token_hex(32), 'random'


app.secret_key, SESSION_KEY_SOURCE = _session_key()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    # Lax still sends the cookie on a normal top-level visit but not on a
    # cross-site POST, which is what a CSRF attempt against these routes is.
    SESSION_COOKIE_SAMESITE='Lax',
    # Set on any real deployment; left off locally so http://localhost works.
    SESSION_COOKIE_SECURE=bool(os.environ.get('VERCEL') or os.environ.get('RENDER')
                               or os.environ.get('FORCE_HTTPS')),
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)

HEADERS = {'User-Agent': 'Mozilla/5.0'}
# Serverless hosts (Vercel) mount a read-only filesystem with only /tmp
# writable, and that directory does not survive a cold start. Registered
# accounts therefore persist only on a host with a real disk; guest mode keeps
# everything in the browser and is unaffected.
DB_PATH = os.environ.get('DB_PATH') or (
    '/tmp/stocks.db' if os.environ.get('VERCEL')
    else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'stocks.db'))

# Content policy. Scripts and styles come only from this site (the chart
# libraries and fonts are vendored); Google Fonts serves the Hebrew face. Inline
# handlers are still used by the legacy modules, hence 'unsafe-inline' for
# scripts, until they move to listeners. News thumbnails come from the
# publishers, so images may load from any https host.
CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: https:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])
SECURITY_HEADERS = {
    'Content-Security-Policy': CSP,
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=()',
    'Cross-Origin-Opener-Policy': 'same-origin',
}


# Versioned static URLs: /static/<path>?v=<content hash>. A changed file gets a new URL, so the
# browser may keep every version for a year without asking again.
_ASSET_V = {}


def asset(path):
    full = os.path.join(app.static_folder, path)
    try:
        mtime = os.path.getmtime(full)
    except OSError:
        return '/static/' + path
    hit = _ASSET_V.get(path)
    if not hit or hit[0] != mtime:
        with open(full, 'rb') as fh:
            hit = (mtime, hashlib.sha256(fh.read()).hexdigest()[:10])
        _ASSET_V[path] = hit
    return f'/static/{path}?v={hit[1]}'


app.jinja_env.globals['asset'] = asset


@app.after_request
def _security_headers(resp):
    for k, v in SECURITY_HEADERS.items():
        resp.headers.setdefault(k, v)
    if app.config['SESSION_COOKIE_SECURE']:
        resp.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
    if request.path.startswith('/static/') and resp.status_code == 200:
        if request.args.get('v') or request.path.startswith(('/static/fonts/', '/static/vendor/')):
            resp.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        else:
            resp.headers['Cache-Control'] = 'public, max-age=3600'
    if request.path.startswith('/api/'):
        resp.headers.setdefault('Cache-Control', 'no-store')
        if resp.is_json:
            for k, v in provenance.headers(request.path, resp.status_code, resp.get_json(silent=True)).items():
                resp.headers[k] = v
    return resp


# Request budget per address for the API. Held per server instance, so on a
# serverless host it is a brake on one client hammering one instance rather
# than an exact global quota; the sign-in throttle below is the strict one.
API_BUDGET = int(os.environ.get('API_BUDGET_PER_MIN', '240'))
_API_HITS = {}


# Structured request log: one JSON line per API request on stdout (the host keeps it). Path and
# status only: no address, no user id, no body, no query values (they can hold portfolio symbols).
import json as _json
import logging as _logging
import uuid as _uuid
from flask import g as _g

_log = _logging.getLogger('jstocks')
if not _log.handlers:
    _h = _logging.StreamHandler()
    _h.setFormatter(_logging.Formatter('%(message)s'))
    _log.addHandler(_h)
    _log.setLevel(_logging.INFO)
    _log.propagate = False


@app.before_request
def _start_timer():
    _g._t0 = time.time()
    _g._rid = _uuid.uuid4().hex[:12]


@app.after_request
def _log_request(resp):
    if request.path.startswith('/api/'):
        _log.info(_json.dumps({'t': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'rid': _g.get('_rid'),
                               'method': request.method, 'path': request.path, 'status': resp.status_code,
                               'ms': round((time.time() - _g.get('_t0', time.time())) * 1000),
                               'data': resp.headers.get('X-Data-Set'), 'data_status': resp.headers.get('X-Data-Status')}))
    resp.headers['X-Request-Id'] = _g.get('_rid', '')
    return resp


@app.errorhandler(Exception)
def _unexpected(exc):
    from werkzeug.exceptions import HTTPException
    if isinstance(exc, HTTPException):
        return exc
    rid = _g.get('_rid') or _uuid.uuid4().hex[:12]
    tb, where = exc.__traceback__, None
    while tb is not None:                   # the innermost frame is where it actually failed
        where = f'{os.path.basename(tb.tb_frame.f_code.co_filename)}:{tb.tb_frame.f_code.co_name}:{tb.tb_lineno}'
        tb = tb.tb_next
    _log.error(_json.dumps({'t': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'rid': rid, 'path': request.path,
                            'error': type(exc).__name__, 'where': where}))
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Something went wrong on the server. It has been logged.', 'request_id': rid}), 500
    return Response('Something went wrong. It has been logged (' + rid + ').', status=500, mimetype='text/plain')


@app.before_request
def _api_budget():
    if not request.path.startswith('/api/') or request.path == '/api/health':
        return None
    ip, now = _client_ip(), time.time()
    hits = [t for t in _API_HITS.get(ip, []) if t > now - 60]
    if len(hits) >= API_BUDGET:
        _API_HITS[ip] = hits
        resp = jsonify({'error': 'Too many requests. Slow down and try again in a minute.'})
        resp.headers['Retry-After'] = '60'
        return resp, 429
    hits.append(now)
    _API_HITS[ip] = hits
    if len(_API_HITS) > 5000:            # bound the table on a long-lived process
        for k in [k for k, v in _API_HITS.items() if not v or v[-1] < now - 60]:
            _API_HITS.pop(k, None)
    return None


# simple in-memory cache {key: (expires_at, data)}
_CACHE = {}


def cache_get(key):
    v = _CACHE.get(key)
    if v and v[0] > time.time():
        provenance.note(v[2])
        return v[1]
    return None


def cache_set(key, data, ttl=300):
    _CACHE[key] = (time.time() + ttl, data, time.time())


def db():
    """Turso in production (TURSO_DATABASE_URL + TURSO_AUTH_TOKEN), a SQLite file otherwise."""
    return storage.connect(DB_PATH)


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
    CREATE TABLE IF NOT EXISTS transactions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        type TEXT NOT NULL,
        date TEXT NOT NULL,
        ticker TEXT,
        qty REAL,
        price REAL,
        fee REAL,
        amount REAL,
        ratio REAL,
        currency TEXT NOT NULL DEFAULT 'USD',
        note TEXT DEFAULT '',
        created_at TEXT);
    CREATE INDEX IF NOT EXISTS transactions_user ON transactions(user_id, date);
    CREATE TABLE IF NOT EXISTS login_fails(
        ip TEXT NOT NULL,
        t REAL NOT NULL);
    CREATE INDEX IF NOT EXISTS login_fails_ip ON login_fails(ip, t);
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


# Password storage. SHA-256 with one shared salt was a single fast hash over
# every account: a rainbow table built once breaks all of them, and a GPU tries
# billions a second. PBKDF2 gives each account its own random salt and a work
# factor, both stored alongside the digest so they can be raised later without
# invalidating anyone.
PBKDF2_ROUNDS = 240_000
LEGACY_SALT = 'js-salt-'


def hash_pw(pw, salt=None, rounds=PBKDF2_ROUNDS):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', pw.encode(), salt.encode(), rounds)
    return f'pbkdf2${rounds}${salt}${digest.hex()}'


def verify_pw(pw, stored):
    """True when the password matches. Also reports whether the stored form is
    outdated, so a legacy account upgrades silently on the next sign-in."""
    if not stored:
        return False, False
    if stored.startswith('pbkdf2$'):
        try:
            _, rounds, salt, _ = stored.split('$', 3)
            rounds = int(rounds)
        except ValueError:
            return False, False
        ok = secrets.compare_digest(hash_pw(pw, salt, rounds), stored)
        return ok, ok and rounds < PBKDF2_ROUNDS
    # pre-PBKDF2 account: verify the old way, then ask the caller to re-hash
    legacy = hashlib.sha256((LEGACY_SALT + pw).encode()).hexdigest()
    ok = secrets.compare_digest(legacy, stored)
    return ok, ok


def _num(v):
    """Coerce user input to a float, or None when it is blank/unparsable."""
    if v is None or v == '':
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# Sign-in throttle. Without one, a weak password is only as safe as how fast an
# attacker can POST. Failures are recorded in the database, keyed per source
# address, so every server instance enforces the same count; if the database
# cannot be reached the in-memory copy still applies.
_LOGIN_FAILS = {}
LOGIN_MAX_FAILS = 8
LOGIN_WINDOW = 600


def _client_ip():
    fwd = request.headers.get('X-Forwarded-For', '')
    return (fwd.split(',')[0].strip() if fwd else request.remote_addr) or 'unknown'


def _ip_key(ip):
    # the address itself is not stored, only a keyed hash of it
    return hashlib.sha256((app.secret_key + '|' + ip).encode()).hexdigest()[:32]


def _login_blocked(ip):
    since = time.time() - LOGIN_WINDOW
    fails = [t for t in _LOGIN_FAILS.get(ip, []) if t > since]
    _LOGIN_FAILS[ip] = fails
    try:
        conn = db()
        n = conn.execute('SELECT COUNT(*) FROM login_fails WHERE ip=? AND t>?', (_ip_key(ip), since)).fetchone()[0]
        conn.close()
    except Exception:                    # noqa: BLE001
        n = 0
    return max(n, len(fails)) >= LOGIN_MAX_FAILS


def _login_fail(ip):
    _LOGIN_FAILS.setdefault(ip, []).append(time.time())
    try:
        conn = db()
        conn.execute('INSERT INTO login_fails(ip,t) VALUES(?,?)', (_ip_key(ip), time.time()))
        conn.execute('DELETE FROM login_fails WHERE t<?', (time.time() - 86400,))
        conn.commit()
        conn.close()
    except Exception:                    # noqa: BLE001
        pass


def _login_ok(ip):
    _LOGIN_FAILS.pop(ip, None)
    try:
        conn = db()
        conn.execute('DELETE FROM login_fails WHERE ip=?', (_ip_key(ip),))
        conn.commit()
        conn.close()
    except Exception:                    # noqa: BLE001
        pass


def current_user():
    return session.get('user_id')


# ---------- Auth ----------

@app.route('/api/health')
def health():
    """Which storage the deployment uses and whether it answers. No secrets, no user data."""
    ok, err = True, None
    try:
        conn = db()
        conn.execute('SELECT COUNT(*) FROM users').fetchone()
        conn.close()
    except Exception as exc:               # noqa: BLE001
        ok, err = False, type(exc).__name__
    feed = dict(market.FEED)
    return jsonify({'storage': storage.backend(), 'storage_ok': ok, 'error': err,
                    'session_key': SESSION_KEY_SOURCE,
                    'quote_feed': feed, 'sec_configured': '@' in os.environ.get('SEC_CONTACT', ''),
                    'host': 'vercel' if os.environ.get('VERCEL') else 'render' if os.environ.get('RENDER') else 'local'})


@app.route('/api/sources')
def sources():
    """Every dataset the site shows: who publishes it and how fresh it is."""
    return jsonify({'datasets': provenance.catalogue(),
                    'note': 'No dataset here is a real-time exchange feed. Retrieval times are per answer, '
                            'in the X-Data-Retrieved header.'})


@app.route('/api/account/delete', methods=['POST'])
def account_delete():
    """Erase the signed-in account and every row stored under it. The password is asked
    again so a borrowed session cannot do it."""
    uid = current_user()
    if not uid:
        return jsonify({'error': 'Sign in first, then delete the account.'}), 401
    d = request.get_json(silent=True) or {}
    conn = db()
    try:
        row = conn.execute('SELECT password_hash FROM users WHERE id=?', (uid,)).fetchone()
        if not row or not verify_pw(d.get('password') or '', row['password_hash'])[0]:
            return jsonify({'error': 'Wrong password'}), 403
        for table in ('portfolio', 'watchlist', 'alerts', 'pf_history', 'settings', 'transactions'):
            conn.execute(f'DELETE FROM {table} WHERE user_id=?', (uid,))
        conn.execute('DELETE FROM users WHERE id=?', (uid,))
        conn.commit()
    finally:
        conn.close()
    session.clear()
    return jsonify({'ok': True})


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
    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400
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
    ip = _client_ip()
    if _login_blocked(ip):
        return jsonify({'error': 'Too many attempts. Try again in a few minutes.'}), 429
    conn = db()
    row = conn.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
    matched, needs_upgrade = verify_pw(password, row['password_hash']) if row else (False, False)
    if not matched:
        conn.close()
        _login_fail(ip)
        # one message for both cases: saying which half was wrong tells an
        # attacker which emails are registered
        return jsonify({'error': 'Wrong email or password'}), 401
    if needs_upgrade:
        conn.execute('UPDATE users SET password_hash=? WHERE id=?',
                     (hash_pw(password), row['id']))
        conn.commit()
    conn.close()
    _login_ok(ip)
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

# ---------- Ledger: transactions and FIFO accounting ----------
TX_FIELDS = ('type', 'date', 'ticker', 'qty', 'price', 'fee', 'amount', 'ratio', 'currency', 'note')
LEDGER_MAX = 5000


def _user_txs(conn, uid):
    rows = conn.execute('SELECT * FROM transactions WHERE user_id=? ORDER BY date, id', (uid,)).fetchall()
    return [{k: r[k] for k in ('id',) + TX_FIELDS} for r in rows]


def _ledger_prices(txs):
    """Last price of every symbol the transactions leave open (at most 100)."""
    try:
        held = [h['ticker'] for h in ledger.compute(txs)['holdings']][:100]
    except ledger.LedgerError:
        return {}
    if not held:
        return {}
    q = market.batch_quotes(held, per_ticker_fallback=quick_quote)
    return {t: v['price'] for t, v in q.items() if v.get('price') is not None}


@app.route('/api/transactions', methods=['GET', 'POST'])
def transactions():
    uid = current_user()
    if not uid:
        return jsonify({'error': 'Not logged in'}), 401
    conn = db()
    try:
        if request.method == 'GET':
            return jsonify(_user_txs(conn, uid))
        d = request.get_json(silent=True) or {}
        items = d.get('items') if isinstance(d.get('items'), list) else [d]
        if not items or len(items) > 1000:
            return jsonify({'error': 'Send between 1 and 1000 transactions'}), 400
        try:
            cleaned = [ledger.clean(x) for x in items]
        except ledger.LedgerError as exc:
            return jsonify({'error': str(exc)}), 400
        existing = _user_txs(conn, uid)
        if len(existing) + len(cleaned) > LEDGER_MAX:
            return jsonify({'error': f'A ledger holds at most {LEDGER_MAX} transactions'}), 400
        try:
            ledger.compute(existing + cleaned)          # the whole history must still balance
        except ledger.LedgerError as exc:
            return jsonify({'error': str(exc)}), 400
        now = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        for c in cleaned:
            conn.execute('INSERT INTO transactions(user_id,type,date,ticker,qty,price,fee,amount,ratio,currency,note,created_at) '
                         'VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                         (uid, c['type'], c['date'], c.get('ticker'), c.get('qty'), c.get('price'), c.get('fee'),
                          c.get('amount'), c.get('ratio'), c['currency'], c['note'], now))
        conn.commit()
        return jsonify({'ok': True, 'added': len(cleaned)})
    finally:
        conn.close()


@app.route('/api/transactions/<int:tx_id>', methods=['DELETE'])
def transaction_delete(tx_id):
    uid = current_user()
    if not uid:
        return jsonify({'error': 'Not logged in'}), 401
    conn = db()
    try:
        rest = [t for t in _user_txs(conn, uid) if t['id'] != tx_id]
        try:
            ledger.compute(rest)
        except ledger.LedgerError as exc:
            return jsonify({'error': f'Deleting it would leave the history unbalanced ({exc}). Delete the later sale first.'}), 409
        cur = conn.execute('DELETE FROM transactions WHERE id=? AND user_id=?', (tx_id, uid))
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'ok': True})
    finally:
        conn.close()


@app.route('/api/ledger', methods=['GET', 'POST'])
def ledger_view():
    """GET: the signed-in user's ledger. POST: a guest's transactions sent from the browser,
    computed and returned without being stored or logged."""
    if request.method == 'GET':
        uid = current_user()
        if not uid:
            return jsonify({'error': 'Not logged in'}), 401
        conn = db()
        txs = _user_txs(conn, uid)
        conn.close()
    else:
        d = request.get_json(silent=True) or {}
        txs = d.get('transactions')
        if not isinstance(txs, list) or len(txs) > LEDGER_MAX:
            return jsonify({'error': f'Send a list of at most {LEDGER_MAX} transactions'}), 400
    try:
        out = ledger.compute(txs, _ledger_prices(txs))
    except ledger.LedgerError as exc:
        return jsonify({'error': str(exc)}), 400
    out['ok'] = True
    return jsonify(out)


def _range_for(start):
    span = (datetime.utcnow().date() - start).days
    return '1y' if span <= 350 else '2y' if span <= 715 else '5y' if span <= 1800 else '10y' if span <= 3600 else 'max'


@app.route('/api/performance', methods=['GET', 'POST'])
def performance_view():
    """Time-weighted performance of the account currency against SPY. GET for the account,
    POST for a guest's transactions (computed, not stored)."""
    if request.method == 'GET':
        uid = current_user()
        if not uid:
            return jsonify({'error': 'Not logged in'}), 401
        conn = db()
        txs = _user_txs(conn, uid)
        conn.close()
        currency = request.args.get('currency', 'USD')
    else:
        d = request.get_json(silent=True) or {}
        txs, currency = d.get('transactions'), d.get('currency', 'USD')
        if not isinstance(txs, list) or len(txs) > LEDGER_MAX:
            return jsonify({'error': f'Send a list of at most {LEDGER_MAX} transactions'}), 400
    currency = str(currency or 'USD').upper()[:3]
    try:
        cleaned = [ledger.clean(t) for t in txs]
    except ledger.LedgerError as exc:
        return jsonify({'error': str(exc)}), 400
    mine = [t for t in cleaned if t['currency'] == currency]
    if not mine:
        return jsonify({'ok': False, 'reason': f'No {currency} transactions yet.'})
    start = min(datetime.strptime(t['date'], '%Y-%m-%d').date() for t in mine)
    rng = _range_for(start)
    symbols = sorted({t['ticker'] for t in mine if t.get('ticker') and t['type'] in ('buy', 'sell')})[:30]

    def pull(sym):
        key = f'perf:{sym}:{rng}'
        hit = cache_get(key)
        if hit is not None:
            return sym, hit
        try:
            pts = marketintel.to_points(yf_chart(sym, '1d', rng))
        except Exception:                    # noqa: BLE001
            pts = []
        if pts:
            cache_set(key, pts, 3 * 3600)
        return sym, pts
    with ThreadPoolExecutor(max_workers=12) as ex:
        got = dict(ex.map(pull, symbols + ['SPY', '^IRX']))
    bench, irx = got.pop('SPY'), got.pop('^IRX')
    if not bench:
        return jsonify({'ok': False, 'reason': 'Benchmark history is unavailable right now.'}), 503
    in_period = [c for d_, c in irx if d_ >= start]
    rf = round(sum(in_period) / len(in_period), 3) if in_period else None
    if rf is not None and not 0 <= rf <= 25:
        rf = None                            # not a plausible bill yield in percent; do not use it
    try:
        out = performance.compute(txs, got, bench, currency=currency, rf_annual=rf)
    except ledger.LedgerError as exc:
        return jsonify({'error': str(exc)}), 400
    out['benchmark'] = 'SPY (S&P 500 fund)'
    out['rf_source'] = ('average 13-week US Treasury bill yield over the period' if rf is not None
                        else 'not available, so zero')
    return jsonify(out)


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
        try:
            alertrules.parse(cond, price)
        except alertrules.RuleError as exc:
            conn.close()
            return jsonify({'error': str(exc)}), 400
        if not ticker or len(ticker) > 15:
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


def member_quote(ticker):
    """One symbol's quote fields from a year of daily bars (the per-symbol chart endpoint answers
    from the host when the batch endpoints are refused)."""
    try:
        q = market.bars_summary(yf_chart(ticker, '1d', '1y'))
    except Exception:                        # noqa: BLE001
        q = None
    return q or {'price': None}


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


# ---------- Market-wide: Fear & Greed, sector heatmap ----------

@app.route('/api/feargreed')
def feargreed():
    """CNN's own index, not a local approximation of it."""
    return jsonify(market.fear_greed())


def index_quotes(index):
    """Batch quotes for every member of an index, shared by the heatmap, breadth and the
    scanner so one page load does not fetch the same 500 quotes three times."""
    key = 'iq:' + index.lower()
    hit = cache_get(key)
    if hit is not None:
        return hit
    rows = market.constituents(index)
    tickers = [r['ticker'] for r in rows]
    quotes = market.batch_quotes(tickers, per_ticker_fallback=member_quote)
    # trend fields the quote feed did not supply come from a year of daily closes
    lacking = [t for t, q in quotes.items() if q.get('dma200') is None or q.get('hi52') is None]
    if lacking:
        try:
            trend = market.trend_fields(lacking)
        except Exception:                    # noqa: BLE001
            trend = {}
        for t in lacking:
            for k, v in (trend.get(t) or {}).items():
                if quotes[t].get(k) is None:
                    quotes[t][k] = v
    # valuation per share from SEC filings when the quote feed has none: last full-year EPS and dividends
    if any(q.get('pe') is None for q in quotes.values()) and '@' in os.environ.get('SEC_CONTACT', ''):
        try:
            ps = fundamentals.annual_per_share()
        except Exception:                    # noqa: BLE001
            ps = {}
        for t, q in quotes.items():
            f = ps.get(t) or ps.get(t.replace('.', '-')) or {}
            px = q.get('price')
            if px and q.get('pe') is None and f.get('eps') and f['eps'] > 0:
                q['pe'], q['pe_basis'] = round(px / f['eps'], 1), f'FY{f["eps_year"]} EPS (SEC)'
            if px and q.get('div_yield') is None and f.get('dps') is not None:
                q['div_yield'], q['dy_basis'] = round(f['dps'] / px * 100, 2), f'FY{f["dps_year"]} dividends (SEC)'
    if quotes:
        cache_set(key, quotes, 300)
    return quotes


def index_rows(index):
    """Members merged with their quotes; a member without a price is left out."""
    quotes = index_quotes(index)
    out = []
    for r in market.constituents(index):
        q = quotes.get(r['ticker'])
        if not q or q.get('price') is None:
            continue
        out.append({**r, **{k: v for k, v in q.items() if v is not None}, 'cap': q.get('cap') or r['cap']})
    return out


@app.route('/api/market/breadth')
def market_breadth():
    index = request.args.get('index', 'sp500').lower()
    if index not in ('sp500', 'ndx', 'nasdaq100'):
        return jsonify({'error': 'Unknown index'}), 400
    key = 'br:' + index
    hit = cache_get(key)
    if hit:
        return jsonify(hit)
    rows = index_rows(index)
    if not rows:
        return jsonify({'ok': False, 'error': 'No quotes available right now'}), 503
    out = {'ok': True, 'index': index, **marketintel.breadth(rows)}
    cache_set(key, out, 120)
    return jsonify(out)


@app.route('/api/company/<ticker>')
def company(ticker):
    """Five fiscal years and eight quarters from the company's SEC filings, with ratios."""
    t = ticker.strip().upper()
    if not t or len(t) > 12 or not all(c.isalnum() or c in '.-' for c in t):
        return jsonify({'error': 'Invalid symbol'}), 400
    key = 'co:' + t
    hit = cache_get(key)
    if hit:
        return jsonify(hit)
    try:
        out = fundamentals.report(t)
    except fundamentals.Unavailable as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 503
    if not out:
        return jsonify({'error': f'{t} has no SEC financial statements (funds, foreign issuers and '
                                 'Israeli-listed shares do not file 10-K reports).'}), 404
    cache_set(key, out, 6 * 3600)
    return jsonify(out)


@app.route('/api/scan')
def scan():
    """Every member of the chosen universe with the scanner's fields; filtering is client-side."""
    universe = request.args.get('universe', 'sp500').lower()
    if universe not in ('sp500', 'ndx', 'all'):
        return jsonify({'error': 'Unknown universe'}), 400
    key = 'scan:' + universe
    hit = cache_get(key)
    if hit:
        return jsonify(hit)
    if universe == 'all':
        seen, members, quotes = set(), [], {}
        for ix in ('sp500', 'ndx'):
            quotes.update(index_quotes(ix))
            for m in market.constituents(ix):
                if m['ticker'] not in seen:
                    seen.add(m['ticker'])
                    members.append(m)
    else:
        members, quotes = market.constituents(universe), index_quotes(universe)
    rs = scanner.rows(members, quotes)
    if not rs:
        return jsonify({'ok': False, 'error': 'No quotes available right now'}), 503
    out = {'ok': True, 'universe': universe, 'members': len(members), 'rows': rs,
           'coverage': scanner.coverage(rs),
           'fields': [{'key': k, 'label': l, 'unit': u, 'help': h} for k, l, u, h in scanner.FIELDS],
           'note': 'Quotes are delayed. Valuation fields come from the same quote feed and are missing '
                   'for some names; a missing value never passes a filter.'}
    cache_set(key, out, 120)
    return jsonify(out)


@app.route('/api/market/sectors')
def market_sectors():
    hit = cache_get('sectors')
    if hit:
        return jsonify(hit)
    syms = [s for _n, s in marketintel.SECTOR_ETFS] + [marketintel.BENCHMARK]

    def pull(sym):
        try:
            return sym, marketintel.to_points(yf_chart(sym, '1d', '2y'))
        except Exception:                # noqa: BLE001
            return sym, []
    with ThreadPoolExecutor(max_workers=12) as ex:
        series = dict(ex.map(pull, syms))
    if not series.get(marketintel.BENCHMARK):
        return jsonify({'ok': False, 'error': 'Benchmark history unavailable'}), 503
    out = {'ok': True, **marketintel.sector_table(series),
           'method': 'Sector = its SPDR fund. 1D/1W/1M/3M count 1/5/21/63 trading sessions back; '
                     'YTD from the last close of the previous year. "vs S&P 500" is the difference in '
                     'percentage points against SPY over the same period.'}
    cache_set('sectors', out, 1800)
    return jsonify(out)


@app.route('/api/market/snapshot')
def market_snapshot():
    hit = cache_get('snapshot')
    if hit:
        return jsonify(hit)
    quotes = market.batch_quotes([s for _g, s, _l, _k in marketintel.SNAPSHOT], per_ticker_fallback=member_quote)
    rows = marketintel.snapshot(quotes)
    if not any(r['price'] is not None for r in rows):
        return jsonify({'ok': False, 'error': 'No quotes available right now'}), 503
    out = {'ok': True, 'instruments': rows}
    cache_set('snapshot', out, 60)
    return jsonify(out)


@app.route('/api/heatmap/<index>')
def heatmap(index):
    """Constituents with sector, market cap and live change, for the treemap.

    500 names cannot each have their own request, so quotes come from the
    batch endpoints and only whatever they miss falls back to per-ticker.
    """
    key = 'hm:' + index.lower()
    hit = cache_get(key)
    if hit:
        return jsonify(hit)
    rows = market.constituents(index)
    quotes = index_quotes(index)
    out = []
    for r in rows:
        q = quotes.get(r['ticker'])
        if not q or q.get('price') is None:
            continue          # an unexplained grey block is worse than omitting it
        out.append({**r,
                    'price': q['price'],
                    'chg': q.get('chg'),
                    # live cap when the feed gave one, the static estimate otherwise
                    'cap': q.get('cap') or r['cap'],
                    'state': q.get('state'),
                    'pre_price': q.get('pre_price'), 'pre_chg': q.get('pre_chg'),
                    'post_price': q.get('post_price'), 'post_chg': q.get('post_chg')})
    if not out:
        return jsonify({'index': index.upper(), 'stocks': [], 'sectors': [],
                        'total_cap': 0, 'generated_at': int(time.time()),
                        'error': 'No quotes available right now'})
    total = sum(r['cap'] for r in out) or 1
    sectors = {}
    for r in out:
        sectors.setdefault(r['sector'], []).append(r)
    summary = []
    for name, members in sectors.items():
        cap = sum(m['cap'] for m in members)
        # cap-weighted: an equal-weighted sector move misrepresents the sector
        chg = sum((m['chg'] or 0) * m['cap'] for m in members) / (cap or 1)
        summary.append({'sector': name, 'cap': cap, 'chg': round(chg, 2),
                        'count': len(members), 'weight': round(cap / total * 100, 2)})
    summary.sort(key=lambda s: market.SECTOR_ORDER.index(s['sector'])
                 if s['sector'] in market.SECTOR_ORDER else 99)
    payload = {'index': index.upper(), 'stocks': out, 'sectors': summary,
               'total_cap': total, 'covered': len(out), 'listed': len(rows),
               'generated_at': int(time.time())}
    cache_set(key, payload, 120)
    return jsonify(payload)


@app.route('/api/gaps')
def gaps():
    """Opening gaps across a universe: the index, or your own names."""
    scope = request.args.get('scope', 'sp100')
    try:
        min_pct = max(0.25, min(20.0, float(request.args.get('min', 1.0))))
    except (TypeError, ValueError):
        min_pct = 1.0

    if scope == 'mine':
        uid = current_user()
        if uid:
            conn = db()
            names = [r['ticker'] for r in conn.execute(
                'SELECT DISTINCT ticker FROM portfolio WHERE user_id=?', (uid,))]
            names += [r['ticker'] for r in conn.execute(
                'SELECT ticker FROM watchlist WHERE user_id=?', (uid,))]
            conn.close()
        else:
            names = [t.strip().upper()
                     for t in request.args.get('tickers', '').split(',') if t.strip()]
        names = list(dict.fromkeys(names))
        if not names:
            return jsonify({'gaps': [], 'scanned': 0,
                            'error': 'Add stocks to your portfolio or watchlist first'})
    else:
        # the largest names by default: a gap in a mega cap moves the index
        limit = 100 if scope == 'sp100' else 60
        names = [c['ticker'] for c in market.constituents('sp500')[:limit]]

    key = f'gaps:{scope}:{min_pct}:' + ','.join(sorted(names))[:120]
    hit = cache_get(key)
    if hit:
        return jsonify(hit)
    try:
        found = engine.scan_gaps(names, min_pct=min_pct)
    except Exception as e:
        return jsonify({'gaps': [], 'scanned': 0, 'error': f'Gap scan failed: {e}'}), 500
    payload = {'gaps': found, 'scanned': len(names), 'min_pct': min_pct,
               'up': sum(1 for g in found if g['direction'] == 'up'),
               'down': sum(1 for g in found if g['direction'] == 'down'),
               'generated_at': int(time.time())}
    cache_set(key, payload, 180)
    return jsonify(payload)


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


@app.route('/api/risk/review', methods=['POST'])
def risk_review():
    """Exposure, open risk, sector weights, stop quality and correlation of the holdings.
    Signed in, holdings and equity come from the account; a guest posts them."""
    d = request.get_json(silent=True) or {}
    uid = current_user()
    if uid:
        conn = db()
        positions = [dict(r) for r in conn.execute('SELECT * FROM portfolio WHERE user_id=?', (uid,))]
        row = conn.execute('SELECT equity FROM settings WHERE user_id=?', (uid,)).fetchone()
        conn.close()
        equity = (dict(row) if row else {}).get('equity')
    else:
        positions = _clean_positions(d.get('positions'))
        equity = _num((d.get('settings') or {}).get('equity'))
    positions = positions[:25]
    if not positions:
        return jsonify({'ok': False, 'reason': 'No holdings yet. Add them under Portfolio > Holdings.'})

    def pull(sym):
        try:
            return sym, yf_chart(sym, '1d', '6mo')
        except Exception:                    # noqa: BLE001
            return sym, None
    with ThreadPoolExecutor(max_workers=10) as ex:
        hist = dict(ex.map(pull, sorted({p['ticker'] for p in positions})))
    prices, atrs, closes = {}, {}, {}
    for t, df in hist.items():
        if df is None or len(df) < 2:
            continue
        prices[t] = round(float(df['Close'].iloc[-1]), 2)
        if len(df) >= 15:
            atrs[t] = round(float(_qi.atr(df).iloc[-1]), 4)
        closes[t] = marketintel.to_points(df)
    sectors = {p['ticker']: (market._BY_TICKER.get(p['ticker']) or {}).get('sector') for p in positions}
    out = riskx.review(positions, prices, atrs, sectors, equity, d.get('limits'), closes)
    out['ok'] = True
    return jsonify(out)


@app.route('/api/lab', methods=['POST'])
def strategy_lab():
    """Run a user-defined rule set on one symbol's daily bars. Indicators are computed on the
    full history so the averages are warmed up before the test window starts."""
    d = request.get_json(silent=True) or {}
    t = str(d.get('ticker') or '').strip().upper()
    if not t or len(t) > 15 or not all(ch.isalnum() or ch in '.-^=' for ch in t):
        return jsonify({'error': 'Enter a symbol'}), 400
    try:
        years = int(d.get('years') or 5)
    except (TypeError, ValueError):
        years = 5
    years = min(10, max(1, years))
    try:
        strategylab.clean(d.get('strategy'))
    except strategylab.StrategyError as exc:
        return jsonify({'error': str(exc)}), 400
    key = f'lab:{t}:{"10y" if years > 4 else "5y"}'
    df = cache_get(key)
    if df is None:
        try:
            df = yf_chart(t, '1d', '10y' if years > 4 else '5y')
        except Exception:                    # noqa: BLE001
            return jsonify({'error': f'No daily history for {t} right now'}), 503
        cache_set(key, df, 3 * 3600)
    start = max(0, len(df) - years * 252)
    if len(df) - start < 60:
        return jsonify({'error': 'Not enough history for this window'}), 400
    try:
        out = strategylab.run(df, d.get('strategy'), start_index=start)
    except strategylab.StrategyError as exc:
        return jsonify({'error': str(exc)}), 400
    out['ticker'] = t
    out['warmup_bars'] = start
    return jsonify(out)


@app.route('/api/relative')
def relative_view():
    """Up to 8 symbols compared on shared daily closes, with SPY as the benchmark."""
    raw = [s.strip().upper() for s in (request.args.get('symbols') or '').split(',') if s.strip()]
    syms = list(dict.fromkeys(s for s in raw if len(s) <= 15 and all(ch.isalnum() or ch in '.-^=' for ch in s)))[:8]
    if len(syms) < 2:
        return jsonify({'error': 'Enter at least two symbols'}), 400
    rng = request.args.get('range', '1y')
    if rng not in ('6mo', '1y', '2y', '5y'):
        rng = '1y'

    def pull(sym):
        key = f'rel:{sym}:{rng}'
        hit = cache_get(key)
        if hit is not None:
            return sym, hit
        try:
            p = marketintel.to_points(yf_chart(sym, '1d', rng))
        except Exception:                    # noqa: BLE001
            p = []
        if p:
            cache_set(key, p, 3 * 3600)
        return sym, p
    with ThreadPoolExecutor(max_workers=9) as ex:
        series = dict(ex.map(pull, syms + (['SPY'] if 'SPY' not in syms else [])))
    missing = [s for s in syms if not series.get(s)]
    series = {s: p for s, p in series.items() if p}
    out = relative.compare(series)
    out['missing'] = missing
    out['range'] = rng
    pair = [s.strip().upper() for s in (request.args.get('pair') or '').split(',')][:2]
    if out.get('ok') and len(pair) == 2 and all(p in series for p in pair) and pair[0] != pair[1]:
        out['rolling'] = {'pair': pair, 'window': relative.ROLL, 'points': relative.rolling(series, *pair)}
    return jsonify(out)


@app.route('/api/calendar')
def calendar_view():
    """One day of one calendar: earnings, economicevents or dividends."""
    kind = request.args.get('kind', 'earnings')
    if kind not in calendars.KINDS:
        return jsonify({'error': 'Unknown calendar'}), 400
    try:
        day = datetime.strptime(request.args.get('date', ''), '%Y-%m-%d').date()
    except ValueError:
        day = datetime.utcnow().date()
    key = f'cal:{kind}:{day.isoformat()}'
    hit = cache_get(key)
    if hit is not None:
        return jsonify(hit)
    try:
        rows = calendars.fetch(kind, day)
    except calendars.Unavailable as exc:
        return jsonify({'ok': False, 'error': f'The calendar source did not answer ({exc}).'}), 503
    out = {'ok': True, 'kind': kind, 'date': day.isoformat(), 'rows': rows,
           'method': calendars.__doc__.split('Method (shown to the user as written here):')[1].strip()}
    cache_set(key, out, 6 * 3600)
    return jsonify(out)


def _earnings_days(symbols, horizon):
    """{symbol: trading days until its next report} within the horizon, from the calendar."""
    out = {}
    today = datetime.utcnow().date()
    for i, day in enumerate(calendars.trading_days(today, min(15, horizon + 1))):
        key = f'cal:earnings:{day.isoformat()}'
        hit = cache_get(key)
        if hit is None:
            try:
                hit = {'rows': calendars.fetch('earnings', day)}
                cache_set(key, {'ok': True, 'kind': 'earnings', 'date': day.isoformat(), **hit,
                                'method': calendars.__doc__.split('Method (shown to the user as written here):')[1].strip()}, 6 * 3600)
            except calendars.Unavailable:
                continue
        for r in hit.get('rows', []):
            if r['symbol'] in symbols and r['symbol'] not in out:
                out[r['symbol']] = i
    return out


@app.route('/api/alerts/evaluate', methods=['POST'])
def alerts_evaluate():
    """Check alerts against current data. Signed in, alerts and stops come from the account;
    a guest posts them."""
    d = request.get_json(silent=True) or {}
    uid = current_user()
    if uid:
        conn = db()
        alerts_ = [dict(r) for r in conn.execute('SELECT * FROM alerts WHERE user_id=?', (uid,))]
        positions = [dict(r) for r in conn.execute('SELECT ticker, stop FROM portfolio WHERE user_id=?', (uid,))]
        conn.close()
    else:
        alerts_ = [a for a in (d.get('alerts') or [])[:60] if isinstance(a, dict)]
        positions = _clean_positions(d.get('positions'))
    stops = {}
    for p in positions:
        if p.get('stop'):
            stops[p['ticker']] = max(stops.get(p['ticker'], 0), float(p['stop']))
    valid = []
    for a in alerts_:
        try:
            kind, param, v = alertrules.parse(a.get('condition'), a.get('price'))
        except alertrules.RuleError:
            continue
        a['ticker'] = str(a.get('ticker') or '').upper()[:15]
        if a['ticker']:
            valid.append((a, kind, param, v))
    tickers = sorted({a['ticker'] for a, *_ in valid})[:30]
    periods = {}
    for a, kind, param, _v in valid:
        if param:
            periods.setdefault(a['ticker'], set()).add(param)

    def pull(t):
        try:
            df = yf_chart(t, '1d', '1y')
        except Exception:                    # noqa: BLE001
            return t, None
        if df is None or len(df) < 2:
            return t, None
        c = df['Close']
        q = market.bars_summary(df) or {}
        info = {'price': q.get('price'), 'chg': q.get('chg'), 'closes': [float(c.iloc[-2]), float(c.iloc[-1])],
                'rel_vol': round(q['volume'] / q['avg_vol'], 2) if q.get('volume') and q.get('avg_vol') else None, 'ma': {}}
        if len(df) >= 15:
            info['rsi'] = float(_qi.rsi(c, 14).iloc[-1])
        for p in periods.get(t, ()):
            if len(df) > p:
                m = _qi.sma(c, p)
                info['ma'][p] = [float(m.iloc[-2]), float(m.iloc[-1])]
        return t, info
    with ThreadPoolExecutor(max_workers=10) as ex:
        data = dict(ex.map(pull, tickers))
    horizon = max([int(v) for a, k, p, v in valid if k == 'earnings_within'] or [0])
    earn = _earnings_days(set(tickers), horizon) if horizon else {}
    out = []
    for a, kind, param, v in valid:
        info = dict(data.get(a['ticker']) or {})
        info['earnings_in_days'] = earn.get(a['ticker'])
        info['stop'] = stops.get(a['ticker'])
        r = alertrules.evaluate(a, info)
        out.append({'id': a.get('id'), 'ticker': a['ticker'], 'condition': a['condition'], 'price': a['price'],
                    'label': alertrules.KINDS[kind][0], **r})
    return jsonify({'ok': True, 'results': out, 'checked_at': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
                    'method': alertrules.__doc__.split('Method (shown to the user as written here):')[1].strip()})


@app.route('/api/risk/size', methods=['POST'])
def risk_size():
    d = request.get_json(silent=True) or {}
    try:
        return jsonify({'ok': True, **riskx.size(d.get('equity'), d.get('risk_pct'), d.get('entry'), d.get('stop'),
                                                  d.get('max_position_pct'), 'short' if d.get('side') == 'short' else 'long')})
    except (TypeError, ValueError) as exc:
        return jsonify({'error': str(exc) if str(exc) else 'Enter equity, risk, entry and stop'}), 400


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
                        'error': f'Backtest failed: {e}'}), 500
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
        return jsonify({'error': f'Could not build the plan: {e}'}), 500


@app.route('/')
def index():
    return render_template('index.html')


# ---------- PWA ----------

def _doc(title, body, description, updated=True):
    return render_template('page.html', **pages.page(title, body, request.path, description, updated))


@app.route('/about')
def about_page():
    return _doc('About', pages.ABOUT, 'What Jonathan Stocks does, the principles behind it and how it is built.', updated=False)


@app.route('/privacy')
def privacy_page():
    return _doc('Privacy', pages.PRIVACY, 'What Jonathan Stocks stores, where, and how to delete it.')


@app.route('/terms')
def terms_page():
    return _doc('Terms of use', pages.TERMS, 'The terms for using Jonathan Stocks.')


@app.route('/disclaimer')
def disclaimer_page():
    return _doc('Financial disclaimer', pages.DISCLAIMER, 'Information only, not investment advice.')


@app.route('/methodology')
def methodology_page():
    sections = [
        ('Market breadth and sectors', marketintel.breadth.__doc__ + '\n' + marketintel.returns.__doc__),
        ('Company financials (SEC filings)', fundamentals.__doc__.split('What is extracted, and how:')[1]),
        ('Stock screener', scanner.__doc__),
        ('Transactions and P&L', ledger.__doc__.split('Method (shown to the user as written here):')[1]),
        ('Portfolio performance', performance.__doc__.split('Method (shown to the user as written here):')[1]),
        ('Portfolio risk and sizing', riskx.__doc__.split('Method (shown to the user as written here):')[1]),
        ('Strategy Lab (backtesting)', strategylab.__doc__.split('Method (shown to the user as written here):')[1]),
        ('Compare & Correlate', relative.__doc__.split('Method (shown to the user as written here):')[1]),
    ]
    return _doc('Data & methodology', pages.methodology(provenance.catalogue(), sections),
                'Where every number on Jonathan Stocks comes from and how each one is computed.')


@app.route('/robots.txt')
def robots():
    return Response('User-agent: *\nAllow: /\nAllow: /about\nAllow: /methodology\nDisallow: /api/\n', mimetype='text/plain')


@app.route('/manifest.json')
def manifest():
    return jsonify({
        'name': 'Jonathan Stocks', 'short_name': 'JStocks',
        'description': 'Financial intelligence and portfolio analytics',
        'start_url': '/', 'display': 'standalone',
        'background_color': '#0a0d13', 'theme_color': '#0a0d13',
        'icons': [{'src': '/static/img/icon-512.png', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'any'},
                  {'src': '/static/img/icon-180.png', 'sizes': '180x180', 'type': 'image/png', 'purpose': 'any'},
                  {'src': '/static/img/favicon.svg', 'sizes': 'any', 'type': 'image/svg+xml', 'purpose': 'any'}],
    })


@app.route('/sw.js')
def sw():
    js = ("self.addEventListener('install',e=>self.skipWaiting());"
          "self.addEventListener('activate',e=>self.clients.claim());"
          "self.addEventListener('fetch',e=>{});")
    return Response(js, mimetype='application/javascript')


@app.route('/api/stock/<ticker>')
def get_stock(ticker):
    """The stock card. Every number comes from the shared engine and quant/indicators.py, so the card,
    the command centre and the chart always agree. Facts only: no buy/sell call, no invented confidence."""
    from quant import indicators as qi
    try:
        an = engine.analyze(ticker)
        if not an.get('ok'):
            return jsonify({'error': an.get('error') or 'Ticker not found'}), 404
        df = engine.fetch_daily(an['ticker'])
        close = df['Close']
        _, _, _, pct_b = qi.bollinger(close)
        bb_pct = round(float(pct_b.iloc[-1]) * 100, 1) if pct_b.notna().iloc[-1] else None
        rsi_v, lv = an.get('rsi'), an.get('levels') or {}
        conditions = []
        if rsi_v is not None:
            conditions.append(f"RSI(14) {rsi_v}" + (' · above 70, stretched' if rsi_v > 70 else
                              ' · below 30, oversold zone' if rsi_v < 30 else ''))
        conditions.append('MACD above its signal line' if an.get('macd_up') else 'MACD below its signal line')
        ma = an.get('ma') or {}
        if ma.get('dist200') is not None:
            conditions.append(f"{'Above' if ma['dist200'] >= 0 else 'Below'} the 200-day average ({ma['dist200']:+.1f}%)")
        if an.get('vol_ratio') and an['vol_ratio'] >= 1.5:
            conditions.append(f"Volume ×{an['vol_ratio']} its 20-day average")
        if lv.get('from_high_pct') is not None:
            conditions.append(f"{lv['from_high_pct']:+.1f}% from the 52-week high")
        dy, ex, sector, name = 0, None, '', an['ticker']
        try:
            result = yf_summary(ticker, 'assetProfile,summaryDetail,price')
            sector = result.get('assetProfile', {}).get('sector', '')
            name = result.get('price', {}).get('longName', an['ticker']) or an['ticker']
            summary = result.get('summaryDetail', {})
            dy = round(float(raw(summary, 'dividendYield') or 0), 4)
            ex = (summary.get('exDividendDate') or {}).get('fmt')
        except Exception:
            pass
        last = df.index[-1]
        return jsonify({
            'ticker': an['ticker'], 'name': name, 'sector': sector,
            'price': an['price'], 'chg': an.get('chg_pct'), 'rsi': rsi_v,
            'macd': 'BULLISH' if an.get('macd_up') else 'BEARISH',
            'atr_pct': an.get('atr_pct'), 'bb_pct': bb_pct, 'vol_ratio': an.get('vol_ratio'),
            'regime': an.get('regime'), 'regime_label': an.get('regime_he'),
            # a transparent, rule-based trend score (components in engine._snapshot), not a forecast
            'trend_score': an.get('trend_score'),
            'conditions': conditions,
            'suggested_stop': (an.get('suggested_stop') or {}).get('price') if isinstance(an.get('suggested_stop'), dict) else an.get('suggested_stop'),
            'support': lv.get('support'), 'resistance': lv.get('resistance'),
            'dividend_yield': dy, 'ex_dividend_date': ex,
            'wk52_low': lv.get('wk52_low'), 'wk52_high': lv.get('wk52_high'),
            'history': an.get('history', [])[-63:],
            'meta': {'source': 'Yahoo Finance daily bars', 'status': 'end-of-day / delayed',
                     'as_of': str(getattr(last, 'date', lambda: last)()), 'currency': 'USD'},
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
            'ma50': arr(close.rolling(50).mean()),
            'ma100': arr(close.rolling(100).mean()),
            'ma150': arr(close.rolling(150).mean()),
            'ma200': arr(close.rolling(200).mean()),
            'ma20': arr(close.rolling(20).mean()),
            'rsi': arr(rsi_s, 2),
            'macd': arr(macd_line), 'signal': arr(macd_sig),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/news')
def market_news():
    """Headlines from the RSS feeds, optionally narrowed to your own names."""
    scope = request.args.get('scope', 'all')
    if scope not in ('all', 'us', 'il', 'mine'):
        scope = 'all'
    key = f'news:{scope}'
    extra = []
    if scope == 'mine':
        uid = current_user()
        if uid:
            conn = db()
            extra = [r['ticker'] for r in conn.execute(
                'SELECT DISTINCT ticker FROM portfolio WHERE user_id=?', (uid,))]
            extra += [r['ticker'] for r in conn.execute(
                'SELECT ticker FROM watchlist WHERE user_id=?', (uid,))]
            conn.close()
        else:
            extra = [t.strip().upper()
                     for t in request.args.get('tickers', '').split(',') if t.strip()]
        extra = list(dict.fromkeys(extra))[:6]
        if not extra:
            return jsonify({'items': [], 'failed': [],
                            'error': 'Add stocks to your portfolio or watchlist to see news about them'})
        key = 'news:mine:' + ','.join(sorted(extra))

    hit = cache_get(key)
    if hit:
        return jsonify(hit)
    out = newsfeed.get_news(scope='all' if scope == 'mine' else scope,
                            extra_tickers=extra, limit=45)
    cache_set(key, out, 300 if out['items'] else 60)
    return jsonify(out)


@app.route('/api/news/sources')
def news_sources():
    """Which feeds actually answer from this deployment. The sandbox the
    aggregator was written in blocks all of them, so this is how the list gets
    checked against reality."""
    return jsonify(newsfeed.source_health(request.args.get('ticker', 'AAPL')))


@app.route('/api/news/<ticker>')
def get_news(ticker):
    """Headlines for one symbol, its own feeds first."""
    key = 'news:t:' + ticker.upper()
    hit = cache_get(key)
    if hit:
        return jsonify(hit)
    out = newsfeed.get_news(ticker=ticker, scope='all', limit=30)
    cache_set(key, out, 300 if out['items'] else 60)
    return jsonify(out)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
