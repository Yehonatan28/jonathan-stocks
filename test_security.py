"""Security tests: account isolation, credential storage, session cookies.

The question these answer is the one that matters for a portfolio: can anyone
else see the amounts you typed in? Run them with:
    python3 test_security.py
"""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['SECRET_KEY'] = 'test-key'
import app as A
A.DB_PATH = tempfile.mktemp(suffix='.db'); A.init_db()
A.app.config['TESTING'] = True

fails = []
def ok(l, c, x=''):
    print(('  PASS  ' if c else '  FAIL  ') + l + ('' if c else '\n          ' + str(x)))
    if not c: fails.append(l)

victim = A.app.test_client()
victim.post('/api/auth/register', json={'username':'jon','email':'jon@x.com','password':'secret123'})
r = victim.post('/api/portfolio', json={'ticker':'NVDA','qty':500,'entry':120,'stop':110})
pid = r.get_json()['id']
victim.post('/api/settings', json={'equity':250000,'risk_pct':1})
victim.post('/api/watchlist/AMD', json={})

attacker = A.app.test_client()
attacker.post('/api/auth/register', json={'username':'eve','email':'eve@x.com','password':'secret123'})

ok('attacker sees an empty portfolio', attacker.get('/api/portfolio').get_json() == [],
   attacker.get('/api/portfolio').get_json())
ok("attacker cannot read victim's settings",
   attacker.get('/api/settings').get_json().get('equity') in (0, 0.0, None),
   attacker.get('/api/settings').get_json())
ok('attacker sees an empty watchlist', attacker.get('/api/watchlist').get_json() == [])
ok("attacker cannot PATCH victim's position by id",
   attacker.patch(f'/api/portfolio/{pid}', json={'stop': 1}).status_code == 404)
d = attacker.delete(f'/api/portfolio/{pid}')
ok("attacker's DELETE does not remove victim's position",
   len(victim.get('/api/portfolio').get_json()) == 1, d.get_json())
ok("attacker's plan contains no victim positions",
   attacker.post('/api/engine/plan', json={}).get_json()['positions'] == [])

anon = A.app.test_client()
for path in ['/api/portfolio', '/api/settings', '/api/watchlist', '/api/alerts', '/api/pf_history']:
    ok(f'anonymous is rejected from {path}', anon.get(path).status_code == 401)
ok('anonymous PATCH is rejected', anon.patch(f'/api/portfolio/{pid}', json={'stop':1}).status_code == 401)

# --- credential handling
import sqlite3
conn = sqlite3.connect(A.DB_PATH); conn.row_factory = sqlite3.Row
row = dict(conn.execute("SELECT * FROM users WHERE email='jon@x.com'").fetchone())
stored = row['password_hash']
print(f'\n  stored hash: {stored[:70]}...  (len {len(stored)})')
ok('password is not stored in plaintext', 'secret123' not in stored)
ok('password hash is salted per user (not a bare digest)',
   len(stored) > 64 or '$' in stored,
   'a 64-char hex digest means a single static salt — rainbow-table territory')

# --- cookie flags
r = victim.post('/api/auth/login', json={'email':'jon@x.com','password':'secret123'})
cookie = r.headers.get('Set-Cookie', '')
print(f'  Set-Cookie: {cookie[:120]}')
ok('session cookie is HttpOnly', 'HttpOnly' in cookie, cookie)
ok('session cookie sets SameSite', 'SameSite' in cookie, cookie)

ok('wrong password is rejected',
   A.app.test_client().post('/api/auth/login', json={'email':'jon@x.com','password':'wrong'}).status_code == 401)

# --- legacy accounts must keep working and silently upgrade
import hashlib
conn2 = sqlite3.connect(A.DB_PATH)
legacy = hashlib.sha256(('js-salt-' + 'oldpass123').encode()).hexdigest()
conn2.execute("INSERT INTO users(username,email,password_hash) VALUES('old','old@x.com',?)", (legacy,))
conn2.commit(); conn2.close()
c = A.app.test_client()
ok('an account created before the change can still sign in',
   c.post('/api/auth/login', json={'email':'old@x.com','password':'oldpass123'}).status_code == 200)
conn2 = sqlite3.connect(A.DB_PATH); conn2.row_factory = sqlite3.Row
after = conn2.execute("SELECT password_hash FROM users WHERE email='old@x.com'").fetchone()[0]
conn2.close()
ok('and its stored hash is upgraded on that sign-in', after.startswith('pbkdf2$'), after[:40])
ok('the old password still works after the upgrade',
   A.app.test_client().post('/api/auth/login', json={'email':'old@x.com','password':'oldpass123'}).status_code == 200)
ok('a wrong password still fails after the upgrade',
   A.app.test_client().post('/api/auth/login', json={'email':'old@x.com','password':'nope'}).status_code == 401)

# --- brute force throttle
burst = A.app.test_client()
codes = [burst.post('/api/auth/login', json={'email':'jon@x.com','password':'bad%d' % i}).status_code
         for i in range(12)]
ok('repeated failed sign-ins get throttled', 429 in codes, codes)

os.unlink(A.DB_PATH)
print('\n' + ('ALL SECURITY CHECKS PASS' if not fails else f'{len(fails)} FAILED: ' + ', '.join(fails)))
sys.exit(1 if fails else 0)
