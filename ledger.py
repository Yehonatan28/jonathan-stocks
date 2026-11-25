"""Portfolio accounting from a list of transactions.

Method (shown to the user as written here):
- Transactions are applied in date order; on the same date, in the order they were entered.
- Types: deposit and withdrawal move cash; buy adds a lot (quantity, price, fee) and spends
  quantity x price + fee; sell closes lots first-in, first-out and receives quantity x price - fee;
  dividend adds cash and counts as income of that symbol; fee spends cash; split multiplies
  the quantity of every open lot by its ratio and divides their cost per share by it.
- Cost basis of a lot includes its buy fee. A sell's fee reduces that sale's proceeds, so the
  realised gain of a sale = proceeds - fee - cost of the lots it closed.
- Unrealised gain = market value of the open lots at the given price - their cost.
- Selling more than is held is rejected: this ledger does not record short positions.
- Each currency is accounted for on its own; amounts in different currencies are never added
  together, because no exchange rate is applied.
"""
from collections import defaultdict
from datetime import date

TYPES = ('deposit', 'withdrawal', 'buy', 'sell', 'dividend', 'fee', 'split')
EPS = 1e-9


class LedgerError(ValueError):
    """A transaction that cannot be applied; the message names it."""


def _num(x, name, positive=True, allow_zero=False):
    try:
        v = float(x)
    except (TypeError, ValueError):
        raise LedgerError(f'{name} must be a number') from None
    if v != v or v in (float('inf'), float('-inf')):
        raise LedgerError(f'{name} must be a number')
    if positive and (v < 0 or (v == 0 and not allow_zero)):
        raise LedgerError(f'{name} must be {"zero or more" if allow_zero else "more than zero"}')
    return v


def clean(tx):
    """Validate one transaction and return it normalised. Raises LedgerError."""
    t = str(tx.get('type', '')).lower().strip()
    if t not in TYPES:
        raise LedgerError(f'unknown type "{t}"')
    try:
        d = date.fromisoformat(str(tx.get('date', ''))[:10])
    except ValueError:
        raise LedgerError('date must be YYYY-MM-DD') from None
    cur = (str(tx.get('currency') or 'USD').upper().strip() or 'USD')[:3]
    out = {'id': tx.get('id'), 'type': t, 'date': d.isoformat(), 'currency': cur,
           'note': str(tx.get('note') or '')[:200]}
    if t in ('buy', 'sell', 'dividend', 'split'):
        sym = str(tx.get('ticker') or '').upper().strip()
        if not sym or len(sym) > 15 or not all(c.isalnum() or c in '.-^=' for c in sym):
            raise LedgerError('a symbol is required')
        out['ticker'] = sym
    if t in ('buy', 'sell'):
        out['qty'] = _num(tx.get('qty'), 'quantity')
        out['price'] = _num(tx.get('price'), 'price', allow_zero=True)
        out['fee'] = _num(tx.get('fee') or 0, 'fee', allow_zero=True)
    elif t == 'split':
        out['ratio'] = _num(tx.get('ratio'), 'split ratio')
    else:
        out['amount'] = _num(tx.get('amount'), 'amount')
    return out


