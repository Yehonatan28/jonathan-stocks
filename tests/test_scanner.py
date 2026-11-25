"""Scanner rows: every derived field against a hand calculation, and missing inputs stay missing."""
import scanner as S

M = {'ticker': 'ABC', 'name': 'ABC Corp', 'sector': 'Technology', 'cap': 50}


def test_derived_fields():
    q = {'price': 90.0, 'chg': -1.5, 'cap': 120.04, 'dma50': 100.0, 'dma200': 80.0, 'hi52': 120.0, 'lo52': 60.0,
         'pe': 22.47, 'fpe': 18.04, 'pb': 4.2, 'div_yield': 1.1, 'volume': 3_000_000, 'avg_vol': 1_500_000}
    r = S.row(M, q)
    assert r['vs50'] == -10.0            # 90/100 - 1
    assert r['vs200'] == 12.5            # 90/80 - 1
    assert r['off_high'] == -25.0        # 90/120 - 1
    assert r['range_pos'] == 50.0        # (90-60)/(120-60)
    assert r['rel_vol'] == 2.0
    assert r['pe'] == 22.5 and r['fpe'] == 18.0 and r['cap'] == 120.0


def test_losses_are_not_a_pe_and_missing_stays_missing():
    r = S.row(M, {'price': 10.0, 'chg': 0.0, 'pe': -4.0, 'fpe': -2.0})
    assert r['pe'] is None and r['fpe'] is None
    assert r['vs50'] is None and r['range_pos'] is None and r['rel_vol'] is None
    assert r['cap'] == 50.0              # the static estimate when the feed has none


def test_rows_skip_unpriced_and_coverage_counts():
    rs = S.rows([M, {**M, 'ticker': 'XYZ'}], {'ABC': {'price': 5.0, 'chg': 1.0, 'pe': 10.0}, 'XYZ': {'price': None}})
    assert [r['ticker'] for r in rs] == ['ABC']
    cov = S.coverage(rs)
    assert cov['pe'] == 1 and cov['vs200'] == 0 and cov['price'] == 1
