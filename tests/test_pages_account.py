"""Public pages render with their content, and account deletion erases everything (password required)."""
import app as A


def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(A, 'DB_PATH', str(tmp_path / 'p.db'))
    monkeypatch.delenv('TURSO_DATABASE_URL', raising=False)
    A.init_db()
    A._API_HITS.clear()
    return A.app


def test_pages_render_and_methodology_matches_code(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch).test_client()
    for path, needle in (('/about', 'Provenance on every screen'), ('/privacy', 'Delete your account'),
                         ('/terms', 'not a licensed investment adviser'), ('/disclaimer', 'not investment advice')):
        r = c.get(path)
        assert r.status_code == 200 and needle in r.get_data(as_text=True), path
    m = c.get('/methodology').get_data(as_text=True)
    assert 'first-in, first-out' in m and 'time-weighted' in m and 'next bar' in m.lower() or 'next open' in m
    assert 'SEC EDGAR' in m and 'Wilder' in m
    assert c.get('/robots.txt').get_data(as_text=True).count('Disallow: /api/') == 1


def test_account_delete_needs_password_and_erases_rows(tmp_path, monkeypatch):
    app = setup(tmp_path, monkeypatch)
    c = app.test_client()
    assert c.post('/api/account/delete', json={'password': 'x'}).status_code == 401
    c.post('/api/auth/register', json={'username': 'del', 'email': 'del@x.com', 'password': 'secret123'})
    c.post('/api/watchlist/AAPL')
    c.post('/api/transactions', json={'type': 'deposit', 'date': '2024-01-01', 'amount': 10})
    assert c.post('/api/account/delete', json={'password': 'wrong'}).status_code == 403
    assert c.post('/api/account/delete', json={'password': 'secret123'}).get_json() == {'ok': True}
    conn = A.db()
    counts = [conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in ('users', 'watchlist', 'transactions')]
    conn.close()
    assert counts == [0, 0, 0]
    assert c.get('/api/transactions').status_code == 401              # the session is gone too
    assert app.test_client().post('/api/auth/login', json={'email': 'del@x.com', 'password': 'secret123'}).status_code == 401
