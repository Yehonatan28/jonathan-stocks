"""Company financials from SEC EDGAR XBRL "company facts" (the numbers in 10-K and 10-Q filings).

Source: https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json, free and official.
The SEC asks every client to identify itself with a contact address in the User-Agent and to
stay under ten requests a second; the contact comes from the SEC_CONTACT environment variable
and nothing is fetched without it.

What is extracted, and how:
- Annual figures: facts from 10-K filings whose period runs 330 to 400 days. When a period was
  reported more than once (a later filing restating it), the latest filing wins.
- Balance-sheet figures: the value at each fiscal year end, from the latest filing reporting it.
- Quarterly income statement: facts from 10-Q filings whose period runs 80 to 100 days. Fourth
  quarters are not filed on their own; Q4 = fiscal year minus Q1-Q3, and is marked derived.
  Quarterly EPS is not derived that way (share counts differ by quarter), so Q4 EPS is empty.
- Several XBRL tags mean the same line (companies choose); each line lists the tags it accepts
  in order of preference, and per period the first tag with a value is used.
Every ratio is computed here from those figures, with its formula in RATIO_DEFS. A ratio
missing any input is None. Nothing is estimated or filled in.
"""
import os
import time
from datetime import date

import requests

TICKERS_URL = 'https://www.sec.gov/files/company_tickers.json'
FACTS_URL = 'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json'

# line -> (label, statement, kind, [tags]); kind: flow (has a period) | instant (balance sheet)
LINES = {
    'revenue': ('Revenue', 'income', 'flow', [
        'RevenueFromContractWithCustomerExcludingAssessedTax', 'Revenues', 'SalesRevenueNet',
        'RevenueFromContractWithCustomerIncludingAssessedTax', 'RevenuesNetOfInterestExpense']),
    'cost_of_revenue': ('Cost of revenue', 'income', 'flow', [
        'CostOfRevenue', 'CostOfGoodsAndServicesSold', 'CostOfGoodsSold']),
    'gross_profit': ('Gross profit', 'income', 'flow', ['GrossProfit']),
    'rnd': ('Research & development', 'income', 'flow', ['ResearchAndDevelopmentExpense']),
    'operating_income': ('Operating income', 'income', 'flow', ['OperatingIncomeLoss']),
    'pretax_income': ('Income before tax', 'income', 'flow', [
        'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest',
        'IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments']),
    'income_tax': ('Income tax', 'income', 'flow', ['IncomeTaxExpenseBenefit']),
    'net_income': ('Net income', 'income', 'flow', ['NetIncomeLoss', 'ProfitLoss']),
    'eps_diluted': ('EPS (diluted)', 'income', 'flow', ['EarningsPerShareDiluted']),
    'shares_diluted': ('Diluted shares', 'income', 'flow', ['WeightedAverageNumberOfDilutedSharesOutstanding']),
    'cash': ('Cash & equivalents', 'balance', 'instant', [
        'CashAndCashEquivalentsAtCarryingValue',
        'CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents']),
    'total_assets': ('Total assets', 'balance', 'instant', ['Assets']),
    'total_liabilities': ('Total liabilities', 'balance', 'instant', ['Liabilities']),
    'equity': ("Shareholders' equity", 'balance', 'instant', [
        'StockholdersEquity', 'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest']),
    # LongTermDebt already includes the current portion; LongTermDebtNoncurrent does not
    'lt_debt': ('Long-term debt (incl. current)', 'balance', 'instant', ['LongTermDebt']),
    'lt_debt_noncurrent': ('Long-term debt (non-current)', 'balance', 'instant', ['LongTermDebtNoncurrent']),
    'lt_debt_current': ('Current portion of long-term debt', 'balance', 'instant', ['LongTermDebtCurrent']),
    'short_debt': ('Short-term borrowings', 'balance', 'instant', ['ShortTermBorrowings', 'CommercialPaper']),
    'cfo': ('Operating cash flow', 'cashflow', 'flow', [
        'NetCashProvidedByUsedInOperatingActivities',
        'NetCashProvidedByUsedInOperatingActivitiesContinuingOperations']),
    'capex': ('Capital expenditure', 'cashflow', 'flow', [
        'PaymentsToAcquirePropertyPlantAndEquipment', 'PaymentsToAcquireProductiveAssets']),
    'buybacks': ('Share repurchases', 'cashflow', 'flow', ['PaymentsForRepurchaseOfCommonStock']),
    'dividends_paid': ('Dividends paid', 'cashflow', 'flow', ['PaymentsOfDividends', 'PaymentsOfDividendsCommonStock']),
    'dps': ('Dividends per share', 'income', 'flow', [
        'CommonStockDividendsPerShareDeclared', 'CommonStockDividendsPerShareCashPaid']),
}
QUARTER_LINES = ['revenue', 'gross_profit', 'operating_income', 'net_income', 'eps_diluted']

