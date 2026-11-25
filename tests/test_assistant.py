"""Assistant: symbol detection, the number validator, and the model call with a fake transport."""
import json

import pytest

import assistant as A

CTX = {'SEC:MSFT:FY2024': {'revenue': 245122000000, 'operating_margin': 44.64, 'eps_diluted': 11.8, 'fiscal_year': 2024},
       'PRICE:MSFT': {'price': 412.35, 'chg': -0.84, 'dma200': 398.1}}


def test_tickers_in_question():
    known = {'MSFT', 'AAPL', 'BRK.B', 'IT'}
    assert A.tickers_in('Compare MSFT and $AAPL margins. Is IT cheap?', known) == ['MSFT', 'AAPL']
    assert A.tickers_in('what about BRK.B', known) == ['BRK.B']
    assert A.wants_market('איך השוק היום?') and A.wants_market('How is market breadth') and not A.wants_market('MSFT margins')


def test_number_validator():
    good = 'Revenue was $245.12 billion in fiscal 2024 [SEC:MSFT:FY2024], operating margin 44.6% [SEC:MSFT:FY2024]; price 412.35.'
    assert A.check_numbers(good, CTX) == []
    bad = 'Operating margin was 47.2% and the price is 412.35 [PRICE:MSFT].'
    assert A.check_numbers(bad, CTX) == ['47.2%']


class R:
    def __init__(self, status, payload):
        self.status_code, self._p = status, payload

    def json(self):
        return self._p


def test_answer_falls_back_and_filters_sources():
    calls = []

    def post(url, json=None, timeout=None, headers=None):
        calls.append(url)
        if 'flash-latest' in url and 'lite' not in url:
            return R(503, {})
        text = '{"answer": "Operating margin was 44.64% [SEC:MSFT:FY2024].", "sources": ["SEC:MSFT:FY2024", "WEB:made-up"]}'
        return R(200, {'candidates': [{'content': {'parts': [{'text': text}]}}]})
    out = A.answer('MSFT margin?', CTX, key='k', post=post)
    assert out['model'] == 'gemini-flash-lite-latest' and len(calls) == 2
    assert out['sources'] == ['SEC:MSFT:FY2024'] and out['unverified'] == []


def test_no_key_and_total_failure():
    with pytest.raises(A.AssistantError, match='not configured'):
        A.answer('q', CTX, key='')
    with pytest.raises(A.AssistantError, match='HTTP 429'):
        A.answer('q', CTX, key='k', post=lambda *a, **k: R(429, {}))


def test_route_consent_and_limits(tmp_path, monkeypatch):
    import app as APP
    monkeypatch.setattr(APP, 'DB_PATH', str(tmp_path / 'a.db'))
    APP.init_db()
    APP._API_HITS.clear(); APP._ASK_HITS.clear()
    seen = {}

    def fake_answer(q, ctx, key=None, post=None):
        seen['ctx'] = ctx
        return {'answer': 'ok', 'sources': [], 'unverified': [], 'model': 'fake'}
    monkeypatch.setattr(APP.assistant, 'answer', fake_answer)
    monkeypatch.setattr(APP, 'member_quote', lambda t: {'price': 10.0, 'chg': 1.0})
    monkeypatch.setattr(APP.fundamentals, 'report', lambda t: None)
    c = APP.app.test_client()
    pos = [{'ticker': 'MSFT', 'qty': 5, 'entry': 300, 'stop': 280}]
    r = c.post('/api/assistant', json={'question': 'How is MSFT doing?', 'positions': pos})
    assert r.get_json()['portfolio_shared'] is False and 'PORTFOLIO' not in seen['ctx'] and 'PRICE:MSFT' in seen['ctx']
    r = c.post('/api/assistant', json={'question': 'How is MSFT doing?', 'positions': pos, 'consent': True})
    assert r.get_json()['portfolio_shared'] is True and seen['ctx']['PORTFOLIO']['positions'][0]['qty'] == 5
    assert c.post('/api/assistant', json={'question': 'x'}).status_code == 400
    for _ in range(8):
        c.post('/api/assistant', json={'question': 'How is MSFT doing?'})
    assert c.post('/api/assistant', json={'question': 'How is MSFT doing?'}).status_code == 429
