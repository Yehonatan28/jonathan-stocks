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
      ${line('operating_margin', 'Operating margin', pct)}</tbody></table></div>
      <p class="mi-foot">Companies do not file a fourth quarter on its own. "Derived Q4" is the fiscal year minus the first three quarters; its EPS is left empty because share counts differ between quarters.</p></div>`;
  }

  function drawCharts(d) {
    charts.forEach((c) => c.destroy()); charts = [];
    if (typeof Chart === 'undefined') return;
    const css = getComputedStyle(document.documentElement);
    const c = (n, fb) => (css.getPropertyValue(n) || fb).trim();
    const grid = c('--line', '#222'), tx = c('--tx3', '#889');
    const labels = d.annual.map((r) => 'FY' + r.fiscal_year);
    const base = { responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: { labels: { color: tx, boxWidth: 10, font: { size: 11 } } } },
      scales: { x: { grid: { display: false }, ticks: { color: tx } }, y: { grid: { color: grid }, ticks: { color: tx } } } };
    const a = document.getElementById('rsChartA'), b = document.getElementById('rsChartB');
    if (a) charts.push(new Chart(a, { type: 'bar', data: { labels, datasets: [
      { label: 'Revenue', data: d.annual.map((r) => r.revenue), backgroundColor: c('--accent', '#5b8def') },
      { label: 'Net income', data: d.annual.map((r) => r.net_income), backgroundColor: c('--up', '#2fb67c') },
      { label: 'Free cash flow', data: d.annual.map((r) => r.fcf), backgroundColor: '#8a7fd6' }] },
      options: { ...base, scales: { ...base.scales, y: { ...base.scales.y, ticks: { color: tx, callback: (v) => money(v) } } } } }));
    if (b) charts.push(new Chart(b, { type: 'line', data: { labels, datasets: [
      { label: 'Gross margin', data: d.annual.map((r) => r.gross_margin), borderColor: c('--accent', '#5b8def'), tension: 0, spanGaps: false },
      { label: 'Operating margin', data: d.annual.map((r) => r.operating_margin), borderColor: c('--up', '#2fb67c'), tension: 0 },
      { label: 'Net margin', data: d.annual.map((r) => r.net_margin), borderColor: c('--gold', '#d6aa4f'), tension: 0 }] },
      options: { ...base, scales: { ...base.scales, y: { ...base.scales.y, ticks: { color: tx, callback: (v) => v + '%' } } } } }));
  }

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
        <div><h2>${e(d.name)}</h2><div class="rs-sub">${e(d.ticker)} · SEC CIK ${e(d.cik)} · fiscal year ends ${e((last.period_end || '').slice(5))}</div></div>
        <div class="rs-kpis">
          <div><span>Price</span><b>${q ? q.price.toFixed(2) : '—'}</b><small class="${tone(q && q.chg)}">${q ? sgn(q.chg) : ''} · delayed</small></div>
          <div><span>P/E on FY${e(last.fiscal_year)} EPS</span><b>${pe ? pe.toFixed(1) + '×' : '—'}</b><small>price / last annual diluted EPS</small></div>
          <div><span>Value at diluted shares</span><b>${cap ? money(cap) : '—'}</b><small>price × FY diluted shares</small></div>
        </div>
      </div>
      <div class="rs-summary"><h3>From the filings</h3>${d.summary.length ? '<ul>' + d.summary.map((s) => `<li>${e(s)}</li>`).join('') + '</ul>' : '<p>Not enough reported figures for a summary.</p>'}
        <p class="mi-foot">Built only from the reported numbers below. Not a forecast, and not investment advice.</p></div>
      <div class="mi-two">
        <div class="mi-block"><div class="sec">Revenue, profit and cash</div><div class="mi-card rs-chart"><canvas id="rsChartA" aria-label="Revenue, net income and free cash flow by fiscal year" role="img"></canvas></div></div>
        <div class="mi-block"><div class="sec">Margins</div><div class="mi-card rs-chart"><canvas id="rsChartB" aria-label="Gross, operating and net margin by fiscal year" role="img"></canvas></div></div>
      </div>
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