RATIO_DEFS = {
    'gross_margin': ('Gross margin', '%', 'gross profit / revenue'),
    'operating_margin': ('Operating margin', '%', 'operating income / revenue'),
    'net_margin': ('Net margin', '%', 'net income / revenue'),
    'revenue_growth': ('Revenue growth', '%', 'revenue / prior-year revenue - 1'),
    'eps_growth': ('EPS growth', '%', 'diluted EPS / prior-year diluted EPS - 1 (only when both are positive)'),
    'fcf': ('Free cash flow', '$', 'operating cash flow - capital expenditure'),
    'fcf_margin': ('FCF margin', '%', 'free cash flow / revenue'),
    'cash_conversion': ('Cash conversion', 'x', 'operating cash flow / net income (only when net income is positive)'),
    'roe': ('Return on equity', '%', 'net income / average of opening and closing equity (only when both are positive)'),
    'roic': ('Return on invested capital', '%',
             'operating income x (1 - effective tax rate) / average of opening and closing (equity + debt - cash); '
             'tax rate = income tax / income before tax, used only between 0 and 50%'),
    'debt_to_equity': ('Debt / equity', 'x', 'reported debt (long-term incl. current portion + short-term borrowings) / equity'),
}

_CIK = {'at': 0, 'map': {}}
_FACTS = {}
FACTS_TTL = 12 * 3600


class Unavailable(Exception):
    """The SEC could not be asked or did not answer; the message says which."""


def _headers():
    contact = os.environ.get('SEC_CONTACT', '').strip()
    if '@' not in contact:
        raise Unavailable('SEC data is not configured on this server (no contact address set).')
    return {'User-Agent': f'Jonathan Stocks research {contact}', 'Accept-Encoding': 'gzip'}


def _get(url, timeout=20):
    try:
        r = requests.get(url, headers=_headers(), timeout=timeout)
    except requests.RequestException as exc:
        raise Unavailable(f'SEC did not answer ({type(exc).__name__}).') from exc
    if r.status_code == 404:
        return None
    if not r.ok:
        raise Unavailable(f'SEC answered HTTP {r.status_code}.')
    return r.json()


def cik_for(ticker):
    if time.time() - _CIK['at'] > 86400 or not _CIK['map']:
        raw = _get(TICKERS_URL) or {}
        m = {v['ticker'].upper(): int(v['cik_str']) for v in raw.values()}
        if m:
            _CIK.update(at=time.time(), map=m,
                        names={v['ticker'].upper(): v.get('title') or '' for v in raw.values()})
    t = ticker.upper()
    return _CIK['map'].get(t) or _CIK['map'].get(t.replace('.', '-'))


def company_facts(ticker):
    cik = cik_for(ticker)
    if not cik:
        return None, None
    hit = _FACTS.get(cik)
    if hit and hit[0] > time.time():
        return cik, hit[1]
    data = _get(FACTS_URL.format(cik=cik), timeout=25)
    if data:
        _FACTS[cik] = (time.time() + FACTS_TTL, data)
        if len(_FACTS) > 40:                      # bound memory on a long-lived process
            for k in sorted(_FACTS, key=lambda k: _FACTS[k][0])[:10]:
                _FACTS.pop(k, None)
    return cik, data


# ------------------------------------------------------------------ parsing

def _d(s):
    return date.fromisoformat(s)


def _entries(facts, tag):
    node = (facts.get('facts', {}).get('us-gaap', {}) or {}).get(tag)
    if not node:
        return []
    out = []
    for unit, items in node.get('units', {}).items():
        if unit not in ('USD', 'USD/shares', 'shares'):
            continue
        out.extend(items)
    return out


def _pick(entries, keep):
    """period key -> value, keeping the latest filing per period."""
    best = {}
    for x in entries:
        k = keep(x)
        if k is None or x.get('val') is None:
            continue
        if k not in best or x.get('filed', '') > best[k][0]:
            best[k] = (x.get('filed', ''), x['val'])
    return {k: v for k, (_f, v) in best.items()}


