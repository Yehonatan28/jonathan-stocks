"""Ledger routes: per-user isolation, balance checks on write and delete, stateless guest mode."""
import app as A


def client(tmp_path, monkeypatch):
    monkeypatch.setattr(A, 'DB_PATH', str(tmp_path / 'l.db'))
    monkeypatch.delenv('TURSO_DATABASE_URL', raising=False)
    A.init_db()
    monkeypatch.setattr(A, '_ledger_prices', lambda txs: {'ABC': 150.0})
    A._API_HITS.clear()
    return A.app


def signup(app, name):
    c = app.test_client()
    assert c.post('/api/auth/register', json={'username': name, 'email': f'{name}@x.com', 'password': 'secret123'}).status_code == 200
    return c


def test_isolation_balance_and_delete_guard(tmp_path, monkeypatch):
    app = client(tmp_path, monkeypatch)
    a, b = signup(app, 'alice'), signup(app, 'bob')
    assert a.post('/api/transactions', json={'items': [
        {'type': 'deposit', 'date': '2024-01-01', 'amount': 1000},
        {'type': 'buy', 'date': '2024-01-02', 'ticker': 'ABC', 'qty': 5, 'price': 100}]}).status_code == 200
    # an oversell is refused and nothing is written
    r = a.post('/api/transactions', json={'type': 'sell', 'date': '2024-01-03', 'ticker': 'ABC', 'qty': 6, 'price': 120})
    assert r.status_code == 400 and 'only 5 held' in r.get_json()['error']
    assert len(a.get('/api/transactions').get_json()) == 2
    # bob sees nothing of alice's, and cannot delete her rows
    assert b.get('/api/transactions').get_json() == []
    buy_id = [t for t in a.get('/api/transactions').get_json() if t['type'] == 'buy'][0]['id']
    assert b.delete(f'/api/transactions/{buy_id}').status_code == 404
    # a sale depends on the buy: deleting the buy is refused until the sale goes
    assert a.post('/api/transactions', json={'type': 'sell', 'date': '2024-01-03', 'ticker': 'ABC', 'qty': 2, 'price': 120}).status_code == 200
    assert a.delete(f'/api/transactions/{buy_id}').status_code == 409
    led = a.get('/api/ledger').get_json()
    assert led['holdings'][0]['qty'] == 3 and led['holdings'][0]['value'] == 450.0
    assert led['sales'][0]['gain'] == 40.0
    assert app.test_client().get('/api/ledger').status_code == 401


def test_guest_ledger_is_computed_not_stored(tmp_path, monkeypatch):
    app = client(tmp_path, monkeypatch)
    c = app.test_client()
    r = c.post('/api/ledger', json={'transactions': [{'type': 'buy', 'date': '2024-01-02', 'ticker': 'ABC', 'qty': 1, 'price': 100}]})
    assert r.status_code == 200 and r.get_json()['holdings'][0]['unrealised'] == 50.0
    conn = A.db()
    assert conn.execute('SELECT COUNT(*) FROM transactions').fetchone()[0] == 0
    conn.close()
    assert c.post('/api/ledger', json={'transactions': 'nope'}).status_code == 400
