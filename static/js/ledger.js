/* Jonathan Stocks · Transactions & P&L (Portfolio)
   Signed in, transactions live in the account (/api/transactions) and are valued by /api/ledger.
   As a guest they stay in this browser and are sent to /api/ledger only to be computed; the
   server does not store or log them. FIFO accounting; method shown on the page. */
(function () {
  'use strict';
  const root = document.getElementById('v-ledger');
  if (!root) return;
  const KEY = 'js_tx';
  const e = (t) => String(t == null ? '' : t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const n2 = (v, d = 2) => (v == null ? '—' : Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }));
  const sgn = (v) => (v == null ? '—' : (v > 0 ? '+' : '') + n2(v));
  const pc = (v) => (v == null ? '—' : (v > 0 ? '+' : '') + n2(v) + '%');
  const tone = (v) => (v == null || v === 0 ? '' : v > 0 ? 'up' : 'dn');
  const signedIn = () => typeof S !== 'undefined' && !!S.user;
  const local = {
    get() { try { return JSON.parse(localStorage.getItem(KEY) || '[]'); } catch (_) { return []; } },
    set(v) { try { localStorage.setItem(KEY, JSON.stringify(v)); } catch (_) { /* storage blocked */ } },
  };
  const today = () => new Date().toISOString().slice(0, 10);
  const FIELDS = {
    buy: ['ticker', 'qty', 'price', 'fee'], sell: ['ticker', 'qty', 'price', 'fee'],
    dividend: ['ticker', 'amount'], split: ['ticker', 'ratio'],
    deposit: ['amount'], withdrawal: ['amount'], fee: ['amount'],
  };

  root.innerHTML = `<div class="wrap ldg">
    <div class="ph"><h1>Transactions &amp; P&amp;L</h1><p>Record buys, sells, dividends, cash and splits. Positions, cost and gains are computed first-in, first-out.</p></div>
    <div class="lg-where" id="lgWhere"></div>
    <div id="lgTotals"></div>
    <div class="mi-block" id="lgPerfBox" hidden><div class="sec">Performance <span class="tag">TIME-WEIGHTED</span><span class="mi-note" id="lgPerfNote"></span></div>
      <div class="mi-two lg-perf"><div class="mi-card rs-chart"><canvas id="lgPerfChart" role="img" aria-label="Portfolio against the S&amp;P 500, indexed to 100"></canvas></div>
      <div class="mi-tiles" id="lgPerfStats"></div></div>
      <details class="rs-defs"><summary>How performance is measured</summary><pre id="lgPerfMethod" class="lg-pre"></pre></details></div>
    <div class="mi-two">
      <div class="mi-block"><div class="sec">Add a transaction</div>
        <form class="lg-form mi-card" id="lgForm" autocomplete="off">
          <label>Type<select name="type">${Object.keys(FIELDS).map((t) => `<option value="${t}">${t[0].toUpperCase() + t.slice(1)}</option>`).join('')}</select></label>
          <label>Date<input name="date" type="date" required></label>
          <label data-f="ticker">Symbol<input name="ticker" maxlength="15" placeholder="AAPL" spellcheck="false"></label>
          <label data-f="qty">Quantity<input name="qty" type="number" step="any" min="0" inputmode="decimal"></label>
          <label data-f="price">Price per share<input name="price" type="number" step="any" min="0" inputmode="decimal"></label>
          <label data-f="fee">Fee<input name="fee" type="number" step="any" min="0" inputmode="decimal" placeholder="0"></label>
          <label data-f="amount">Amount<input name="amount" type="number" step="any" min="0" inputmode="decimal"></label>
          <label data-f="ratio">Split ratio<input name="ratio" type="number" step="any" min="0" inputmode="decimal" placeholder="4 for a 4-for-1"></label>
          <label>Currency<select name="currency"><option>USD</option><option>ILS</option><option>EUR</option><option>GBP</option></select></label>
          <label class="wide">Note<input name="note" maxlength="200" placeholder="optional"></label>
          <div class="wide lg-act"><button class="btn btn-gold btn-sm" type="submit">Add</button><span class="auth-err" id="lgErr" role="alert"></span></div>
        </form>
        <div class="lg-io"><button class="btn btn-ghost btn-sm" id="lgExport">Export CSV</button>
          <label class="btn btn-ghost btn-sm">Import CSV<input type="file" accept=".csv,text/csv" id="lgImport" hidden></label>
          <small>Columns: type, date, ticker, qty, price, fee, amount, ratio, currency, note</small></div>
      </div>
      <div class="mi-block"><div class="sec">Realised sales</div><div class="mi-card" id="lgSales"></div></div>
    </div>
    <div class="mi-block"><div class="sec">Open positions <span class="tag">FIFO</span></div><div class="mi-card scr-table" id="lgHold"></div></div>
    <div class="mi-block"><div class="sec">History</div><div class="mi-card scr-table" id="lgList"></div></div>
    <details class="rs-defs lg-method"><summary>How this is computed</summary><pre id="lgMethod"></pre></details>
  </div>`;
  const $l = (id) => document.getElementById(id);
  const form = $l('lgForm');
  form.date.value = today();

  function showFields() {
    const want = FIELDS[form.type.value];
    form.querySelectorAll('[data-f]').forEach((l) => { l.hidden = !want.includes(l.dataset.f); });
  }
  form.type.addEventListener('change', showFields);
  showFields();

  async function txs() { return signedIn() ? api('/api/transactions') : local.get(); }

  async function refresh() {
    $l('lgWhere').innerHTML = signedIn()
      ? 'Saved in your account. Only you can see it.'
      : 'Guest mode: saved in this browser only. It is sent to the server to be computed and is not stored there.';
    let list, led;
    try {
      list = await txs();
      led = signedIn() ? await api('/api/ledger') : await api('/api/ledger', { method: 'POST', body: JSON.stringify({ transactions: list }) });
    } catch (err) {
      $l('lgTotals').innerHTML = `<div class="mi-empty">${e((err && err.error) || 'Could not compute the ledger.')}</div>`;
      list = list || [];
      led = null;
    }
    renderList(list);
    if (!led) return;
    $l('lgMethod').textContent = led.method;
    renderTotals(led.totals);
    perf(list, Object.keys(led.totals));
    renderHoldings(led.holdings);
    renderSales(led.sales);
  }

  let perfChart = null;
  async function perf(list, currencies) {
    const box = $l('lgPerfBox');
    if (!list.length || !currencies.length) { box.hidden = true; return; }
    const cur = currencies.includes('USD') ? 'USD' : currencies[0];
    let p;
    try {
      p = signedIn() ? await api('/api/performance?currency=' + cur)
        : await api('/api/performance', { method: 'POST', body: JSON.stringify({ transactions: list, currency: cur }) });
    } catch (err) { p = { ok: false, reason: (err && (err.reason || err.error)) || 'Performance is unavailable right now.' }; }
    box.hidden = false;
    if (!p.ok) {
      $l('lgPerfStats').innerHTML = `<div class="mi-empty">${e(p.reason)}</div>`;
      $l('lgPerfNote').textContent = '';
      if (perfChart) { perfChart.destroy(); perfChart = null; }
      return;
    }
    const s = p.stats;
    $l('lgPerfNote').textContent = `${p.currency} account · ${p.start} to ${p.end} · ${p.days} trading days` +
      (p.skipped_other_currency ? ` · ${p.skipped_other_currency} transactions in other currencies left out` : '') +
      (p.unpriced.length ? ` · no history for ${p.unpriced.join(', ')}` : '');
    const need = (v, n) => (v == null ? `<span class="muted">needs ${n} trading days</span>` : '');
    const tile = (lab, v, fmt, cls, sub) => `<div class="mi-tile"><div class="t-lab">${lab}</div><div class="t-val ${cls || ''}">${v == null ? '—' : fmt(v)}</div><div class="t-sub">${sub || ''}</div></div>`;
    const pctf = (v) => (v > 0 ? '+' : '') + n2(v) + '%';
    $l('lgPerfStats').innerHTML =
      tile('Return', s.total_return, pctf, tone(s.total_return), 'S&P 500 (SPY) ' + (s.benchmark_return == null ? '—' : pctf(s.benchmark_return))) +
      tile('Annualised', s.cagr, pctf, tone(s.cagr), need(s.cagr, 252)) +
      tile('Volatility', s.volatility, (v) => n2(v) + '%', '', s.volatility == null ? need(null, 60) : 'annualised') +
      tile('Sharpe / Sortino', s.sharpe, (v) => n2(v) + ' / ' + (s.sortino == null ? '—' : n2(s.sortino)), '', s.sharpe == null ? need(null, 60) : 'risk-free: ' + e(p.rf_source)) +
      tile('Beta / alpha', s.beta, (v) => n2(v) + ' / ' + (s.alpha == null ? '—' : pctf(s.alpha)), '', s.beta == null ? need(null, 60) : 'vs SPY, alpha annualised') +
      tile('Max drawdown', s.max_drawdown, (v) => n2(v) + '%', s.max_drawdown < 0 ? 'dn' : '', s.max_drawdown_peak ? `${s.max_drawdown_peak} → ${s.max_drawdown_trough}` : 'no fall from a peak');
    $l('lgPerfMethod').textContent = p.method;
    if (perfChart) perfChart.destroy();
    if (typeof Chart === 'undefined') return;
    const css = getComputedStyle(document.documentElement);
    const c = (n, fb) => (css.getPropertyValue(n) || fb).trim();
    perfChart = new Chart($l('lgPerfChart'), { type: 'line', data: { labels: p.series.map((x) => x.date), datasets: [
      { label: 'Portfolio', data: p.series.map((x) => x.portfolio), borderColor: c('--accent', '#5b8def'), pointRadius: 0, borderWidth: 2, tension: 0 },
      { label: 'S&P 500 (SPY)', data: p.series.map((x) => x.benchmark), borderColor: c('--tx3', '#889'), pointRadius: 0, borderWidth: 1.5, borderDash: [4, 3], tension: 0 }] },
      options: { responsive: true, maintainAspectRatio: false, animation: false, interaction: { mode: 'index', intersect: false },
        plugins: { legend: { labels: { color: c('--tx3', '#889'), boxWidth: 10, font: { size: 11 } } } },
        scales: { x: { ticks: { color: c('--tx3', '#889'), maxTicksLimit: 6 }, grid: { display: false } },
          y: { ticks: { color: c('--tx3', '#889') }, grid: { color: c('--line', '#222') }, title: { display: true, text: 'indexed to 100', color: c('--tx3', '#889') } } } } });
  }

  function renderTotals(totals) {
    const curs = Object.keys(totals);
    if (!curs.length) { $l('lgTotals').innerHTML = '<div class="mi-empty">No transactions yet. Start with a deposit, then a buy.</div>'; return; }
    $l('lgTotals').innerHTML = curs.map((c) => {
      const t = totals[c];
      const tile = (lab, v, cls, sub) => `<div class="mi-tile"><div class="t-lab">${lab}</div><div class="t-val ${cls || ''}">${v}</div>${sub ? `<div class="t-sub">${sub}</div>` : ''}</div>`;
      return `<div class="mi-block"><div class="sec">${e(c)} account${curs.length > 1 ? ' <span class="mi-note">currencies are kept apart; no exchange rate is applied</span>' : ''}</div><div class="mi-tiles">
        ${tile('Account value', t.account_value == null ? '—' : n2(t.account_value), '', t.unpriced.length ? 'no price for ' + e(t.unpriced.join(', ')) : 'positions + cash')}
        ${tile('Cash', n2(t.cash), t.cash < 0 ? 'dn' : '', t.cash < 0 ? 'negative: buys exceed recorded deposits' : '')}
        ${tile('Unrealised gain', sgn(t.unrealised), tone(t.unrealised), 'on open positions')}
        ${tile('Realised gain', sgn(t.realised), tone(t.realised), 'from sales, after fees')}
        ${tile('Dividends', n2(t.dividends), '', 'fees paid ' + n2(t.fees))}
        ${tile('Net deposits', n2(t.net_contributions), '', `in ${n2(t.deposits)} · out ${n2(t.withdrawals)}`)}
      </div></div>`;
    }).join('');
  }

  function renderHoldings(hs) {
    $l('lgHold').innerHTML = hs.length ? `<table class="mi-t scr-t"><thead><tr><th class="sticky">Symbol</th><th class="n">Qty</th><th class="n">Avg cost</th>
      <th class="n">Price</th><th class="n">Value</th><th class="n">Unrealised</th><th class="n">%</th><th class="n">Realised</th><th class="n">Dividends</th><th class="n">Lots</th></tr></thead>
      <tbody>${hs.map((h) => `<tr data-t="${e(h.ticker)}" tabindex="0"><td class="sticky"><b>${e(h.ticker)}</b><small>${e(h.currency)}</small></td>
      <td class="n">${n2(h.qty, h.qty % 1 ? 4 : 0)}</td><td class="n">${n2(h.avg_cost)}</td><td class="n">${n2(h.price)}</td><td class="n">${n2(h.value)}</td>
      <td class="n ${tone(h.unrealised)}">${sgn(h.unrealised)}</td><td class="n ${tone(h.unrealised_pct)}">${pc(h.unrealised_pct)}</td>
      <td class="n ${tone(h.realised)}">${h.realised ? sgn(h.realised) : '—'}</td><td class="n">${h.dividends ? n2(h.dividends) : '—'}</td>
      <td class="n" title="${e(h.lots.map((l) => `${l.qty} @ ${l.cost_per_share} from ${l.opened}`).join('\n'))}">${h.lots.length}</td></tr>`).join('')}</tbody></table>`
      : '<div class="mi-empty">No open positions.</div>';
  }

  function renderSales(ss) {
    $l('lgSales').innerHTML = ss.length ? `<table class="mi-t"><thead><tr><th>Date</th><th>Symbol</th><th class="n">Qty</th><th class="n">Gain</th><th class="n">Return</th></tr></thead>
      <tbody>${ss.slice(0, 12).map((s) => `<tr><td>${e(s.date)}</td><td><b>${e(s.ticker)}</b></td><td class="n">${n2(s.qty, s.qty % 1 ? 4 : 0)}</td>
      <td class="n ${tone(s.gain)}">${sgn(s.gain)} <small>${e(s.currency)}</small></td><td class="n ${tone(s.return_pct)}">${pc(s.return_pct)}</td></tr>`).join('')}</tbody></table>`
      : '<div class="mi-empty">No sales yet.</div>';
  }

  function renderList(list) {
    const rows = list.map((t, i) => ({ ...t, _i: i })).sort((a, b) => (b.date || '').localeCompare(a.date || '') || b._i - a._i);
    const what = (t) => t.type === 'buy' || t.type === 'sell' ? `${n2(t.qty, t.qty % 1 ? 4 : 0)} @ ${n2(t.price)}${t.fee ? ' + fee ' + n2(t.fee) : ''}`
      : t.type === 'split' ? `${t.ratio}-for-1` : n2(t.amount);
    $l('lgList').innerHTML = rows.length ? `<table class="mi-t scr-t"><thead><tr><th>Date</th><th>Type</th><th>Symbol</th><th class="n">Detail</th><th>Cur.</th><th>Note</th><th></th></tr></thead>
      <tbody>${rows.map((t) => `<tr><td>${e(t.date)}</td><td><span class="lg-type t-${e(t.type)}">${e(t.type)}</span></td><td><b>${e(t.ticker || '')}</b></td>
      <td class="n">${what(t)}</td><td>${e(t.currency || 'USD')}</td><td class="muted">${e(t.note || '')}</td>
      <td class="n"><button class="x" data-del="${signedIn() ? t.id : t._i}" aria-label="Delete this ${e(t.type)}">×</button></td></tr>`).join('')}</tbody></table>`
      : '<div class="mi-empty">Nothing recorded yet.</div>';
  }

  async function add(items) {
    $l('lgErr').textContent = '';
    try {
      if (signedIn()) {
        await api('/api/transactions', { method: 'POST', body: JSON.stringify({ items }) });
      } else {
        const next = local.get().concat(items);
        await api('/api/ledger', { method: 'POST', body: JSON.stringify({ transactions: next }) });   // validates the whole history
        local.set(next);
      }
      return true;
    } catch (err) {
      $l('lgErr').textContent = (err && err.error) || 'Could not add it.';
      return false;
    }
  }

  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const f = new FormData(form);
    const t = { type: f.get('type'), date: f.get('date'), currency: f.get('currency'), note: f.get('note') || '' };
    FIELDS[t.type].forEach((k) => { const v = f.get(k); t[k] = k === 'ticker' ? String(v || '').trim().toUpperCase() : (v === '' ? (k === 'fee' ? 0 : null) : Number(v)); });
    if (await add([t])) {
      ['ticker', 'qty', 'price', 'fee', 'amount', 'ratio', 'note'].forEach((k) => { form[k].value = ''; });
      if (typeof toast === 'function') toast('Added', 'ok');
      refresh();
    }
  });

  root.addEventListener('click', async (ev) => {
    const d = ev.target.closest('[data-del]');
    if (d) {
      if (!confirm('Delete this transaction?')) return;
      try {
        if (signedIn()) await api('/api/transactions/' + d.dataset.del, { method: 'DELETE' });
        else {
          const next = local.get(); next.splice(+d.dataset.del, 1);
          await api('/api/ledger', { method: 'POST', body: JSON.stringify({ transactions: next }) });
          local.set(next);
        }
        refresh();
      } catch (err) { if (typeof toast === 'function') toast((err && err.error) || 'Could not delete it', 'err'); }
      return;
    }
    if (ev.target.id === 'lgExport') exportCsv();
    const tr = ev.target.closest('#lgHold tr[data-t]');
    if (tr && typeof openChart === 'function') openChart(tr.dataset.t);
  });

  const COLS = ['type', 'date', 'ticker', 'qty', 'price', 'fee', 'amount', 'ratio', 'currency', 'note'];
  async function exportCsv() {
    const list = await txs();
    const q = (v) => (v == null ? '' : /[",\n]/.test(String(v)) ? '"' + String(v).replace(/"/g, '""') + '"' : String(v));
    const csv = [COLS.join(',')].concat(list.map((t) => COLS.map((c) => q(t[c])).join(','))).join('\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    a.download = `transactions-${today()}.csv`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }

  function parseCsv(text) {
    const rows = [];
    let row = [], cell = '', quoted = false;
    for (let i = 0; i < text.length; i++) {
      const ch = text[i];
      if (quoted) { if (ch === '"' && text[i + 1] === '"') { cell += '"'; i++; } else if (ch === '"') quoted = false; else cell += ch; }
      else if (ch === '"') quoted = true;
      else if (ch === ',') { row.push(cell); cell = ''; }
      else if (ch === '\n' || ch === '\r') { if (ch === '\r' && text[i + 1] === '\n') i++; row.push(cell); rows.push(row); row = []; cell = ''; }
      else cell += ch;
    }
    if (cell || row.length) { row.push(cell); rows.push(row); }
    return rows.filter((r) => r.some((c) => c.trim() !== '') && !String(r[0]).startsWith('#'));
  }
  $l('lgImport').addEventListener('change', async (ev) => {
    const file = ev.target.files[0];
    ev.target.value = '';
    if (!file) return;
    if (file.size > 1e6) { $l('lgErr').textContent = 'The file is larger than 1 MB.'; return; }
    const rows = parseCsv(await file.text());
    const head = (rows.shift() || []).map((h) => h.trim().toLowerCase());
    if (!head.includes('type') || !head.includes('date')) { $l('lgErr').textContent = 'The first row must name the columns (type, date, ...).'; return; }
    const items = rows.map((r) => {
      const o = {};
      head.forEach((h, i) => { if (COLS.includes(h)) o[h] = r[i] === undefined || r[i] === '' ? null : r[i]; });
      ['qty', 'price', 'fee', 'amount', 'ratio'].forEach((k) => { if (o[k] != null) o[k] = Number(o[k]); });
      return o;
    });
    if (await add(items)) { if (typeof toast === 'function') toast(`Imported ${items.length} transactions`, 'ok'); refresh(); }
  });

  let started = false;
  const start = () => { if (root.classList.contains('on')) { if (!started) started = true; refresh(); } };
  new MutationObserver(start).observe(root, { attributes: true, attributeFilter: ['class'] });
  start();
})();