def _flow(facts, tags, lo, hi, forms):
    """{(start, end): value} for periods lasting lo..hi days, first tag with a value wins."""
    out = {}
    for tag in tags:
        def keep(x):
            if x.get('form') not in forms or 'start' not in x:
                return None
            days = (_d(x['end']) - _d(x['start'])).days
            return (x['start'], x['end']) if lo <= days <= hi else None
        for k, v in _pick(_entries(facts, tag), keep).items():
            out.setdefault(k, v)
    return out


def _instant(facts, tags, forms):
    out = {}
    for tag in tags:
        def keep(x):
            return x['end'] if x.get('form') in forms and 'start' not in x else None
        for k, v in _pick(_entries(facts, tag), keep).items():
            out.setdefault(k, v)
    return out


def _div(a, b):
    return a / b if a is not None and b not in (None, 0) else None


def _pct(x):
    return round(x * 100, 2) if x is not None else None


def annual(facts, years=5):
    forms = ('10-K', '10-K/A')
    flows = {k: _flow(facts, tags, 330, 400, forms) for k, (_l, _s, kind, tags) in LINES.items() if kind == 'flow'}
    insts = {k: _instant(facts, tags, forms) for k, (_l, _s, kind, tags) in LINES.items() if kind == 'instant'}
    # fiscal years = the annual periods of net income (every filer reports it), newest last
    periods = sorted(flows['net_income'] or flows['revenue'], key=lambda p: p[1])
    # one period per fiscal year end; a 52/53-week year can leave two starts for one end
    by_end = {}
    for p in periods:
        by_end[p[1]] = p
    periods = [by_end[e] for e in sorted(by_end)][-(years + 1):]   # one extra for growth and averages
    rows = []
    for start, end in periods:
        r = {'fiscal_year': int(end[:4]), 'period_start': start, 'period_end': end}
        for k, v in flows.items():
            r[k] = v.get((start, end))
        for k, v in insts.items():
            r[k] = v.get(end)
        if r['gross_profit'] is None and r['revenue'] is not None and r['cost_of_revenue'] is not None:
            r['gross_profit'] = r['revenue'] - r['cost_of_revenue']
            r['gross_profit_derived'] = True
        rows.append(r)
    for i, r in enumerate(rows):
        _ratios(r, rows[i - 1] if i else None)
    return rows[-years:]


def _debt(r):
    """Reported debt: total long-term debt (or non-current + current portion when only those
    are tagged) plus short-term borrowings. None when no debt line is tagged at all."""
    if r.get('lt_debt') is not None:
        long_term = r['lt_debt']
    elif r.get('lt_debt_noncurrent') is not None or r.get('lt_debt_current') is not None:
        long_term = (r.get('lt_debt_noncurrent') or 0) + (r.get('lt_debt_current') or 0)
    else:
        long_term = None
    if long_term is None and r.get('short_debt') is None:
        return None
    return (long_term or 0) + (r.get('short_debt') or 0)


def _ratios(r, prev):
    rev = r.get('revenue')
    r['gross_margin'] = _pct(_div(r.get('gross_profit'), rev))
    r['operating_margin'] = _pct(_div(r.get('operating_income'), rev))
    r['net_margin'] = _pct(_div(r.get('net_income'), rev))
    r['fcf'] = (r['cfo'] - r['capex']) if r.get('cfo') is not None and r.get('capex') is not None else None
    r['fcf_margin'] = _pct(_div(r['fcf'], rev))
    ni = r.get('net_income')
    r['cash_conversion'] = round(r['cfo'] / ni, 2) if r.get('cfo') is not None and ni and ni > 0 else None
    debt = _debt(r)
    eq = r.get('equity')
    r['debt'] = debt
    r['debt_to_equity'] = round(debt / eq, 2) if debt is not None and eq and eq > 0 else None
    r['revenue_growth'] = r['eps_growth'] = r['roe'] = r['roic'] = None
    if not prev:
        return
    r['revenue_growth'] = _pct(_div(rev, prev.get('revenue')) - 1) if _div(rev, prev.get('revenue')) is not None else None
    e1, e0 = r.get('eps_diluted'), prev.get('eps_diluted')
    if e1 is not None and e0 and e0 > 0 and e1 > 0:
        r['eps_growth'] = _pct(e1 / e0 - 1)
    q0, q1 = prev.get('equity'), eq
    if ni is not None and q0 and q1 and q0 > 0 and q1 > 0:
        r['roe'] = _pct(ni / ((q0 + q1) / 2))
    tax, pre, oi = r.get('income_tax'), r.get('pretax_income'), r.get('operating_income')
    rate = _div(tax, pre) if pre and pre > 0 else None
    d0, d1 = _debt(prev), debt
    c0, c1 = prev.get('cash'), r.get('cash')
    if None not in (oi, rate, q0, q1, d0, d1, c0, c1) and 0 <= rate <= 0.5:
        ic = ((q0 + d0 - c0) + (q1 + d1 - c1)) / 2
        if ic > 0:
            r['roic'] = _pct(oi * (1 - rate) / ic)
            r['tax_rate'] = _pct(rate)


