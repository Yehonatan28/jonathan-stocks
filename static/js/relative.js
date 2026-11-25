/* Jonathan Stocks · Compare & Correlate (Equity Research)
   Up to eight symbols on shared daily closes: indexed performance, period returns, volatility,
   drawdown, beta to SPY, a correlation matrix and a rolling correlation for one pair
   (/api/relative), plus filed fundamentals side by side for up to four (/api/company).
   Address: #/relative?s=AAPL,MSFT */
(function () {
  'use strict';
  const root = document.getElementById('v-relative');
  if (!root) return;
  const e = (t) => String(t == null ? '' : t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const n2 = (v, d = 2) => (v == null ? '—' : Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }));
  const pc = (v) => (v == null ? '—' : (v > 0 ? '+' : '') + n2(v) + '%');
  const tone = (v) => (v == null || v === 0 ? '' : v > 0 ? 'up' : 'dn');
  const COLORS = ['#5b8def', '#2fb67c', '#d6aa4f', '#c86fd8', '#e5566c', '#4fc3c8', '#e08a3c', '#9aa5b8'];

  root.innerHTML = `<div class="wrap cmpr">
    <div class="ph"><h1>Compare &amp; Correlate</h1><p>Up to eight symbols on the same days: performance from 100, risk, drawdown, beta and how they move together. Filed fundamentals for the first four.</p></div>
    <form class="rs-search" id="relForm" autocomplete="off">
      <input id="relInput" placeholder="AAPL, MSFT, NVDA, GOOGL" aria-label="Symbols, separated by commas" spellcheck="false" style="width:320px">
      <select id="relRange" aria-label="Period"><option value="6mo">6 months</option><option value="1y" selected>1 year</option><option value="2y">2 years</option><option value="5y">5 years</option></select>
      <button class="btn btn-gold btn-sm" type="submit">Compare</button>
      <span class="rs-quick">${[['Mega tech', 'AAPL,MSFT,NVDA,GOOGL'], ['Banks', 'JPM,BAC,WFC,GS'], ['Sectors', 'XLK,XLF,XLE,XLV,XLU'], ['Gold vs stocks', 'GLD,SPY,TLT']]
        .map(([l, s]) => `<button type="button" class="chip-btn" data-s="${s}">${l}</button>`).join('')}</span>
    </form>
    <div id="relOut"><div class="mi-empty">Enter two to eight symbols, separated by commas.</div></div>
    <details class="rs-defs"><summary>How this is computed</summary><pre class="lg-pre" id="relMethod"></pre></details>
  </div>`;
  const $c = (id) => document.getElementById(id);
  let charts = [];
  let last = null;

  function chartsDestroy() { charts.forEach((c) => c.destroy()); charts = []; }
  function lineChart(el, labels, sets, fmt, legend = true) {
    if (typeof Chart === 'undefined') return;
    const css = getComputedStyle(document.documentElement);
    const c = (n, fb) => (css.getPropertyValue(n) || fb).trim();
    charts.push(new Chart(el, { type: 'line', data: { labels, datasets: sets.map((s) => ({ pointRadius: 0, borderWidth: 1.8, tension: 0, ...s })) },
      options: { responsive: true, maintainAspectRatio: false, animation: false, interaction: { mode: 'index', intersect: false },
        plugins: { legend: { display: legend, labels: { color: c('--tx3', '#889'), boxWidth: 10, font: { size: 11 } } } },
        scales: { x: { ticks: { color: c('--tx3', '#889'), maxTicksLimit: 7 }, grid: { display: false } },
          y: { ticks: { color: c('--tx3', '#889'), callback: fmt }, grid: { color: c('--line', '#222') } } } } }));
  }

  async function fundamentals(syms) {
    const box = $c('relFund');
    const take = syms.slice(0, 4);
    const res = await Promise.all(take.map((s) => api('/api/company/' + encodeURIComponent(s)).catch(() => null)));
    const have = take.map((s, i) => [s, res[i]]).filter(([, r]) => r && r.annual && r.annual.length);
    if (!have.length) { box.innerHTML = '<div class="mi-empty">No SEC filings for these symbols (funds and non-US issuers do not file 10-Ks).</div>'; return; }
    const rows = [['fiscal_year', 'Fiscal year', (v) => (v == null ? '—' : 'FY' + v)], ['revenue', 'Revenue', (v) => (v == null ? '—' : '$' + (v / 1e9).toFixed(1) + 'B')],
      ['revenue_growth', 'Revenue growth', pc], ['gross_margin', 'Gross margin', (v) => (v == null ? '—' : n2(v, 1) + '%')],
      ['operating_margin', 'Operating margin', (v) => (v == null ? '—' : n2(v, 1) + '%')], ['net_margin', 'Net margin', (v) => (v == null ? '—' : n2(v, 1) + '%')],
      ['fcf_margin', 'FCF margin', (v) => (v == null ? '—' : n2(v, 1) + '%')], ['roe', 'Return on equity', (v) => (v == null ? '—' : n2(v, 1) + '%')],
      ['roic', 'Return on invested capital', (v) => (v == null ? '—' : n2(v, 1) + '%')], ['debt_to_equity', 'Debt / equity', (v) => (v == null ? '—' : n2(v) + '×')]];
    box.innerHTML = `<table class="mi-t scr-t"><thead><tr><th class="sticky">Latest fiscal year</th>${have.map(([s]) => `<th class="n">${e(s)}</th>`).join('')}</tr></thead><tbody>
      ${rows.map(([k, l, f]) => `<tr><td class="sticky">${l}</td>${have.map(([, r]) => `<td class="n">${f(r.annual[r.annual.length - 1][k])}</td>`).join('')}</tr>`).join('')}</tbody></table>
      <p class="mi-foot" style="padding:0 12px 10px">From each company's latest 10-K (fiscal years end on different dates). Open one in Company Research for five years and the formulas.</p>`;
  }

  function render(d) {
    chartsDestroy();
    const syms = d.symbols;
    const color = (i) => COLORS[i % COLORS.length];
    const pairOpts = [];
    for (let i = 0; i < syms.length; i++) for (let j = i + 1; j < syms.length; j++) pairOpts.push(`${syms[i]},${syms[j]}`);
    $c('relOut').innerHTML = `
      ${d.missing && d.missing.length ? `<p class="mi-foot">No history for ${e(d.missing.join(', '))}; left out.</p>` : ''}
      <div class="mi-block"><div class="sec">Performance <span class="tag">INDEXED TO 100</span><span class="mi-note">${e(d.start)} to ${e(d.end)} · ${d.days} shared days</span></div>
        <div class="mi-card rs-chart lab-chart"><canvas id="relIdx" role="img" aria-label="Indexed performance"></canvas></div></div>
      <div class="mi-block"><div class="mi-card scr-table"><table class="mi-t scr-t"><thead><tr><th class="sticky">Symbol</th><th class="n">1M</th><th class="n">3M</th><th class="n">6M</th><th class="n">1Y</th><th class="n">YTD</th>
        <th class="n">Volatility</th><th class="n">Max drawdown</th><th class="n">Beta to SPY</th></tr></thead><tbody>
        ${syms.map((s, i) => { const t = d.stats[s]; return `<tr data-t="${e(s)}" tabindex="0"><td class="sticky"><b style="color:${color(i)}">${e(s)}</b></td>
          ${['1M', '3M', '6M', '1Y', 'YTD'].map((k) => `<td class="n ${tone(t.returns[k])}">${pc(t.returns[k])}</td>`).join('')}
          <td class="n">${t.volatility == null ? '—' : n2(t.volatility) + '%'}</td><td class="n dn">${n2(t.max_drawdown)}%</td><td class="n">${t.beta == null ? '—' : n2(t.beta)}</td></tr>`; }).join('')}
      </tbody></table></div></div>
      <div class="mi-two">
        <div class="mi-block"><div class="sec">Drawdown from peak</div><div class="mi-card rs-chart"><canvas id="relDd" role="img" aria-label="Drawdown from peak"></canvas></div></div>
        <div class="mi-block"><div class="sec">Correlation of daily returns</div><div class="mi-card scr-table"><table class="mi-t rk-corr"><thead><tr><th></th>${syms.map((s) => `<th class="n">${e(s)}</th>`).join('')}</tr></thead><tbody>
          ${syms.map((a, i) => `<tr><th>${e(a)}</th>${d.correlation[i].map((v) => (v == null ? '<td class="n muted">—</td>' : `<td class="n cc" style="--c:${Math.max(0, v).toFixed(2)};--n:${Math.max(0, -v).toFixed(2)}">${v.toFixed(2)}</td>`)).join('')}</tr>`).join('')}
          </tbody></table></div></div>
      </div>
      <div class="mi-block"><div class="sec">Rolling correlation <span class="tag">60 DAYS</span>
        <select id="relPair" aria-label="Pair">${pairOpts.map((p) => `<option ${d.rolling && d.rolling.pair.join(',') === p ? 'selected' : ''}>${p}</option>`).join('')}</select></div>
        <div class="mi-card rs-chart lab-dd"><canvas id="relRoll" role="img" aria-label="Rolling 60-day correlation"></canvas></div></div>
      <div class="mi-block"><div class="sec">Fundamentals side by side <span class="tag">SEC FILINGS</span></div><div class="mi-card scr-table" id="relFund"><div class="spinner"></div></div></div>`;
    $c('relMethod').textContent = d.method;
    const labels = d.indexed.map((x) => x.date);
    lineChart($c('relIdx'), labels, syms.map((s, i) => ({ label: s, data: d.indexed.map((x) => x[s]), borderColor: color(i) })), (v) => v);
    lineChart($c('relDd'), d.dates, syms.map((s, i) => ({ label: s, data: d.stats[s].drawdown, borderColor: color(i), borderWidth: 1.3 })), (v) => v + '%');
    if (d.rolling) {
      lineChart($c('relRoll'), d.rolling.points.map((x) => x.date), [{ label: d.rolling.pair.join(' vs '), data: d.rolling.points.map((x) => x.corr), borderColor: COLORS[0] }], (v) => v, false);
    }
    fundamentals(syms);
  }

  async function run(symbols, pair) {
    const list = symbols.split(',').map((s) => s.trim().toUpperCase()).filter(Boolean).slice(0, 8);
    if (list.length < 2) { $c('relOut').innerHTML = '<div class="mi-empty">Enter at least two symbols.</div>'; return; }
    $c('relInput').value = list.join(', ');
    const p = pair || `${list[0]},${list[1]}`;
    const h = '#/relative?s=' + list.join(',');
    if (location.hash !== h) history.replaceState(null, '', h);
    $c('relOut').innerHTML = '<div class="spinner"></div>';
    try {
      const d = await api(`/api/relative?symbols=${encodeURIComponent(list.join(','))}&range=${$c('relRange').value}&pair=${encodeURIComponent(p)}`);
      if (!d.ok) { $c('relOut').innerHTML = `<div class="mi-empty">${e(d.reason)}</div>`; return; }
      last = list.join(',');
      render(d);
    } catch (err) { $c('relOut').innerHTML = `<div class="mi-empty">${e((err && err.error) || 'The comparison is unavailable right now.')}</div>`; }
  }

  root.addEventListener('submit', (ev) => { ev.preventDefault(); run($c('relInput').value); });
  root.addEventListener('click', (ev) => {
    const q = ev.target.closest('.rs-quick [data-s]');
    if (q) { run(q.dataset.s); return; }
    const tr = ev.target.closest('tr[data-t]');
    if (tr && typeof openChart === 'function') openChart(tr.dataset.t);
  });
  root.addEventListener('change', (ev) => {
    if (ev.target.id === 'relPair' && last) run(last, ev.target.value);
    if (ev.target.id === 'relRange' && last) run(last);
  });
  function fromHash() {
    const m = location.hash.match(/^#\/relative\?s=([A-Za-z0-9.,\-^=]+)/);
    if (m && m[1] !== last) run(decodeURIComponent(m[1]));
  }
  window.addEventListener('hashchange', fromHash);
  fromHash();
})();
