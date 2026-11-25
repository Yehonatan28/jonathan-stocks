/* Jonathan Stocks · Stock Screener (Equity Research)
   Rows come from /api/scan; everything else happens here: presets, range filters, sector,
   sorting, visible columns, saved screens and CSV export. A row with a missing value never
   passes a filter on that field, and the coverage of each field is shown beside it. */
(function () {
  'use strict';
  const root = document.getElementById('v-screener');
  if (!root) return;
  const e = (t) => String(t == null ? '' : t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (_) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (_) { /* storage blocked */ } },
  };

  const PRESETS = [
    { id: 'all', name: 'Everything', f: {} },
    { id: 'uptrend', name: 'Above both averages', f: { vs50: [0, null], vs200: [0, null] } },
    { id: 'below200', name: 'Below the 200-day', f: { vs200: [null, 0] } },
    { id: 'highs', name: 'Near 52-week high', f: { off_high: [-2, null] } },
    { id: 'lows', name: 'Near 52-week low', f: { range_pos: [null, 5] } },
    { id: 'value', name: 'P/E under 15', f: { pe: [null, 15] } },
    { id: 'yield', name: 'Yield 3% or more', f: { div_yield: [3, null] } },
    { id: 'volume', name: 'Unusual volume', f: { rel_vol: [2, null] } },
    { id: 'bigdown', name: 'Large caps down 2%+', f: { cap: [200, null], chg: [null, -2] } },
  ];
  const DEFAULT_COLS = ['price', 'chg', 'cap', 'pe', 'fpe', 'div_yield', 'vs50', 'vs200', 'off_high', 'rel_vol'];

  const st = {
    universe: store.get('js.scr.universe', 'sp500'),
    sector: '',
    f: {},                         // key -> [min, max]
    sort: store.get('js.scr.sort', { key: 'cap', dir: -1 }),
    cols: store.get('js.scr.cols', DEFAULT_COLS),
    preset: 'all',
    limit: 100,
    data: null,
  };

  root.innerHTML = `<div class="wrap scr">
    <div class="ph"><h1>Stock Screener</h1><p>Filter the S&amp;P 500 and Nasdaq-100 by valuation, trend and activity. Every filter shows how many names have the field.</p></div>
    <div class="scr-bar">
      <div class="seg" id="scrUni" role="tablist" aria-label="Universe">
        <button role="tab" data-u="sp500">S&amp;P 500</button><button role="tab" data-u="ndx">Nasdaq-100</button><button role="tab" data-u="all">Both</button></div>
      <select id="scrSector" aria-label="Sector"><option value="">All sectors</option></select>
      <div class="spacer"></div>
      <button class="btn btn-ghost btn-sm" id="scrColsBtn" aria-expanded="false">Columns</button>
      <button class="btn btn-ghost btn-sm" id="scrSave">Save screen</button>
      <button class="btn btn-ghost btn-sm" id="scrCsv">Export CSV</button>
    </div>
    <div class="scr-presets" id="scrPresets"></div>
    <div class="scr-saved" id="scrSaved"></div>
    <details class="scr-filters" id="scrFiltersBox"><summary>Filters <span id="scrActive"></span></summary><div class="scr-grid" id="scrFilters"></div>
      <div class="scr-frow"><button class="btn btn-ghost btn-sm" id="scrClear">Clear filters</button></div></details>
    <div class="scr-cols" id="scrCols" hidden></div>
    <div class="scr-count" id="scrCount" aria-live="polite"></div>
    <div class="scr-table" id="scrTable"><div class="spinner"></div></div>
    <div class="scr-more" id="scrMore"></div>
    <p class="mi-foot" id="scrNote"></p>
  </div>`;
  const $s = (id) => document.getElementById(id);

  const fieldOf = (k) => (st.data ? st.data.fields.find((f) => f.key === k) : null);
  function fmtv(k, v) {
    if (v == null) return '—';
    const f = fieldOf(k);
    const unit = f ? f.unit : '';
    if (k === 'price') return v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    if (k === 'cap') return v >= 1000 ? (v / 1000).toFixed(2) + 'T' : v.toFixed(1) + 'B';
    if (unit === '%') return (['chg', 'vs50', 'vs200', 'off_high'].includes(k) && v > 0 ? '+' : '') + v.toFixed(k === 'range_pos' ? 0 : 2) + '%';
    if (unit === 'x') return v.toFixed(k === 'rel_vol' ? 2 : 1) + '×';
    return String(v);
  }
  const toneOf = (k, v) => (v == null || !['chg', 'vs50', 'vs200'].includes(k) ? '' : v > 0 ? 'up' : v < 0 ? 'dn' : '');

  function passes(r) {
    if (st.sector && r.sector !== st.sector) return false;
    for (const [k, [lo, hi]] of Object.entries(st.f)) {
      if (lo == null && hi == null) continue;
      const v = r[k];
      if (v == null) return false;
      if (lo != null && v < lo) return false;
      if (hi != null && v > hi) return false;
    }
    return true;
  }
  function results() {
    const { key, dir } = st.sort;
    return st.data.rows.filter(passes).sort((a, b) => {
      const x = a[key], y = b[key];
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      return typeof x === 'string' ? dir * x.localeCompare(y) : dir * (x - y);
    });
  }

  function renderControls() {
    root.querySelectorAll('#scrUni button').forEach((b) => { b.classList.toggle('on', b.dataset.u === st.universe); b.setAttribute('aria-selected', String(b.dataset.u === st.universe)); });
    $s('scrPresets').innerHTML = PRESETS.map((p) => `<button class="chip-btn ${p.id === st.preset ? 'on' : ''}" data-p="${p.id}">${e(p.name)}</button>`).join('');
    const saved = store.get('js.scr.saved', []);
    $s('scrSaved').innerHTML = saved.length ? '<span>Saved:</span>' + saved.map((s, i) =>
      `<span class="saved"><button class="chip-btn" data-s="${i}">${e(s.name)}</button><button class="x" data-del="${i}" aria-label="Delete ${e(s.name)}">×</button></span>`).join('') : '';
    if (!st.data) return;
    const sectors = Array.from(new Set(st.data.rows.map((r) => r.sector).filter(Boolean))).sort();
    $s('scrSector').innerHTML = '<option value="">All sectors</option>' + sectors.map((s) => `<option ${s === st.sector ? 'selected' : ''}>${e(s)}</option>`).join('');
    const cov = st.data.coverage, n = st.data.rows.length;
    $s('scrFilters').innerHTML = st.data.fields.filter((f) => f.key !== 'price').map((f) => {
      const [lo, hi] = st.f[f.key] || [null, null];
      const off = !cov[f.key];
      return `<label class="flt ${off ? 'off' : ''}" title="${e(off ? 'The quote feed is not supplying this field right now' : f.help)}"><span>${e(f.label)} <small>${f.unit === '$B' ? '$B' : f.unit === '%' ? '%' : f.unit === 'x' ? '×' : ''} · ${off ? 'unavailable now' : cov[f.key] + '/' + n}</small></span>
        <span class="mm"><input type="number" step="any" inputmode="decimal" placeholder="min" data-k="${f.key}" data-i="0" value="${lo ?? ''}" aria-label="${e(f.label)} minimum" ${off ? 'disabled' : ''}>
        <input type="number" step="any" inputmode="decimal" placeholder="max" data-k="${f.key}" data-i="1" value="${hi ?? ''}" aria-label="${e(f.label)} maximum" ${off ? 'disabled' : ''}></span></label>`;
    }).join('');
    const active = Object.values(st.f).filter(([a, b]) => a != null || b != null).length + (st.sector ? 1 : 0);
    $s('scrActive').textContent = active ? `· ${active} active` : '';
    $s('scrCols').innerHTML = st.data.fields.map((f) => `<label><input type="checkbox" data-c="${f.key}" ${st.cols.includes(f.key) ? 'checked' : ''}> ${e(f.label)}</label>`).join('');
  }

  function renderTable() {
    if (!st.data) return;
    const rs = results();
    const cols = st.data.fields.filter((f) => st.cols.includes(f.key) && st.data.coverage[f.key]);
    const arrow = (k) => (st.sort.key === k ? (st.sort.dir > 0 ? ' ▲' : ' ▼') : '');
    const aria = (k) => (st.sort.key === k ? (st.sort.dir > 0 ? 'ascending' : 'descending') : 'none');
    const missing = st.data.fields.filter((f) => !st.data.coverage[f.key]).map((f) => f.label);
    const nEst = st.cols.includes('cap') ? st.data.rows.filter((r) => r.cap_est).length : 0;
    $s('scrCount').textContent = `${rs.length} of ${st.data.rows.length} stocks match` + (missing.length ? ` · not available from the feed right now: ${missing.join(', ')}` : '')
      + (nEst ? ` · market cap marked est. for ${nEst}: a static index-table estimate (Oct 2026), not price × filed shares` : '');
    const shown = rs.slice(0, st.limit);
    $s('scrTable').innerHTML = rs.length ? `<table class="mi-t scr-t"><thead><tr>
      <th class="sticky" aria-sort="${aria('ticker')}"><button data-sort="ticker">Symbol${arrow('ticker')}</button></th>
      <th aria-sort="${aria('sector')}"><button data-sort="sector">Sector${arrow('sector')}</button></th>
      ${cols.map((f) => `<th class="n" aria-sort="${aria(f.key)}" title="${e(f.help)}"><button data-sort="${f.key}">${e(f.label)}${arrow(f.key)}</button></th>`).join('')}
      </tr></thead><tbody>${shown.map((r) => `<tr data-t="${e(r.ticker)}" tabindex="0">
      <td class="sticky"><b>${e(r.ticker)}</b><small>${e(r.name || '')}</small></td><td class="sec-c">${e(r.sector || '')}</td>
      ${cols.map((f) => `<td class="n ${toneOf(f.key, r[f.key])}">${fmtv(f.key, r[f.key])}${f.key === 'cap' && r.cap_est && r.cap != null ? ' <span class="est" title="Static index-table estimate, Oct 2026: no filed share count for this company">est.</span>' : ''}</td>`).join('')}</tr>`).join('')}</tbody></table>`
      : '<div class="mi-empty">No stock matches every filter. Loosen one, or clear them.</div>';
    $s('scrMore').innerHTML = rs.length > st.limit ? `<button class="btn btn-ghost btn-sm" id="scrMoreBtn">Show ${Math.min(100, rs.length - st.limit)} more</button>` : '';
  }
  const render = () => { renderControls(); renderTable(); };

  async function load() {
    $s('scrTable').innerHTML = '<div class="spinner"></div>';
    try {
      st.data = await api('/api/scan?universe=' + st.universe);
      $s('scrNote').textContent = st.data.note || '';
    } catch (err) {
      st.data = null;
      $s('scrTable').innerHTML = `<div class="mi-empty">${e((err && err.error) || 'The scanner is unavailable right now.')}</div>`;
      $s('scrCount').textContent = '';
    }
    st.limit = 100;
    render();
  }

  // ---- events
  root.addEventListener('click', (ev) => {
    const t = ev.target;
    const u = t.closest('#scrUni button');
    if (u) { st.universe = u.dataset.u; store.set('js.scr.universe', st.universe); load(); return; }
    const p = t.closest('[data-p]');
    if (p) { const pr = PRESETS.find((x) => x.id === p.dataset.p); st.preset = pr.id; st.f = JSON.parse(JSON.stringify(pr.f)); st.limit = 100; render(); return; }
    const s = t.closest('[data-s]');
    if (s) { const sv = store.get('js.scr.saved', [])[+s.dataset.s]; if (sv) { Object.assign(st, { f: sv.f, sector: sv.sector || '', preset: '' }); if (sv.universe && sv.universe !== st.universe) { st.universe = sv.universe; load(); } else render(); } return; }
    const d = t.closest('[data-del]');
    if (d) { const all = store.get('js.scr.saved', []); all.splice(+d.dataset.del, 1); store.set('js.scr.saved', all); renderControls(); return; }
    const so = t.closest('[data-sort]');
    if (so) { const k = so.dataset.sort; st.sort = { key: k, dir: st.sort.key === k ? -st.sort.dir : (k === 'ticker' || k === 'sector' ? 1 : -1) }; store.set('js.scr.sort', st.sort); renderTable(); return; }
    if (t.id === 'scrMoreBtn') { st.limit += 100; renderTable(); return; }
    if (t.id === 'scrClear') { st.f = {}; st.sector = ''; st.preset = 'all'; render(); return; }
    if (t.id === 'scrColsBtn') { const box = $s('scrCols'); box.hidden = !box.hidden; t.setAttribute('aria-expanded', String(!box.hidden)); return; }
    if (t.id === 'scrSave') {
      const name = (prompt('Name this screen') || '').trim().slice(0, 40);
      if (!name) return;
      const all = store.get('js.scr.saved', []).filter((x) => x.name !== name);
      all.push({ name, f: st.f, sector: st.sector, universe: st.universe });
      store.set('js.scr.saved', all.slice(-12));
      renderControls();
      if (typeof toast === 'function') toast('Screen saved in this browser', 'ok');
      return;
    }
    if (t.id === 'scrCsv') { exportCsv(); return; }
    const tr = t.closest('tr[data-t]');
    if (tr && typeof openChart === 'function') openChart(tr.dataset.t);
  });
  root.addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter') { const tr = ev.target.closest && ev.target.closest('tr[data-t]'); if (tr && typeof openChart === 'function') openChart(tr.dataset.t); }
  });
  root.addEventListener('change', (ev) => {
    const t = ev.target;
    if (t.id === 'scrSector') { st.sector = t.value; st.preset = ''; render(); return; }
    if (t.dataset.c) { st.cols = st.data.fields.map((f) => f.key).filter((k) => (k === t.dataset.c ? t.checked : st.cols.includes(k))); store.set('js.scr.cols', st.cols); renderTable(); }
  });
  let typing;
  root.addEventListener('input', (ev) => {
    const t = ev.target;
    if (!t.dataset.k) return;
    const cur = st.f[t.dataset.k] || [null, null];
    const v = t.value.trim() === '' ? null : Number(t.value);
    cur[+t.dataset.i] = Number.isFinite(v) ? v : null;
    st.f[t.dataset.k] = cur;
    st.preset = '';
    clearTimeout(typing);
    typing = setTimeout(() => {
      renderTable();
      root.querySelectorAll('#scrPresets .chip-btn').forEach((b) => b.classList.remove('on'));
      const active = Object.values(st.f).filter(([a, b]) => a != null || b != null).length + (st.sector ? 1 : 0);
      $s('scrActive').textContent = active ? `· ${active} active` : '';
    }, 180);
  });

  function exportCsv() {
    if (!st.data) return;
    const cols = st.data.fields;
    const q = (v) => (v == null ? '' : /[",\n]/.test(String(v)) ? '"' + String(v).replace(/"/g, '""') + '"' : String(v));
    const lines = [['ticker', 'name', 'sector', ...cols.map((f) => `${f.key} (${f.unit})`)].join(',')]
      .concat(results().map((r) => [r.ticker, r.name, r.sector, ...cols.map((f) => r[f.key])].map(q).join(',')));
    const stamp = new Date().toISOString().slice(0, 16).replace(/[:T]/g, '-');
    const blob = new Blob(['# Jonathan Stocks screen, ' + st.universe + ', exported ' + new Date().toISOString() + ', quotes delayed\n' + lines.join('\n')], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `screen-${st.universe}-${stamp}.csv`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }

  // load on first visit to the screen
  let started = false;
  const start = () => { if (!started && root.classList.contains('on')) { started = true; load(); } };
  new MutationObserver(start).observe(root, { attributes: true, attributeFilter: ['class'] });
  start();
  renderControls();
})();