def quarterly(facts, quarters=8):
    q_forms = ('10-Q', '10-Q/A')
    a_forms = ('10-K', '10-K/A')
    out = {}
    for k in QUARTER_LINES:
        tags = LINES[k][3]
        q = _flow(facts, tags, 80, 100, q_forms)
        fy = _flow(facts, tags, 330, 400, a_forms)
        for (s, e), v in q.items():
            out.setdefault(e, {'period_start': s, 'period_end': e, 'derived': False})[k] = v
        if k == 'eps_diluted':
            continue
        # Q4 = fiscal year - the three quarters inside it
        for (fs, fe), fv in fy.items():
            inside = sorted([(s, e, v) for (s, e), v in q.items() if s >= fs and e < fe], key=lambda x: x[1])
            if len(inside) == 3 and inside[0][0] == fs:
                q4_start = inside[-1][1]
                row = out.setdefault(fe, {'period_start': q4_start, 'period_end': fe, 'derived': True})
                if row.get('derived'):
                    row[k] = fv - sum(v for _s, _e, v in inside)
    rows = sorted(out.values(), key=lambda r: r['period_end'])[-quarters:]
    for r in rows:
        for k in QUARTER_LINES:
            r.setdefault(k, None)
        r['gross_margin'] = _pct(_div(r.get('gross_profit'), r.get('revenue')))
        r['operating_margin'] = _pct(_div(r.get('operating_income'), r.get('revenue')))
    return rows


def summary(name, rows):
    """A few factual sentences from the latest two years. No adjectives that the numbers do
    not carry, and no forecast."""
    if not rows:
        return []
    r = rows[-1]
    out = []
    fy = f"fiscal {r['fiscal_year']} (to {r['period_end']})"
    if r.get('revenue') is not None:
        s = f"{name} reported revenue of {_money(r['revenue'])} in {fy}"
        if r.get('revenue_growth') is not None:
            s += f", {'up' if r['revenue_growth'] >= 0 else 'down'} {abs(r['revenue_growth']):.1f}% on the year before"
        out.append(s + '.')
    if r.get('operating_margin') is not None:
        prev = rows[-2].get('operating_margin') if len(rows) > 1 else None
        s = f"Operating margin was {r['operating_margin']:.1f}%"
        if prev is not None:
            s += f" against {prev:.1f}% a year earlier"
        out.append(s + '.')
    if r.get('net_income') is not None:
        out.append(f"Net income was {_money(r['net_income'])}"
                   + (f", diluted EPS {r['eps_diluted']:.2f}" if r.get('eps_diluted') is not None else '') + '.')
    if r.get('fcf') is not None:
        out.append(f"Free cash flow (operating cash flow less capital expenditure) was {_money(r['fcf'])}"
                   + (f", {r['fcf_margin']:.1f}% of revenue" if r.get('fcf_margin') is not None else '') + '.')
    if r.get('debt') is not None and r.get('cash') is not None:
        out.append(f"At year end it held {_money(r['cash'])} in cash and equivalents against {_money(r['debt'])} of reported debt.")
    return out


def _money(v):
    a = abs(v)
    s = f'${a / 1e12:.2f} trillion' if a >= 1e12 else f'${a / 1e9:.2f} billion' if a >= 1e9 else f'${a / 1e6:.1f} million'
    return ('-' if v < 0 else '') + s


