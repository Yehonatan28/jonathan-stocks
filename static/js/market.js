/* Jonathan Stocks · Market Intelligence (Market Overview)
   Breadth over every S&P 500 member, sector funds against the index, the cross-asset
   snapshot, and the day's leaders and laggards. Every figure comes from /api/market/*;
   a figure the server could not compute is shown as a dash, never as zero. */
(function () {
  'use strict';
  const el = (id) => document.getElementById(id);
  const e = (t) => String(t == null ? '' : t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const num = (v, d = 2) => (v == null || isNaN(v) ? '—' : Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }));
  const pct = (v, d = 2) => (v == null ? '—' : (v > 0 ? '+' : '') + num(v, d) + '%');
  const pp = (v) => (v == null ? '—' : (v > 0 ? '+' : '') + num(v, 1) + ' pp');
  const tone = (v) => (v == null || v === 0 ? '' : v > 0 ? 'up' : 'dn');
  const unavailable = (box, msg) => { if (box) box.innerHTML = `<div class="mi-empty">${e(msg || 'Unavailable right now. Nothing is shown in its place.')}</div>`; };

  // ---- breadth
  function gauge(label, part, hint) {
    const p = part && part.pct != null ? part.pct : null;
    return `<div class="mi-tile"><div class="t-lab">${label}</div>
      <div class="t-val ${p == null ? '' : p >= 50 ? 'up' : 'dn'}">${p == null ? '—' : num(p, 1) + '%'}</div>
      <div class="meter"><i style="width:${p == null ? 0 : p}%"></i></div>
      <div class="t-sub">${part && part.of ? `${part.above} of ${part.of} members` : 'no data'} · ${hint}</div></div>`;
  }
  function renderBreadth(b) {
    const total = b.advancers + b.decliners + b.unchanged;
    const share = total ? b.advancers / total : null;
    const word = share == null ? '—' : share > 0.66 ? 'Broad advance' : share > 0.55 ? 'Leaning up' : share >= 0.45 ? 'Mixed' : share >= 0.34 ? 'Leaning down' : 'Broad decline';
    if (el('pulseTxt')) { el('pulseTxt').textContent = word; el('pulseTxt').className = 'b-big ' + (share == null ? '' : share > 0.55 ? 'up' : share < 0.45 ? 'dn' : ''); }
    if (el('pulseSub')) el('pulseSub').textContent = `${b.advancers} up · ${b.decliners} down · ${b.unchanged} flat of ${b.priced} priced`;
    if (el('adBar') && total) el('adBar').innerHTML = `<i class="a" style="flex:${b.advancers}"></i><i class="u" style="flex:${b.unchanged}"></i><i class="d" style="flex:${b.decliners}"></i>`;
    el('brNote').textContent = `${b.priced} of ${b.members} members priced`;
    el('brTiles').innerHTML =
      `<div class="mi-tile"><div class="t-lab">Advance / decline</div><div class="t-val">${b.advancers}<span class="sl"> / </span>${b.decliners}</div>
        <div class="t-sub">ratio ${b.ad_ratio == null ? '—' : num(b.ad_ratio, 2)} · ${b.unchanged} unchanged</div></div>` +
      gauge('Above 50-day average', b.above_50d, 'short-term trend') +
      gauge('Above 200-day average', b.above_200d, 'long-term trend') +
      `<div class="mi-tile"><div class="t-lab">Near 52-week high / low</div><div class="t-val"><span class="up">${b.near_52w_high.count}</span><span class="sl"> / </span><span class="dn">${b.near_52w_low.count}</span></div>
        <div class="t-sub">within 2% · of ${b.near_52w_high.of} with a 52-week range</div></div>` +
      `<div class="mi-tile"><div class="t-lab">Average move today</div><div class="t-val ${tone(b.cap_weighted_chg)}">${pct(b.cap_weighted_chg)}</div>
        <div class="t-sub">cap-weighted · equal-weighted <b class="${tone(b.equal_weighted_chg)}">${pct(b.equal_weighted_chg)}</b></div></div>`;
    const rowsOf = (list) => list.length ? `<table class="mi-t"><tbody>${list.map((r) =>
      `<tr tabindex="0" data-t="${e(r.ticker)}"><td class="sym">${e(r.ticker)}</td><td class="nm">${e(r.name || '')}<small>${e(r.sector || '')}</small></td>
       <td class="n">${num(r.price)}</td><td class="n ${tone(r.chg)}">${pct(r.chg)}</td></tr>`).join('')}</tbody></table>` : '<div class="mi-empty">No data</div>';
    el('leaders').innerHTML = rowsOf(b.leaders || []);
    el('laggards').innerHTML = rowsOf(b.laggards || []);
  }

  // ---- sectors
  const PERIODS = ['1D', '1W', '1M', '3M', 'YTD'];
  let secData = null;
  let period = '1M';
  try { period = localStorage.getItem('js.secPeriod') || '1M'; } catch (_) { /* storage blocked */ }
  if (!PERIODS.includes(period)) period = '1M';
  function renderSectors() {
    const seg = el('secPeriods');
    seg.innerHTML = PERIODS.map((p) => `<button type="button" role="tab" aria-selected="${p === period}" class="${p === period ? 'on' : ''}" data-p="${p}">${p}</button>`).join('');
    if (!secData) return;
    const bench = secData.benchmark.returns[period];
    const rows = secData.sectors.slice().sort((a, b) => (b.vs_benchmark[period] ?? -1e9) - (a.vs_benchmark[period] ?? -1e9));
    const span = Math.max(1, ...rows.map((r) => Math.abs(r.vs_benchmark[period] || 0)));
    el('secTable').innerHTML = `<table class="mi-t"><thead><tr><th>Sector</th><th class="n">Return</th><th class="bar-h">vs S&amp;P 500</th></tr></thead><tbody>` +
      rows.map((r) => {
        const v = r.vs_benchmark[period];
        const w = v == null ? 0 : Math.abs(v) / span * 50;
        return `<tr><td class="nm">${e(r.sector)}<small>${e(r.etf)}</small></td><td class="n ${tone(r.returns[period])}">${pct(r.returns[period])}</td>
          <td class="bar-c"><div class="rel"><i class="${v >= 0 ? 'pos' : 'neg'}" style="width:${w}%;${v >= 0 ? 'left:50%' : 'right:50%'}"></i></div><span class="${tone(v)}">${pp(v)}</span></td></tr>`;
      }).join('') +
      `</tbody><tfoot><tr><td class="nm">S&amp;P 500<small>SPY</small></td><td class="n ${tone(bench)}">${pct(bench)}</td><td class="bar-c"><span>benchmark</span></td></tr></tfoot></table>`;
    const asOf = secData.sectors.map((s) => s.as_of).filter(Boolean).sort().pop();
    el('secFoot').textContent = `Closing prices${asOf ? ' to ' + asOf : ''}. ` + (secData.method || '');
  }
  el('secPeriods') && el('secPeriods').addEventListener('click', (ev) => {
    const b = ev.target.closest('button[data-p]');
    if (!b) return;
    period = b.dataset.p;
    try { localStorage.setItem('js.secPeriod', period); } catch (_) { /* storage blocked */ }
    renderSectors();
  });

  // ---- cross-asset snapshot (indices already have their own boards above)
  function renderSnapshot(list) {
    const groups = ['Rates', 'Currencies', 'Commodities', 'Crypto'];
    el('snapTable').innerHTML = `<table class="mi-t"><tbody>` + groups.map((g) => {
      const items = list.filter((r) => r.group === g);
      return `<tr class="grp"><th colspan="3">${g}</th></tr>` + items.map((r) => {
        if (r.status === 'unavailable') return `<tr><td class="nm">${e(r.label)}</td><td class="n">—</td><td class="n muted">unavailable</td></tr>`;
        const val = r.kind === 'yield' ? num(r.price, 3) + '%' : num(r.price, r.price < 10 ? 4 : 2);
        const chg = r.kind === 'yield'
          ? `<td class="n ${tone(r.chg_bp)}">${r.chg_bp == null ? '—' : (r.chg_bp > 0 ? '+' : '') + num(r.chg_bp, 1) + ' bp'}</td>`
          : `<td class="n ${tone(r.chg)}">${pct(r.chg)}</td>`;
        return `<tr><td class="nm">${e(r.label)}<small>${e(r.symbol)}</small></td><td class="n">${val}</td>${chg}</tr>`;
      }).join('');
    }).join('') + `</tbody></table>`;
  }

  // ---- loading
  let loadedAt = 0;
  async function load(force) {
    if (!force && Date.now() - loadedAt < 60000) return;
    loadedAt = Date.now();
    const get = (u) => api(u).then((j) => ({ ok: true, j })).catch((j) => ({ ok: false, j }));
    renderSectors();
    const [br, sec, snap] = await Promise.all([get('/api/market/breadth?index=sp500'), get('/api/market/sectors'), get('/api/market/snapshot')]);
    if (br.ok && br.j.ok) renderBreadth(br.j); else { unavailable(el('brTiles')); unavailable(el('leaders')); unavailable(el('laggards')); if (el('pulseSub')) el('pulseSub').textContent = 'Breadth unavailable right now'; }
    if (sec.ok && sec.j.ok) { secData = sec.j; renderSectors(); } else unavailable(el('secTable'));
    if (snap.ok && snap.j.ok) renderSnapshot(snap.j.instruments); else unavailable(el('snapTable'));
  }
  document.addEventListener('click', (ev) => {
    const tr = ev.target.closest('#leaders tr[data-t], #laggards tr[data-t]');
    if (tr && typeof openChart === 'function') openChart(tr.dataset.t);
  });
  document.addEventListener('keydown', (ev) => {
    if (ev.key !== 'Enter') return;
    const tr = ev.target.closest && ev.target.closest('#leaders tr[data-t], #laggards tr[data-t]');
    if (tr && typeof openChart === 'function') openChart(tr.dataset.t);
  });
  window.MarketIntel = { load };
  if (el('v-home')) load(true);
  setInterval(() => { const v = el('v-home'); if (v && v.classList.contains('on') && !document.hidden) load(true); }, 120000);
})();
