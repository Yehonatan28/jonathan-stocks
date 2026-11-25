"""Today for your names: each rule at its threshold, holdings-only rules, ordering."""
import digest as D


def test_rules_and_order():
    quotes = {
        'MOVE': {'price': 100, 'chg': -6.5},
        'VOL': {'price': 50, 'chg': 0.2, 'volume': 3_000_000, 'avg_vol': 1_000_000},
        'HIGH': {'price': 99, 'chg': 0.1, 'hi52': 100, 'lo52': 50},
        'LOW': {'price': 51, 'chg': 0.1, 'hi52': 100, 'lo52': 50},
        'STOP': {'price': 102, 'chg': 0.0, 'dma200': 110},
        'QUIET': {'price': 10, 'chg': 1.0, 'hi52': 20, 'lo52': 5},
        'EARN': {'price': 10, 'chg': 0.0},
    }
    holdings = {'STOP': {'stop': 100}, 'QUIET': {'stop': None}}
    items = D.build(list(quotes), quotes, holdings, {'EARN': 0, 'QUIET': 9})
    kinds = [(i['kind'], i['ticker']) for i in items]
    assert kinds[0] == ('stop', 'STOP') and items[0]['text'].startswith('2.00% above its stop')
    assert ('earnings', 'EARN') in kinds and ('move', 'MOVE') in kinds and ('volume', 'VOL') in kinds
    assert ('range', 'HIGH') in kinds and ('range', 'LOW') in kinds and ('trend', 'STOP') in kinds
    assert not any(t == 'QUIET' for _, t in kinds)               # nothing notable, earnings too far
    assert next(i for i in items if i['ticker'] == 'MOVE')['level'] == 'high'
    assert next(i for i in items if i['ticker'] == 'EARN')['text'] == 'reports earnings today'


def test_trend_and_stop_only_for_holdings():
    q = {'W': {'price': 90, 'chg': 0, 'dma200': 100}}
    assert D.build(['W'], q, {}, {}) == []
    assert D.build(['W'], q, {'W': {'stop': 95}}, {})[0]['text'].startswith('at or below its stop')
