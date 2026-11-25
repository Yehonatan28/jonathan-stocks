/* Jonathan Stocks · Calendar (Intelligence)
   Earnings, economic events and dividends for the next trading days (/api/calendar). Holdings and
   watchlist names are marked and can be shown alone. Estimates are labelled as estimates. */
(function () {
  'use strict';
  const root = document.getElementById('v-calendar');
  if (!root) return;
  const e = (t) => String(t == null ? '' : t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const n2 = (v, d = 2) => (v == null ? '—' : Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }));
  const cap = (v) => (v == null ? '—' : v >= 1e12 ? '$' + (v / 1e12).toFixed(2) + 'T' : v >= 1e9 ? '$' + (v / 1e9).toFixed(1) + 'B' : '$' + (v / 1e6).toFixed(0) + 'M');
  const KINDS = [['earnings', 'Earnings'], ['economicevents', 'Economic events'], ['dividends', 'Dividends']];
  const days = [];
  for (let d = new Date(); days.length < 10; d.setDate(d.getDate() + 1)) if (d.getDay() % 6) days.push(new Date(d));
  const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const st = { kind: 'earnings', day: iso(days[0]), mine: false, minCap: 10e9, us: true };
  let mineSet = new Set();

  root.innerHTML = `<div class="wrap calw">
    <div class="ph"><h1>Calendar</h1><p>Earnings, economic releases and dividends for the next two weeks. Your holdings and watchlist are marked.</p></div>
    <div class="seg" id="calKind" role="tablist">${KINDS.map(([k, l]) => `<button data-k="${k}" role="tab">${l}</button>`).join('')}</div>
    <div class="cal-days" id="calDays" role="tablist" aria-label="Day">${days.map((d) => `<button data-d="${iso(d)}" role="tab"><b>${d.toLocaleDateString('en-US', { weekday: 'short' })}</b><span>${d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</span></button>`).join('')}</div>
    <div class="cal-filters" id="calFilters"></div>
    <div class="mi-card scr-table" id="calTable"><div class="spinner"></div></div>
    <p class="mi-foot" id="calNote"></p>
    <details class="rs-defs"><summary>Source and method</summary><pre class="lg-pre" id="calMethod"></pre></details>
  </div>`;
  const $k = (id) => document.getElementById(id);

  async function loadMine() {
    try {
      const pf = typeof store !== 'undefined' ? await store.getPf() : [];
      const wl = typeof store !== 'undefined' ? await store.getWatch() : [];
      mineSet = new Set([...(pf || []).map((p) => p.ticker), ...(wl || []).map((w) => (typeof w === 'string' ? w : w.ticker))].filter(Boolean).map((x) => String(x).toUpperCase()));
    } catch (_) { mineSet = new Set(); }
  }

  function filters() {
    const f = $k('calFilters');
    if (st.kind === 'earnings' || st.kind === 'dividends') {
      f.innerHTML = `<label class="chip-btn"><input type="checkbox" id="calMine" ${st.mine ? 'checked' : ''}> Only my holdings and watchlist${mineSet.size ? ` (${mineSet.size})` : ''}</label>` +
        (st.kind === 'earnings' ? `<label class="chip-btn">Market cap at least <select id="calCap">${[[0, 'any'], [2e9, '$2B'], [10e9, '$10B'], [50e9, '$50B'], [200e9, '$200B']].map(([v, l]) => `<option value="${v}" ${v === st.minCap ? 'selected' : ''}>${l}</option>`).join('')}</select></label>` : '');
    } else {
      f.innerHTML = `<label class="chip-btn"><input type="checkbox" id="calUs" ${st.us ? 'checked' : ''}> United States only</label>`;
    }
  }

  function render(d) {
    $k('calMethod').textContent = d.method;
    let rows = d.rows;
    if (st.kind === 'earnings') rows = rows.filter((r) => (!st.mine || mineSet.has(r.symbol)) && (st.mine || (r.market_cap || 0) >= st.minCap));
    if (st.kind === 'dividends' && st.mine) rows = rows.filter((r) => mineSet.has(r.symbol));
    if (st.kind === 'economicevents' && st.us) rows = rows.filter((r) => (r.country || '').toLowerCase().includes('united states'));
    const mark = (s) => (mineSet.has(s) ? ' class="mine"' : '');
    let html;
    if (!rows.length) html = `<div class="mi-empty">Nothing ${d.rows.length ? 'matches the filters' : 'scheduled'} for this day.</div>`;
    else if (st.kind === 'earnings') {
      html = `<table class="mi-t scr-t"><thead><tr><th class="sticky">Company</th><th>When</th><th class="n">Market cap</th><th>Quarter</th>
        <th class="n">EPS estimate</th><th class="n">Analysts</th><th class="n">EPS a year ago</th></tr></thead><tbody>
        ${rows.map((r) => `<tr data-t="${e(r.symbol)}" tabindex="0"${mark(r.symbol)}><td class="sticky"><b>${e(r.symbol)}</b><small>${e(r.name)}</small></td><td>${e(r.session)}</td>
        <td class="n">${cap(r.market_cap)}</td><td>${e(r.quarter || '—')}</td><td class="n">${n2(r.eps_estimate)} <small>est.</small></td><td class="n">${r.estimates || '—'}</td><td class="n">${n2(r.eps_last_year)}</td></tr>`).join('')}</tbody></table>`;
    } else if (st.kind === 'economicevents') {
      html = `<table class="mi-t scr-t"><thead><tr><th>Time (GMT)</th><th>Country</th><th>Event</th><th class="n">Actual</th><th class="n">Consensus <small>est.</small></th><th class="n">Previous</th></tr></thead><tbody>
        ${rows.map((r) => `<tr><td>${e(r.time_gmt || '—')}</td><td>${e(r.country || '—')}</td><td><b>${e(r.event)}</b></td><td class="n">${e(r.actual || '—')}</td><td class="n">${e(r.consensus || '—')}</td><td class="n">${e(r.previous || '—')}</td></tr>`).join('')}</tbody></table>`;
    } else {
      html = `<table class="mi-t scr-t"><thead><tr><th class="sticky">Company</th><th>Ex-dividend</th><th>Record</th><th>Payment</th><th class="n">Amount</th><th class="n">Annual rate</th></tr></thead><tbody>
        ${rows.map((r) => `<tr data-t="${e(r.symbol)}" tabindex="0"${mark(r.symbol)}><td class="sticky"><b>${e(r.symbol)}</b><small>${e(r.name)}</small></td><td>${e(r.ex_date || '—')}</td><td>${e(r.record_date || '—')}</td><td>${e(r.pay_date || '—')}</td>
        <td class="n">${n2(r.amount, 3)}</td><td class="n">${n2(r.annual, 2)}</td></tr>`).join('')}</tbody></table>`;
    }
    $k('calTable').innerHTML = html;
    $k('calNote').textContent = `${rows.length} of ${d.rows.length} shown for ${d.date}. ` +
      (st.kind === 'earnings' ? 'EPS estimates are analysts’ consensus forecasts, not results. ' : '') + (mineSet.size ? 'Highlighted rows are in your holdings or watchlist.' : '');
  }

  let last = null;
  async function load() {
    root.querySelectorAll('#calKind button').forEach((b) => { b.classList.toggle('on', b.dataset.k === st.kind); b.setAttribute('aria-selected', String(b.dataset.k === st.kind)); });
    root.querySelectorAll('#calDays button').forEach((b) => { b.classList.toggle('on', b.dataset.d === st.day); b.setAttribute('aria-selected', String(b.dataset.d === st.day)); });
    filters();
    $k('calTable').innerHTML = '<div class="spinner"></div>';
    try { last = await api(`/api/calendar?kind=${st.kind}&date=${st.day}`); render(last); }
    catch (err) { $k('calTable').innerHTML = `<div class="mi-empty">${e((err && err.error) || 'The calendar is unavailable right now.')}</div>`; }
  }

  root.addEventListener('click', (ev) => {
    const k = ev.target.closest('#calKind [data-k]'); if (k) { st.kind = k.dataset.k; load(); return; }
    const d = ev.target.closest('#calDays [data-d]'); if (d) { st.day = d.dataset.d; load(); return; }
    const tr = ev.target.closest('tr[data-t]'); if (tr && typeof openChart === 'function') openChart(tr.dataset.t);
  });
  root.addEventListener('change', (ev) => {
    if (ev.target.id === 'calMine') st.mine = ev.target.checked;
    if (ev.target.id === 'calCap') st.minCap = Number(ev.target.value);
    if (ev.target.id === 'calUs') st.us = ev.target.checked;
    if (last) render(last);
  });
  let started = false;
  const start = async () => { if (root.classList.contains('on') && !started) { started = true; await loadMine(); load(); } };
  new MutationObserver(start).observe(root, { attributes: true, attributeFilter: ['class'] });
  start();
})();
