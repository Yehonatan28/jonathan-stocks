"""The spark fallback (both response shapes, a failed group retried per symbol) and the trend
fields computed from a year of closes."""
import market as M


class R:
    def __init__(self, status, payload):
        self.status_code, self._p = status, payload
        self.ok = status == 200

    def json(self):
        return self._p


def spark_payload(symbols, closes_for):
    return {'spark': {'result': [{'symbol': s, 'response': [{'meta': {'regularMarketTime': 1},
             'indicators': {'quote': [{'close': closes_for(s)}]}}]} for s in symbols]}}


def test_group_failure_is_retried_one_by_one(monkeypatch):
    calls = []

    def get(url, headers=None, timeout=None, params=None):
        syms = params['symbols'].split(',')
        calls.append(syms)
        if 'BAD' in syms:
            return R(404, {})
        return R(200, spark_payload(syms, lambda s: [10.0, 11.0]))
    monkeypatch.setattr(M.requests, 'get', get)
    out = M._quotes_spark(['AAA', 'BAD', 'CCC'])
    assert set(out) == {'AAA', 'CCC'}
    assert out['AAA']['price'] == 11.0 and out['AAA']['chg'] == 10.0
    assert calls[0] == ['AAA', 'BAD', 'CCC'] and ['AAA'] in calls and ['CCC'] in calls


def test_flat_shape_is_read(monkeypatch):
    monkeypatch.setattr(M.requests, 'get', lambda *a, **k: R(200, {'AAA': {'close': [5.0, None, 4.0], 'chartPreviousClose': 5}}))
    out = M._quotes_spark(['AAA'])
    assert out['AAA']['price'] == 4.0 and out['AAA']['chg'] == -20.0


def test_trend_fields_from_closes(monkeypatch):
    closes = [float(i) for i in range(1, 253)]      # 1..252
    monkeypatch.setattr(M.requests, 'get', lambda url, headers=None, timeout=None, params=None:
                        R(200, spark_payload(params['symbols'].split(','), lambda s: closes if s == 'LONG' else closes[:60])))
    M._CACHE.clear()
    f = M.trend_fields(['LONG', 'SHORT'])
    assert f['LONG']['dma50'] == sum(range(203, 253)) / 50
    assert f['LONG']['dma200'] == sum(range(53, 253)) / 200
    assert (f['LONG']['hi52'], f['LONG']['lo52']) == (252.0, 1.0)
    assert 'dma200' not in f['SHORT'] and 'hi52' not in f['SHORT'] and f['SHORT']['dma50'] == sum(range(11, 61)) / 50
