"""SEC XBRL parsing and ratios, on a hand-built company-facts document in the SEC's own shape."""
import fundamentals as F

FY = [('2021-10-01', '2022-09-30'), ('2022-10-01', '2023-09-30'), ('2023-10-01', '2024-09-30')]


def fx(start, end, val, form='10-K', filed='2024-11-01'):
    x = {'end': end, 'val': val, 'form': form, 'filed': filed, 'accn': 'acc-' + end}
    if start:
        x['start'] = start
    return x


def facts():
    usd = lambda items: {'units': {'USD': items}}
    return {'entityName': 'Example Corp', 'facts': {'us-gaap': {
        # revenue under the newer tag for all years; the 2023 figure was later restated (higher filed date wins)
        'RevenueFromContractWithCustomerExcludingAssessedTax': usd([
            fx(*FY[0], 800), fx(*FY[1], 900, filed='2023-11-01'), fx(*FY[1], 1000, filed='2024-11-01'), fx(*FY[2], 1200),
            # quarters of fiscal 2024, and a six-month figure that must be ignored
            fx('2023-10-01', '2023-12-31', 250, '10-Q'), fx('2024-01-01', '2024-03-31', 300, '10-Q'),
            fx('2024-04-01', '2024-06-30', 310, '10-Q'), fx('2023-10-01', '2024-03-31', 550, '10-Q')]),
        'GrossProfit': usd([fx(*FY[0], 400), fx(*FY[1], 500), fx(*FY[2], 660)]),
        'OperatingIncomeLoss': usd([fx(*FY[0], 160), fx(*FY[1], 200), fx(*FY[2], 300)]),
        'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest':
            usd([fx(*FY[1], 190), fx(*FY[2], 280)]),
        'IncomeTaxExpenseBenefit': usd([fx(*FY[1], 38), fx(*FY[2], 56)]),       # 20% both years
        'NetIncomeLoss': usd([fx(*FY[0], 120), fx(*FY[1], 152), fx(*FY[2], 224),
                              fx('2023-10-01', '2023-12-31', 50, '10-Q'), fx('2024-01-01', '2024-03-31', 55, '10-Q'),
                              fx('2024-04-01', '2024-06-30', 60, '10-Q')]),
        'EarningsPerShareDiluted': {'units': {'USD/shares': [fx(*FY[0], 1.20), fx(*FY[1], 1.50), fx(*FY[2], 2.25)]}},
        'NetCashProvidedByUsedInOperatingActivities': usd([fx(*FY[1], 190), fx(*FY[2], 280)]),
        'PaymentsToAcquirePropertyPlantAndEquipment': usd([fx(*FY[1], 40), fx(*FY[2], 70)]),
        'StockholdersEquity': usd([fx(None, '2022-09-30', 600), fx(None, '2023-09-30', 700), fx(None, '2024-09-30', 900)]),
        'LongTermDebtNoncurrent': usd([fx(None, '2023-09-30', 300), fx(None, '2024-09-30', 280)]),
        'LongTermDebtCurrent': usd([fx(None, '2023-09-30', 20), fx(None, '2024-09-30', 20)]),
        'CashAndCashEquivalentsAtCarryingValue': usd([fx(None, '2023-09-30', 120), fx(None, '2024-09-30', 200)]),
    }}}


def test_annual_lines_and_restatement():
    rows = F.annual(facts())
    assert [r['fiscal_year'] for r in rows] == [2022, 2023, 2024]
    assert rows[1]['revenue'] == 1000                 # restated value, not the first one filed
    assert rows[2]['revenue'] == 1200 and rows[2]['equity'] == 900


def test_ratios_by_hand():
    r = F.annual(facts())[-1]
    assert r['gross_margin'] == 55.0                  # 660/1200
    assert r['operating_margin'] == 25.0              # 300/1200
    assert r['net_margin'] == round(224 / 1200 * 100, 2)
    assert r['revenue_growth'] == 20.0                # 1200/1000
    assert r['eps_growth'] == 50.0                    # 2.25/1.50
    assert r['fcf'] == 210 and r['fcf_margin'] == 17.5
    assert r['cash_conversion'] == 1.25               # 280/224
    assert r['roe'] == round(224 / 800 * 100, 2)      # avg equity (700+900)/2
    assert r['debt'] == 300 and r['debt_to_equity'] == round(300 / 900, 2)
    # ROIC: 300*(1-0.2) / avg((700+320-120), (900+300-200)) = 240 / 950
    assert r['roic'] == round(240 / 950 * 100, 2)


def test_first_year_has_no_growth_and_missing_inputs_stay_none():
    first = F.annual(facts())[0]
    assert first['revenue_growth'] is None and first['roe'] is None
    assert first['fcf'] is None and first['cash_conversion'] is None and first['debt_to_equity'] is None


def test_quarters_and_derived_q4():
    qs = F.quarterly(facts())
    ends = [q['period_end'] for q in qs]
    assert '2024-03-31' in ends and all(q['period_end'] != '2024-03-31' or q['revenue'] == 300 for q in qs)
    q4 = next(q for q in qs if q['period_end'] == '2024-09-30')
    assert q4['derived'] is True
    assert q4['revenue'] == 1200 - (250 + 300 + 310)  # 340
    assert q4['net_income'] == 224 - (50 + 55 + 60)
    assert q4['eps_diluted'] is None                  # never derived by subtraction
    assert not any(q['revenue'] == 550 for q in qs)   # six-month figure excluded


def test_summary_states_facts_only():
    rows = F.annual(facts())
    s = ' '.join(F.summary('Example Corp', rows))
    assert 'up 20.0%' in s and 'Operating margin was 25.0% against 20.0%' in s
    assert 'Free cash flow' in s


def test_negative_eps_has_no_growth():
    f = facts()
    f['facts']['us-gaap']['EarningsPerShareDiluted']['units']['USD/shares'][1]['val'] = -0.5
    r = F.annual(f)[-1]
    assert r['eps_growth'] is None


def test_without_contact_nothing_is_fetched(monkeypatch):
    monkeypatch.delenv('SEC_CONTACT', raising=False)
    F._CIK.update(at=0, map={})
    try:
        F.cik_for('AAPL')
    except F.Unavailable as exc:
        assert 'not configured' in str(exc)
    else:
        raise AssertionError('should not fetch without a contact')
