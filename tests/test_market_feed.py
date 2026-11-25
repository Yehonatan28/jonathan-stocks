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


def test_bars_summary_by_hand():
    import pandas as pd
    n = 252
    close = [100.0 + i for i in range(n)]                  # 100 .. 351
    df = pd.DataFrame({'Open': close, 'High': [c + 2 for c in close], 'Low': [c - 3 for c in close],
                       'Close': close, 'Volume': [1000] * (n - 1) + [3000]})
    q = M.bars_summary(df)
    assert q['price'] == 351.0 and q['prev_close'] == 350.0 and q['chg'] == round((351 / 350 - 1) * 100, 2)
    assert q['dma50'] == sum(close[-50:]) / 50 and q['dma200'] == sum(close[-200:]) / 200
    assert q['hi52'] == 353.0 and q['lo52'] == 97.0          # from the bars' highs and lows
    assert q['volume'] == 3000 and q['avg_vol'] == 1000       # today excluded from the average


def test_short_history_leaves_fields_out():
    import pandas as pd
    q = M.bars_summary(pd.DataFrame({'High': [2, 3], 'Low': [1, 1], 'Close': [1.5, 2.5], 'Volume': [10, 20]}))
    assert q['price'] == 2.5 and 'dma50' not in q and 'hi52' not in q and 'avg_vol' not in q


def test_fallback_keeps_every_field_and_breakers_hold(monkeypatch):
    import time
    monkeypatch.setattr(M, '_quotes_v7', lambda t: {})
    monkeypatch.setattr(M, '_quotes_spark', lambda t: {})
    out = M.batch_quotes(['AAA'], per_ticker_fallback=lambda t: {'ticker': t, 'price': 5.0, 'chg': 1.0, 'dma200': 4.0, 'spark': [1]})
    assert out['AAA']['dma200'] == 4.0 and 'spark' not in out['AAA'] and 'ticker' not in out['AAA']
    # a spark outage is remembered, so the next call does not ask again
    monkeypatch.undo()
    calls = []
    monkeypatch.setattr(M.requests, 'get', lambda *a, **k: calls.append(1) or R(503, {}))
    M.FEED.pop('spark_down_until', None)
    M._spark(['A', 'B'], '5d')
    first = len(calls)
    M._spark(['A', 'B'], '5d')
    assert first > 0 and len(calls) == first and M.FEED['spark_down_until'] > time.time()
    M.FEED.pop('spark_down_until', None)
