"""Printable report: SVG charts and the route with stubbed data."""
import app as A
import report as R


def test_svg_charts():
    s = R.bars_svg(['FY1', 'FY2'], [('Revenue', '#000', [100e9, 120e9]), ('Net income', '#111', [-5e9, 10e9])])
    assert s.startswith('<svg') and s.count('<rect') == 4 and s.count('class="zero"') == 1
    assert 'Revenue, Net income by fiscal year' in s
    assert R.lines_svg(['FY1'], [('x', '#000', [1.0])]) == ''           # one point is not a line
    assert R.bars_svg([], []) == ''


def test_route(monkeypatch):
    rep = {'ticker': 'ABC', 'name': 'ABC Corp', 'cik': 1, 'summary': ['ABC reported revenue of $1.00 billion.'],
           'source': 'SEC EDGAR XBRL company facts', 'source_url': 'https://example',
           'annual': [{'fiscal_year': 2023, 'revenue': 9e8, 'net_income': 1e8, 'fcf': 9e7, 'gross_margin': 50.0,
                       'operating_margin': 20.0, 'net_margin': 11.1, 'eps_diluted': 2.0, 'debt_to_equity': 0.5},
                      {'fiscal_year': 2024, 'revenue': 1e9, 'net_income': 1.2e8, 'fcf': 1e8, 'gross_margin': 52.0,
                       'operating_margin': 21.0, 'net_margin': 12.0, 'eps_diluted': 2.5, 'revenue_growth': 11.11, 'debt_to_equity': 0.4}]}
    monkeypatch.setattr(A.fundamentals, 'report', lambda t: rep if t == 'ABC' else None)
    monkeypatch.setattr(A, 'member_quote', lambda t: {'price': 50.0, 'chg': 1.2, 'hi52': 60.0, 'lo52': 40.0, 'dma50': 48.0, 'dma200': 45.0})
    c = A.app.test_client()
    html = c.get('/report/abc').get_data(as_text=True)
    assert 'ABC Corp' in html and '20.0×' in html and '+11.1%' in html and '<svg' in html and 'not investment advice' in html
    assert c.get('/report/NOPE').status_code == 404 and c.get('/report/<x>').status_code in (400, 404)
