/* Jonathan Stocks · Company Research (Equity Research)
   Five fiscal years and eight quarters from the company's SEC filings (/api/company/<t>),
   the market quote beside them (/api/quotes), ratios with their formulas, and a summary made
   only of the reported numbers. Address: #/research?t=MSFT */
(function () {
  'use strict';
  const root = document.getElementById('v-research');
  if (!root) return;
  const e = (t) => String(t == null ? '' : t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const money = (v) => {
    if (v == null) return '—';
    const a = Math.abs(v), s = v < 0 ? '-' : '';
    if (a >= 1e12) return s + (a / 1e12).toFixed(2) + 'T';
    if (a >= 1e9) return s + (a / 1e9).toFixed(2) + 'B';
    if (a >= 1e6) return s + (a / 1e6).toFixed(1) + 'M';
    return s + a.toLocaleString('en-US');
  };
  const pct = (v) => (v == null ? '—' : v.toFixed(1) + '%');
  const sgn = (v) => (v == null ? '—' : (v > 0 ? '+' : '') + v.toFixed(1) + '%');
  const tone = (v) => (v == null ? '' : v > 0 ? 'up' : v < 0 ? 'dn' : '');

  root.innerHTML = `<div class="wrap rs">
    <div class="ph"><h1>Company Research</h1><p>Financial statements as filed with the SEC, five fiscal years and eight quarters, with every ratio's formula.</p></div>
    <form class="rs-search" id="rsForm" autocomplete="off">
      <input id="rsInput" placeholder="Symbol, e.g. MSFT" aria-label="Symbol" maxlength="12" spellcheck="false">
      <button class="btn btn-gold btn-sm" type="submit">Open</button>
      <span class="rs-quick">${['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'JPM', 'KO'].map((t) => `<button type="button" class="chip-btn" data-t="${t}">${t}</button>`).join('')}</span>
    </form>
    <div id="rsBody"><div class="mi-empty">Choose a company. US-listed companies that file 10-K reports are covered; funds and Tel Aviv listings are not.</div></div>
  </div>`;
  const body = document.getElementById('rsBody');
  let charts = [];

  function table(title, rows, lines, fmt, note) {
    const cols = rows.map((r) => `<th class="n">FY${r.fiscal_year}<small>${e(r.period_end)}</small></th>`).join('');
    const trs = lines.map(([key, label, f, cls]) => {
      const vals = rows.map((r) => r[key]);
      if (vals.every((v) => v == null)) return '';
      return `<tr class="${cls || ''}"><td class="nm">${e(label)}</td>${vals.map((v) => `<td class="n ${f === sgn ? tone(v) : ''}">${(f || fmt)(v)}</td>`).join('')}</tr>`;
    }).join('');
    return trs ? `<div class="mi-block"><div class="sec">${e(title)}</div><div class="mi-card rs-tbl"><table class="mi-t"><thead><tr><th>${note ? e(note) : 'USD'}</th>${cols}</tr></thead><tbody>${trs}</tbody></table></div></div>` : '';
  }

  function ratiosTable(d) {
    const rows = d.annual;
    const defs = d.ratios;
    const order = ['gross_margin', 'operating_margin', 'net_margin', 'revenue_growth', 'eps_growth', 'fcf_margin', 'cash_conversion', 'roe', 'roic', 'debt_to_equity'];
    const fmtR = (k, v) => (v == null ? '—' : defs[k].unit === 'x' ? v.toFixed(2) + '×' : ['revenue_growth', 'eps_growth'].includes(k) ? sgn(v) : pct(v));
    const trs = order.map((k) => {
      const vals = rows.map((r) => r[k]);
      if (vals.every((v) => v == null)) return '';
      return `<tr><td class="nm"><span class="tip" tabindex="0" title="${e(defs[k].formula)}">${e(defs[k].label)}</span></td>${vals.map((v) => `<td class="n ${['revenue_growth', 'eps_growth'].includes(k) ? tone(v) : ''}">${fmtR(k, v)}</td>`).join('')}</tr>`;
    }).join('');
    const cols = rows.map((r) => `<th class="n">FY${r.fiscal_year}</th>`).join('');
    return `<div class="mi-block"><div class="sec">Key ratios <span class="tag">COMPUTED FROM FILINGS</span></div>
      <div class="mi-card rs-tbl"><table class="mi-t"><thead><tr><th>Ratio</th>${cols}</tr></thead><tbody>${trs}</tbody></table></div>
      <details class="rs-defs"><summary>How each ratio is computed</summary><dl>${order.map((k) => `<dt>${e(defs[k].label)}</dt><dd>${e(defs[k].formula)}</dd>`).join('')}</dl></details></div>`;
  }

  function quarterTable(qs) {
    if (!qs.length) return '';
    const cols = qs.map((q) => `<th class="n">${e(q.period_end)}${q.derived ? '<small>derived Q4</small>' : '<small>10-Q</small>'}</th>`).join('');
    const line = (k, label, f) => `<tr><td class="nm">${label}</td>${qs.map((q) => `<td class="n">${f(q[k])}</td>`).join('')}</tr>`;
    return `<div class="mi-block"><div class="sec">Quarters <span class="tag">INCOME STATEMENT</span></div>
      <div class="mi-card rs-tbl"><table class="mi-t"><thead><tr><th>Quarter ending</th>${cols}</tr></thead><tbody>
      ${line('revenue', 'Revenue', money)}${line('gross_profit', 'Gross profit', money)}${line('operating_income', 'Operating income', money)}
      ${line('net_income', 'Net income', money)}${line('eps_diluted', 'EPS (diluted)', (v) => (v == null ? '—' : v.toFixed(2)))}
      ${line('operating_margin', 'Operating margin', pct)}
      <tr><td class="nm">Revenue, change on a year earlier</td>${qs.map((q, i) => { const p = qs[i - 4]; const v = p && p.revenue && q.revenue != null ? (q.revenue / p.revenue - 1) * 100 : null; return `<td class="n ${tone(v)}">${v == null ? '—' : sgn(v)}</td>`; }).join('')}</tr></tbody></table></div>
      <p class="mi-foot">Companies do not file a fourth quarter on its own. "Derived Q4" is the fiscal year minus the first three quarters; its EPS is left empty because share counts differ between quarters. The change on a year earlier compares a quarter with the one four quarters before it.</p></div>`;
  }

  /* Charts: annual or quarterly, each in a frame with its metric, units, range and source, a
     keyboard legend and a table view that also gives the change on a year earlier. A derived Q4
     (fiscal year minus three filed quarters) is marked in its label. */
  let per = 'annual', cur = null;
  // change on a year earlier; undefined (a dash) when the earlier figure is zero or negative
  const yoy = (vals, lag) => vals.map((v, i) => (i >= lag && v != null && vals[i - lag] > 0 ? (v / vals[i - lag] - 1) * 100 : null));
  function series(d) {
    if (per === 'annual') {
      const r = d.annual;
      return { labels: r.map((x) => 'FY' + x.fiscal_year), lag: 1, range: r.length ? `FY${r[0].fiscal_year} to FY${r[r.length - 1].fiscal_year}` : '',
        money: [['Revenue', r.map((x) => x.revenue), '--accent'], ['Net income', r.map((x) => x.net_income), '--up'], ['Free cash flow', r.map((x) => x.fcf), '--violet']],
        margin: [['Gross margin', r.map((x) => x.gross_margin), '--accent'], ['Operating margin', r.map((x) => x.operating_margin), '--up'], ['Net margin', r.map((x) => x.net_margin), '--gold']],
        derived: false };
    }
    const q = d.quarterly;
    return { labels: q.map((x) => x.period_end.slice(0, 7) + (x.derived ? ' Q4*' : '')), lag: 4, range: q.length ? `quarters ending ${q[0].period_end} to ${q[q.length - 1].period_end}` : '',
      money: [['Revenue', q.map((x) => x.revenue), '--accent'], ['Net income', q.map((x) => x.net_income), '--up']],
      margin: [['Gross margin', q.map((x) => x.gross_margin), '--accent'], ['Operating margin', q.map((x) => x.operating_margin), '--up'],
        ['Net margin', q.map((x) => (x.revenue && x.net_income != null ? x.net_income / x.revenue * 100 : null)), '--gold']],
      derived: q.some((x) => x.derived) };
  }
  function chartsHtml(d) {
    const sr = series(d);
    const note = (sr.derived ? '* Q4 derived: fiscal year minus the three filed quarters. ' : '') + (per === 'quarterly' ? 'Free cash flow is reported for full years only. ' : '') + 'The table view adds the change on a year earlier.';
    const asOf = per === 'annual' ? (d.annual[d.annual.length - 1] || {}).period_end : (d.quarterly[d.quarterly.length - 1] || {}).period_end;
    return `<div class="rs-per seg" role="group" aria-label="Period of the charts">
        <button type="button" data-per="annual" aria-pressed="${per === 'annual'}" class="${per === 'annual' ? 'on' : ''}">Annual</button>
        <button type="button" data-per="quarterly" aria-pressed="${per === 'quarterly'}" class="${per === 'quarterly' ? 'on' : ''}">Quarterly</button></div>
      <div class="mi-two">
        ${ChartFrame.html({ id: 'rsA', title: 'Revenue, net income and free cash flow', metric: 'As reported', units: 'US dollars', range: sr.range, source: 'SEC filings (XBRL)', asOf, note })}
        ${ChartFrame.html({ id: 'rsB', title: 'Margins', metric: 'Profit as a share of revenue', units: '%', range: sr.range, source: 'computed from SEC filings', asOf, note: per === 'quarterly' ? 'Quarterly net margin is computed here as net income over revenue.' : '' })}
      </div>`;
  }
  function drawCharts(d) {
    cur = d;
    charts.forEach((c) => c.destroy()); charts = [];
    if (typeof Chart === 'undefined') return;
    const css = getComputedStyle(document.documentElement);
    const c = (n, fb) => (css.getPropertyValue(n) || fb).trim();
    const sr = series(d);
    const a = document.getElementById('rsA-c'), b = document.getElementById('rsB-c');
    const pctF = (v) => (v == null ? '—' : Number(v).toFixed(1) + '%');
    const chgF = (v) => (v == null ? '—' : (v > 0 ? '+' : '') + Number(v).toFixed(1) + '%');
    const yoyRows = (list, fmt) => list.flatMap(([label, vals]) => [{ label, values: vals, fmt },
      { label: `${label}, change on a year earlier`, values: yoy(vals, sr.lag), fmt: chgF }]);
    if (a) {
      const ch = new Chart(a, { type: 'bar', data: { labels: sr.labels, datasets: sr.money.map(([label, data, tk]) => ({ label, data, backgroundColor: c(tk, '#5b8def') })) },
        options: ChartFrame.base((v) => money(v)) });
      charts.push(ch);
      ChartFrame.fill('rsA', ch, sr.labels, yoyRows(sr.money, money));
    }
    if (b) {
      const ch = new Chart(b, { type: 'line', data: { labels: sr.labels, datasets: sr.margin.map(([label, data, tk]) => ({ label, data, borderColor: c(tk, '#5b8def'), backgroundColor: c(tk, '#5b8def'), tension: 0, spanGaps: false, pointRadius: 3 })) },
        options: ChartFrame.base(pctF) });
      charts.push(ch);
      ChartFrame.fill('rsB', ch, sr.labels, sr.margin.map(([label, vals]) => ({ label, values: vals, fmt: pctF })));
    }
  }
  root.addEventListener('click', (ev) => {
    const b = ev.target.closest('[data-per]');
    if (!b || !cur) return;
    per = b.dataset.per;
    document.getElementById('rsCharts').innerHTML = chartsHtml(cur);
    drawCharts(cur);
    const f = document.querySelector(`[data-per="${per}"]`); if (f) f.focus();
  });
  document.addEventListener('themechange', () => { if (cur && root.classList.contains('on')) drawCharts(cur); });

  async function open(t) {
    t = (t || '').trim().toUpperCase();
    if (!t) return;
    document.getElementById('rsInput').value = t;
    if (location.hash !== '#/research?t=' + t) history.replaceState(null, '', '#/research?t=' + encodeURIComponent(t));
    body.innerHTML = '<div class="spinner"></div>';
    let d, q = null;
    try {
      [d, q] = await Promise.all([api('/api/company/' + encodeURIComponent(t)), api('/api/quotes?tickers=' + encodeURIComponent(t)).then((x) => x[0]).catch(() => null)]);
    } catch (err) {
      body.innerHTML = `<div class="mi-empty">${e((err && err.error) || 'Financial statements are unavailable right now.')}</div>`;
      return;
    }
    const last = d.annual[d.annual.length - 1] || {};
    const cap = q && q.price && last.shares_diluted ? q.price * last.shares_diluted : null;
    const pe = q && q.price && last.eps_diluted > 0 ? q.price / last.eps_diluted : null;
    body.innerHTML = `
      <div class="rs-head">
        <div><h2>${e(d.name)}</h2><div class="rs-sub">${e(d.ticker)} · SEC CIK ${e(d.cik)} · fiscal year ends ${e((last.period_end || '').slice(5))}</div>
          <a class="btn btn-ghost btn-sm rs-pdf" href="/report/${encodeURIComponent(d.ticker)}" target="_blank" rel="noopener">Printable report (PDF)</a></div>
        <div class="rs-kpis">
          <div><span>Price</span><b>${q ? q.price.toFixed(2) : '—'}</b><small class="${tone(q && q.chg)}">${q ? sgn(q.chg) : ''} · delayed</small></div>
          <div><span>P/E on FY${e(last.fiscal_year)} EPS</span><b>${pe ? pe.toFixed(1) + '×' : '—'}</b><small>price / last annual diluted EPS</small></div>
          <div><span>Value at diluted shares</span><b>${cap ? money(cap) : '—'}</b><small>price × FY diluted shares</small></div>
        </div>
      </div>
      <div class="rs-summary"><h3>From the filings</h3>${d.summary.length ? '<ul>' + d.summary.map((s) => `<li>${e(s)}</li>`).join('') + '</ul>' : '<p>Not enough reported figures for a summary.</p>'}
        <p class="mi-foot">Built only from the reported numbers below. Not a forecast, and not investment advice.</p></div>
      <div class="mi-block" id="rsCharts">${chartsHtml(d)}</div>
      ${ratiosTable(d)}
      ${table('Income statement', d.annual, [['revenue', 'Revenue'], ['gross_profit', 'Gross profit'], ['rnd', 'Research & development'], ['operating_income', 'Operating income', null, 'em'], ['pretax_income', 'Income before tax'], ['income_tax', 'Income tax'], ['net_income', 'Net income', null, 'em'], ['eps_diluted', 'EPS (diluted)', (v) => (v == null ? '—' : v.toFixed(2))], ['shares_diluted', 'Diluted shares', money], ['dps', 'Dividends per share', (v) => (v == null ? '—' : v.toFixed(2))]], money)}
      ${table('Balance sheet', d.annual, [['cash', 'Cash & equivalents'], ['total_assets', 'Total assets', null, 'em'], ['total_liabilities', 'Total liabilities'], ['debt', 'Reported debt'], ['equity', "Shareholders' equity", null, 'em']], money, 'At fiscal year end')}
      ${table('Cash flow', d.annual, [['cfo', 'Operating cash flow', null, 'em'], ['capex', 'Capital expenditure'], ['fcf', 'Free cash flow', null, 'em'], ['buybacks', 'Share repurchases'], ['dividends_paid', 'Dividends paid']], money)}
      ${quarterTable(d.quarterly)}
      <div class="mi-block rs-src"><div class="sec">Source and method</div>
        <p>${e(d.source)}. <a href="${e(d.source_url)}" target="_blank" rel="noopener">Raw data</a> · <a href="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&amp;CIK=${e(d.cik)}" target="_blank" rel="noopener">Filings on EDGAR</a></p>
        <pre>${e(d.method)}</pre></div>`;
    drawCharts(d);
  }

  root.addEventListener('submit', (ev) => { ev.preventDefault(); open(document.getElementById('rsInput').value); });
  root.addEventListener('click', (ev) => { const b = ev.target.closest('.rs-quick [data-t]'); if (b) open(b.dataset.t); });
  function fromHash() {
    const m = location.hash.match(/^#\/research\?t=([A-Za-z0-9.\-]+)/);
    if (m && m[1].toUpperCase() !== document.getElementById('rsInput').value) open(decodeURIComponent(m[1]));
  }
  window.addEventListener('hashchange', fromHash);
  window.openResearch = (t) => { location.hash = '#/research?t=' + encodeURIComponent(t); };
  fromHash();
})();