def report(ticker):
    """Everything the research page needs, or raises Unavailable."""
    cik, facts = company_facts(ticker)
    if not facts:
        return None
    name = facts.get('entityName') or ticker.upper()
    years = annual(facts)
    quarters = quarterly(facts)
    filings = sorted({(x.get('form'), x.get('filed'), x.get('accn')) for x in _entries(facts, 'NetIncomeLoss')
                      if x.get('form') in ('10-K', '10-Q')}, key=lambda t: t[1] or '')[-6:]
    return {
        'ok': True, 'ticker': ticker.upper(), 'name': name, 'cik': cik,
        'annual': years, 'quarterly': quarters, 'summary': summary(name, years),
        'lines': {k: {'label': l, 'statement': s} for k, (l, s, _k, _t) in LINES.items()},
        'ratios': {k: {'label': l, 'unit': u, 'formula': f} for k, (l, u, f) in RATIO_DEFS.items()},
        'filings': [{'form': f, 'filed': d, 'accession': a,
                     'url': f'https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type={f}'}
                    for f, d, a in reversed(filings)],
        'source': 'SEC EDGAR XBRL company facts (10-K and 10-Q filings)',
        'source_url': FACTS_URL.format(cik=cik),
        'method': __doc__.split('What is extracted, and how:')[1].strip(),
    }


# ------------------------------------------------------------ cross-company frames
FRAMES_URL = 'https://data.sec.gov/api/xbrl/frames/{tax}/{tag}/{unit}/{period}.json'
_FRAMES = {}


def frame(tag, unit, period, tax='us-gaap'):
    """{cik: value} for one fact across every filer, from the SEC's frames service: the value
    from each company's filing that best fits the calendar period (e.g. CY2025 for a year).
    Cached for a day. Raises Unavailable."""
    key = (tax, tag, unit, period)
    hit = _FRAMES.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    data = _get(FRAMES_URL.format(tax=tax, tag=tag, unit=unit, period=period), timeout=25) or {}
    out = {int(r['cik']): r['val'] for r in data.get('data', []) if r.get('cik') and r.get('val') is not None}
    _FRAMES[key] = (time.time() + 86400, out)
    return out


def annual_per_share(today=None):
    """Diluted EPS and dividends per share of the last full calendar year, by ticker, with the
    year used. Companies missing from the latest year's frame fall back to the year before."""
    from datetime import date as _date
    y = (today or _date.today()).year - 1
    if not _CIK['map']:
        cik_for('AAPL')                       # fills the ticker map
    by_cik = {}
    for tag, field in (('EarningsPerShareDiluted', 'eps'), ('CommonStockDividendsPerShareDeclared', 'dps')):
        for year in (y, y - 1):
            try:
                vals = frame(tag, 'USD-per-shares', f'CY{year}')
            except Unavailable:
                continue
            for cik, v in vals.items():
                row = by_cik.setdefault(cik, {})
                if field not in row:
                    row[field], row[field + '_year'] = v, year
    out = {}
    for t, cik in _CIK['map'].items():
        if cik in by_cik:
            out[t] = by_cik[cik]
    return out


def _quarters_back(today, n):
    """The n calendar quarters before the one containing today, newest first: [(year, q)]."""
    y, q = today.year, (today.month - 1) // 3 + 1
    out = []
    for _ in range(n):
        q -= 1
        if q == 0:
            y, q = y - 1, 4
        out.append((y, q))
    return out


def shares_outstanding(today=None):
    """Common shares outstanding by ticker, from the cover page of each company's latest 10-Q or
    10-K (dei:EntityCommonStockSharesOutstanding through the SEC frames service), with the
    calendar quarter it was read from. Companies with several share classes report them
    separately and are not in the frame. Each row carries the filer's CIK so the caller can leave
    out two listed classes of one filer and never count a company twice."""
    from datetime import date as _date
    if not _CIK['map']:
        cik_for('AAPL')
    by_cik = {}
    for y, q in _quarters_back(today or _date.today(), 3):
        try:
            vals = frame('EntityCommonStockSharesOutstanding', 'shares', f'CY{y}Q{q}I', tax='dei')
        except Unavailable:
            continue
        for cik, v in vals.items():
            if cik not in by_cik and v:
                by_cik[cik] = {'shares': v, 'period': f'CY{y} Q{q}'}
    return {t: {**by_cik[c], 'cik': c} for t, c in _CIK['map'].items() if c in by_cik}


def sec_names():
    """{ticker: registered company name} from the SEC ticker list (empty until it has been fetched)."""
    return _CIK.get('names') or {}
