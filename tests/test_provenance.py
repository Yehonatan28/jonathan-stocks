"""Every data answer says where it came from, how fresh it is, and when it was retrieved."""
import time

import app as A
import provenance as P


def _client():
    return A.app.test_client()


def test_every_data_route_is_registered():
    data_routes = {r.rule.split('<')[0].rstrip('/') for r in A.app.url_map.iter_rules()
                   if r.rule.startswith('/api/') and not r.rule.startswith(('/api/auth', '/api/portfolio', '/api/watchlist',
                                                                            '/api/alerts', '/api/settings', '/api/pf_history',
                                                                            '/api/health', '/api/sources'))}
    missing = sorted(p for p in data_routes if not P.match(p) and not P.match(p + '/x'))
    assert missing == [], missing


def test_cached_answer_reports_original_retrieval_time(monkeypatch):
    A._CACHE.clear()
    t0 = time.time() - 120
    A._CACHE['fg'] = (time.time() + 600, {'score': 40}, t0)
    monkeypatch.setattr(A, 'cache_get', A.cache_get)
    with A.app.test_request_context('/api/feargreed'):
        assert A.cache_get('fg') == {'score': 40}
        h = P.headers('/api/feargreed', 200, {'score': 40})
    assert h['X-Data-Set'] == 'feargreed' and h['X-Data-Status'] == 'delayed'
    assert h['X-Data-Retrieved'] == P.iso(t0)


def test_failed_source_is_marked_unavailable_and_bad_request_is_not():
    with A.app.test_request_context('/api/chart/AAPL'):
        assert P.headers('/api/chart/AAPL', 502, {'error': 'upstream'})['X-Data-Status'] == 'unavailable'
        assert P.headers('/api/chart/AAPL', 200, {'ok': False})['X-Data-Status'] == 'unavailable'
        assert P.headers('/api/chart/NOPE', 404, {'error': 'not found'}) == {}


def test_private_routes_carry_no_provenance():
    r = _client().get('/api/watchlist')
    assert 'X-Data-Set' not in r.headers


def test_sources_catalogue_is_honest():
    j = _client().get('/api/sources').get_json()
    assert {d['status'] for d in j['datasets']} <= {'delayed', 'eod'}
    assert 'real-time' in j['note']
