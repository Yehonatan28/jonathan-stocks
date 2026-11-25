"""Research assistant: answers questions from the platform's own data, with sources.

Method (shown to the user as written here):
- The server picks the data the question needs (company statements from SEC filings, price and
  trend from daily bars, market breadth and sectors) and labels each item with a source id. Only
  that data, never the open web, is given to the language model (Google Gemini).
- The model is instructed to answer only from that data, to cite the source id of every fact, to
  keep estimates apart from reported results, to say when the data does not contain the answer,
  and never to recommend buying or selling.
- Every number in the answer is then checked against the data that was sent. A number that does
  not appear there, within rounding, is marked as unverified.
- Your holdings are included only when you tick the consent box for that question. Otherwise no
  portfolio data leaves the server.
- Answers can still be wrong. Check anything that matters against the cited source.
"""
import json
import os
import re

import requests

URL = 'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
MODELS = ['gemini-flash-latest', 'gemini-flash-lite-latest']
SYSTEM = (
    'You are the research assistant of Jonathan Stocks, a financial information site. Answer the user\'s question '
    'using ONLY the JSON data under CONTEXT. Rules:\n'
    '1. Every fact or number must come from CONTEXT and be followed by its source id in square brackets, e.g. [SEC:MSFT:FY2024].\n'
    '2. If CONTEXT does not contain what is needed, say so plainly; do not use outside knowledge, do not guess.\n'
    '3. Keep reported results and estimates apart, and name estimates as estimates.\n'
    '4. Never recommend buying, selling or holding, and never predict prices. You describe data.\n'
    '5. Copy numbers exactly as they appear in CONTEXT (you may round to two decimals); do not compute new figures '
    'unless the question asks for a simple difference or ratio, and then show the inputs.\n'
    '6. Answer in the language of the question (Hebrew or English), concisely: a short paragraph or a few bullets.\n'
    'Return JSON: {"answer": "...", "sources": ["ids used"]}.'
)
STOP = {'A', 'I', 'AND', 'THE', 'OR', 'VS', 'IS', 'ARE', 'FOR', 'OF', 'IN', 'ON', 'TO', 'PE', 'EPS', 'FCF', 'ROE', 'ROIC',
        'RSI', 'ATR', 'MACD', 'CEO', 'USA', 'US', 'IT', 'AI', 'ETF', 'YTD', 'GDP', 'CPI', 'FED', 'SEC', 'S', 'P'}
MARKET_WORDS = re.compile(r'\b(market|breadth|sectors?|s&p|index|indices|rates?|yields?|oil|gold|dollar)\b', re.I)
# Hebrew words take prefixes (ה, ב, ל, ו, ש...) so they are matched without word boundaries
MARKET_HE = re.compile(r'(שוק|סקטור|מדד|ריבית|זהב|נפט|דולר|אג"ח)')


class AssistantError(Exception):
    pass


def tickers_in(question, known):
    """Symbols mentioned in the question, in order, that the platform knows. $AAPL and AAPL both count."""
    out = []
    for tok in re.findall(r'\$?\b([A-Z]{1,5}(?:[.-][A-Z])?)\b', question):
        t = tok.upper()
        if t in STOP or t in out:
            continue
        if t in known:
            out.append(t)
    return out[:3]


def wants_market(question):
    return bool(MARKET_WORDS.search(question) or MARKET_HE.search(question))


def flatten_numbers(obj, out=None):
    out = [] if out is None else out
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            flatten_numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            flatten_numbers(v, out)
    elif isinstance(obj, str):
        for m in re.findall(r'-?\d[\d,]*\.?\d*', obj):
            try:
                out.append(float(m.replace(',', '')))
            except ValueError:
                pass
    return out


def _scaled(v):
    """A context value and the forms it is usually written in: as is, in billions/millions, as a percentage."""
    forms = {v}
    a = abs(v)
    if a >= 1e6:
        forms |= {v / 1e9, v / 1e6, v / 1e12}
    if a <= 1.5:
        forms.add(v * 100)
    return forms


def check_numbers(answer, context):
    """Numbers in the answer that are not in the context (within rounding). Years, source ids,
    list markers and small counts are ignored."""
    have = set()
    for v in flatten_numbers(context):
        have |= _scaled(v)
    text = re.sub(r'\[[^\]]*\]', ' ', answer)                       # drop source ids
    unverified = []
    for m in re.finditer(r'(?<![\w.])-?\$?(\d[\d,]*\.?\d*)\s*(%|[BMT]\b|billion|million|trillion)?', text):
        raw = m.group(1).replace(',', '')
        try:
            x = float(raw)
        except ValueError:
            continue
        if x.is_integer() and (1900 <= x <= 2100 or x <= 12):        # years, counts, list numbers
            continue
        tol = max(0.006, abs(x) * 0.006)
        if not any(abs(x - h) <= tol or abs(x - abs(h)) <= tol for h in have):
            unverified.append(m.group(0).strip())
    return list(dict.fromkeys(unverified))


def ask_model(question, context, key, post=None, models=None, timeout=25):
    post = post or requests.post
    body = {'systemInstruction': {'parts': [{'text': SYSTEM}]},
            'contents': [{'role': 'user', 'parts': [{'text': 'CONTEXT:\n' + json.dumps(context, ensure_ascii=False)
                                                     + '\n\nQUESTION:\n' + question}]}],
            'generationConfig': {'temperature': 0.2, 'responseMimeType': 'application/json'}}
    errors = []
    for model in models or MODELS:
        try:
            r = post(URL.format(model=model), json=body, timeout=timeout,
                     headers={'x-goog-api-key': key, 'Content-Type': 'application/json'})
        except requests.RequestException as exc:
            errors.append(f'{model}: {type(exc).__name__}')
            continue
        if r.status_code != 200:
            errors.append(f'{model}: HTTP {r.status_code}')
            continue
        try:
            parts = r.json()['candidates'][0]['content']['parts']
            data = json.loads(''.join(p.get('text', '') for p in parts))
            return {'answer': str(data.get('answer') or '').strip(), 'sources': list(data.get('sources') or []), 'model': model}
        except (KeyError, IndexError, ValueError, TypeError):
            errors.append(f'{model}: unreadable answer')
    raise AssistantError('; '.join(errors) or 'no model answered')


def answer(question, context, key=None, post=None):
    key = key or os.environ.get('GEMINI_API_KEY', '')
    if not key:
        raise AssistantError('The assistant is not configured on this server (no model key).')
    out = ask_model(question, context, key, post=post)
    known = set(context.keys())
    out['sources'] = [s for s in out['sources'] if s in known]
    out['unverified'] = check_numbers(out['answer'], context)
    return out