def compute(transactions, prices=None):
    """transactions: list of dicts; prices: {ticker: last price} in each ticker's own currency.

    Returns holdings, closed sales, cash and totals per currency. Raises LedgerError naming
    the first transaction that cannot be applied."""
    prices = prices or {}
    txs = []
    for i, tx in enumerate(transactions):
        try:
            c = clean(tx)
        except LedgerError as exc:
            raise LedgerError(f'transaction {i + 1}: {exc}') from None
        c['_seq'] = i
        txs.append(c)
    txs.sort(key=lambda x: (x['date'], x['_seq']))

    lots = defaultdict(list)                  # (ticker, currency) -> [[qty, cost_per_share, date]]
    cash = defaultdict(float)
    flows = defaultdict(lambda: {'deposits': 0.0, 'withdrawals': 0.0, 'fees': 0.0})
    income = defaultdict(float)               # (ticker, currency) -> dividends
    realised = defaultdict(float)             # (ticker, currency) -> realised gain
    sales = []

    for tx in txs:
        cur, t = tx['currency'], tx['type']
        key = (tx.get('ticker'), cur)
        where = f"{tx['date']} {t}{' ' + tx['ticker'] if tx.get('ticker') else ''}"
        if t == 'deposit':
            cash[cur] += tx['amount']; flows[cur]['deposits'] += tx['amount']
        elif t == 'withdrawal':
            cash[cur] -= tx['amount']; flows[cur]['withdrawals'] += tx['amount']
        elif t == 'fee':
            cash[cur] -= tx['amount']; flows[cur]['fees'] += tx['amount']
        elif t == 'dividend':
            cash[cur] += tx['amount']; income[key] += tx['amount']
        elif t == 'buy':
            cost = tx['qty'] * tx['price'] + tx['fee']
            cash[cur] -= cost
            flows[cur]['fees'] += tx['fee']
            lots[key].append([tx['qty'], cost / tx['qty'], tx['date']])
        elif t == 'split':
            if not lots[key]:
                raise LedgerError(f'{where}: no open position to split')
            for lot in lots[key]:
                lot[0] *= tx['ratio']
                lot[1] /= tx['ratio']
        elif t == 'sell':
            held = sum(l[0] for l in lots[key])
            if tx['qty'] > held + EPS:
                raise LedgerError(f'{where}: selling {tx["qty"]:g} but only {held:g} held')
            left, basis = tx['qty'], 0.0
            while left > EPS:
                lot = lots[key][0]
                take = min(left, lot[0])
                basis += take * lot[1]
                lot[0] -= take
                left -= take
                if lot[0] <= EPS:
                    lots[key].pop(0)
            proceeds = tx['qty'] * tx['price'] - tx['fee']
            cash[cur] += proceeds
            flows[cur]['fees'] += tx['fee']
            gain = proceeds - basis
            realised[key] += gain
            sales.append({'date': tx['date'], 'ticker': tx['ticker'], 'currency': cur, 'qty': tx['qty'],
                          'proceeds': round(proceeds, 2), 'cost': round(basis, 2), 'gain': round(gain, 2),
                          'return_pct': round(gain / basis * 100, 2) if basis > 0 else None})

    holdings = []
    for (sym, cur), ls in lots.items():
        qty = sum(l[0] for l in ls)
        if qty <= EPS:
            continue
        cost = sum(l[0] * l[1] for l in ls)
        px = prices.get(sym)
        value = qty * px if px is not None else None
        holdings.append({
            'ticker': sym, 'currency': cur, 'qty': round(qty, 6), 'avg_cost': round(cost / qty, 4),
            'cost': round(cost, 2), 'price': px, 'value': round(value, 2) if value is not None else None,
            'unrealised': round(value - cost, 2) if value is not None else None,
            'unrealised_pct': round((value / cost - 1) * 100, 2) if value is not None and cost > 0 else None,
            'realised': round(realised.get((sym, cur), 0.0), 2), 'dividends': round(income.get((sym, cur), 0.0), 2),
            'lots': [{'qty': round(l[0], 6), 'cost_per_share': round(l[1], 4), 'opened': l[2]} for l in ls],
        })
    holdings.sort(key=lambda h: -(h['value'] if h['value'] is not None else h['cost']))

    currencies = sorted(set(cash) | {h['currency'] for h in holdings} | {s['currency'] for s in sales} | {c for _s, c in income})
    totals = {}
    for cur in currencies:
        hs = [h for h in holdings if h['currency'] == cur]
        priced = all(h['value'] is not None for h in hs)
        mv = sum(h['value'] for h in hs) if priced else None
        f = flows[cur]
        totals[cur] = {
            'cash': round(cash[cur], 2),
            'positions_cost': round(sum(h['cost'] for h in hs), 2),
            'positions_value': round(mv, 2) if mv is not None else None,
            'account_value': round(mv + cash[cur], 2) if mv is not None else None,
            'unrealised': round(sum(h['unrealised'] for h in hs), 2) if priced else None,
            'realised': round(sum(v for (s, c), v in realised.items() if c == cur), 2),
            'dividends': round(sum(v for (s, c), v in income.items() if c == cur), 2),
            'deposits': round(f['deposits'], 2), 'withdrawals': round(f['withdrawals'], 2), 'fees': round(f['fees'], 2),
            'net_contributions': round(f['deposits'] - f['withdrawals'], 2),
            'unpriced': [h['ticker'] for h in hs if h['value'] is None],
        }
    return {'holdings': holdings, 'sales': sorted(sales, key=lambda s: s['date'], reverse=True),
            'totals': totals, 'count': len(txs), 'method': __doc__.split('Method (shown to the user as written here):')[1].strip()}
