"""Printable company report: the Company Research data on one A4-friendly page, with charts
drawn on the server as SVG so they print sharply. Pure functions; the route supplies the data."""
from html import escape


def money(v):
    if v is None:
        return '—'
    a, s = abs(v), '-' if v < 0 else ''
    if a >= 1e12:
        return f'{s}${a / 1e12:.2f}T'
    if a >= 1e9:
        return f'{s}${a / 1e9:.2f}B'
    if a >= 1e6:
        return f'{s}${a / 1e6:.1f}M'
    return f'{s}${a:,.0f}'


def pct(v, signed=False):
    if v is None:
        return '—'
    return (f'{v:+.1f}%' if signed else f'{v:.1f}%')


def bars_svg(labels, series, width=520, height=200):
    """Grouped bars. series: [(name, colour, [values])]. Negative values go below the zero line."""
    vals = [v for _n, _c, vs in series for v in vs if v is not None]
    if not vals or not labels:
        return ''
    top, bot = max(0, max(vals)), min(0, min(vals))
    span = (top - bot) or 1
    pad_l, pad_b, pad_t = 64, 22, 14
    h = height - pad_b - pad_t
    zero_y = pad_t + h * top / span
    gw = (width - pad_l - 8) / len(labels)
    bw = gw * 0.8 / len(series)
    out = [f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" aria-label="{escape(", ".join(n for n, _c, _v in series))} by fiscal year">']
    for k in range(5):
        v = bot + span * k / 4
        y = pad_t + h * (top - v) / span
        out.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width - 4}" y2="{y:.1f}" class="grid"/>'
                   f'<text x="{pad_l - 6}" y="{y + 3:.1f}" text-anchor="end">{escape(money(v))}</text>')
    for i, lab in enumerate(labels):
        x0 = pad_l + gw * i + gw * 0.1
        for j, (_n, colour, vs) in enumerate(series):
            v = vs[i]
            if v is None:
                continue
            y = pad_t + h * (top - max(v, 0)) / span
            hh = abs(v) / span * h
            out.append(f'<rect x="{x0 + j * bw:.1f}" y="{y:.1f}" width="{bw - 2:.1f}" height="{max(hh, 0.5):.1f}" fill="{colour}"/>')
        out.append(f'<text x="{pad_l + gw * i + gw / 2:.1f}" y="{height - 6}" text-anchor="middle">{escape(lab)}</text>')
    out.append(f'<line x1="{pad_l}" y1="{zero_y:.1f}" x2="{width - 4}" y2="{zero_y:.1f}" class="zero"/>')
    out.append('</svg>')
    return ''.join(out)


def lines_svg(labels, series, width=520, height=200):
    """Lines in percent. series: [(name, colour, [values])]."""
    vals = [v for _n, _c, vs in series for v in vs if v is not None]
    if not vals or len(labels) < 2:
        return ''
    top, bot = max(vals), min(min(vals), 0)
    span = (top - bot) or 1
    pad_l, pad_b, pad_t = 40, 22, 14
    h = height - pad_b - pad_t
    step = (width - pad_l - 16) / (len(labels) - 1)
    out = [f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" aria-label="{escape(", ".join(n for n, _c, _v in series))} by fiscal year">']
    for k in range(5):
        v = bot + span * k / 4
        y = pad_t + h * (top - v) / span
        out.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width - 4}" y2="{y:.1f}" class="grid"/>'
                   f'<text x="{pad_l - 6}" y="{y + 3:.1f}" text-anchor="end">{v:.0f}%</text>')
    for i, lab in enumerate(labels):
        out.append(f'<text x="{pad_l + step * i:.1f}" y="{height - 6}" text-anchor="middle">{escape(lab)}</text>')
    for _n, colour, vs in series:
        pts = [(pad_l + step * i, pad_t + h * (top - v) / span) for i, v in enumerate(vs) if v is not None]
        if len(pts) >= 2:
            out.append('<polyline fill="none" stroke="{}" stroke-width="2" points="{}"/>'.format(
                colour, ' '.join(f'{x:.1f},{y:.1f}' for x, y in pts)))
        for x, y in pts:
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" fill="{colour}"/>')
    out.append('</svg>')
    return ''.join(out)


RATIO_ROWS = [('gross_margin', 'Gross margin', False), ('operating_margin', 'Operating margin', False),
              ('net_margin', 'Net margin', False), ('revenue_growth', 'Revenue growth', True),
              ('eps_growth', 'EPS growth', True), ('fcf_margin', 'FCF margin', False), ('roe', 'Return on equity', False),
              ('roic', 'Return on invested capital', False)]


def context(rep, quote, generated):
    """Everything the template needs, already formatted."""
    rows = rep['annual']
    labels = [f"FY{r['fiscal_year']}" for r in rows]
    last = rows[-1] if rows else {}
    px = (quote or {}).get('price')
    pe = px / last['eps_diluted'] if px and last.get('eps_diluted') and last['eps_diluted'] > 0 else None
    lines = lambda keys: [(lab, [money(r.get(k)) if not ratio else (pct(r.get(k), signed) if k != 'debt_to_equity' else
                                (f"{r.get(k):.2f}x" if r.get(k) is not None else '—')) for r in rows])
                          for k, lab, ratio, signed in keys]
    return {
        'rep': rep, 'labels': labels, 'generated': generated,
        'price': px, 'chg': (quote or {}).get('chg'), 'pe': pe,
        'hi52': (quote or {}).get('hi52'), 'lo52': (quote or {}).get('lo52'),
        'dma50': (quote or {}).get('dma50'), 'dma200': (quote or {}).get('dma200'),
        'chart_money': bars_svg(labels, [('Revenue', '#3b6fd8', [r.get('revenue') for r in rows]),
                                         ('Net income', '#1f9d63', [r.get('net_income') for r in rows]),
                                         ('Free cash flow', '#7a68c8', [r.get('fcf') for r in rows])]),
        'chart_margins': lines_svg(labels, [('Gross', '#3b6fd8', [r.get('gross_margin') for r in rows]),
                                            ('Operating', '#1f9d63', [r.get('operating_margin') for r in rows]),
                                            ('Net', '#c08a1e', [r.get('net_margin') for r in rows])]),
        'ratios': [(lab, [pct(r.get(k), signed) for r in rows]) for k, lab, signed in RATIO_ROWS]
                  + [('Debt / equity', [f"{r['debt_to_equity']:.2f}x" if r.get('debt_to_equity') is not None else '—' for r in rows])],
        'income': lines([('revenue', 'Revenue', False, False), ('gross_profit', 'Gross profit', False, False),
                         ('operating_income', 'Operating income', False, False), ('net_income', 'Net income', False, False)])
                  + [('EPS (diluted)', [f"{r['eps_diluted']:.2f}" if r.get('eps_diluted') is not None else '—' for r in rows])],
        'balance': lines([('cash', 'Cash & equivalents', False, False), ('total_assets', 'Total assets', False, False),
                          ('debt', 'Reported debt', False, False), ('equity', "Shareholders' equity", False, False)]),
        'cash': lines([('cfo', 'Operating cash flow', False, False), ('capex', 'Capital expenditure', False, False),
                       ('fcf', 'Free cash flow', False, False), ('buybacks', 'Share repurchases', False, False),
                       ('dividends_paid', 'Dividends paid', False, False)]),
    }
