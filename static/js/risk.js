/* Jonathan Stocks · Portfolio Risk (Quant & Risk)
   Reviews the holdings from Portfolio > Holdings against the user's own limits (/api/risk/review)
   and sizes a new position (/api/risk/size). Limits are kept in this browser. */
(function () {
  'use strict';
  const root = document.getElementById('v-risk');
  if (!root) return;
  const e = (t) => String(t == null ? '' : t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const n2 = (v, d = 2) => (v == null ? '—' : Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }));
  const LKEY = 'js.risk.limits';
  const getL = () => { try { return JSON.parse(localStorage.getItem(LKEY) || '{}'); } catch (_) { return {}; } };
  const setL = (v) => { try { localStorage.setItem(LKEY, JSON.stringify(v)); } catch (_) { /* storage blocked */ } };
  const LIMITS = [['max_position_pct', 'Largest position', 20], ['max_sector_pct', 'Largest sector', 35],
    ['max_trade_risk_pct', 'Risk per trade', 1], ['max_portfolio_risk_pct', 'Total open risk', 6]];

  root.innerHTML = `<div class="wrap rk">
    <div class="ph"><h1>Portfolio Risk</h1><p>Your holdings against your own limits: weights, open risk to the stops, sectors, stop distance in ATR and correlation. Information, not advice.</p></div>
    <div class="rk-limits mi-card"><b>Your limits</b><span class="mi-note">% of equity · saved in this browser</span>
      ${LIMITS.map(([k, l, d]) => `<label>${l}<input type="number" step="0.1" min="0" data-l="${k}" placeholder="${d}" inputmode="decimal"></label>`).join('')}
      <button class="btn btn-ghost btn-sm" id="rkApply">Apply</button></div>
    <div id="rkBody"><div class="spinner"></div></div>
    <div class="mi-block"><div class="sec">Position size calculator <span class="tag">LONG OR SHORT</span></div>
      <form class="lg-form mi-card rk-size" id="rkSize" autocomplete="off">
        <label>Side<select name="side"><option value="long">Long</option><option value="short">Short</option></select></label>
        <label>Account equity<input name="equity" type="number" step="any" min="0" inputmode="decimal" required></label>
        <label>Risk per trade (%)<input name="risk_pct" type="number" step="0.05" min="0" value="1" inputmode="decimal" required></label>
        <label>Entry<input name="entry" type="number" step="any" min="0" inputmode="decimal" required></label>
        <label>Stop<input name="stop" type="number" step="any" min="0" inputmode="decimal" required></label>
        <label>Largest position (%)<input name="max_position_pct" type="number" step="0.5" min="0" inputmode="decimal" placeholder="no cap"></label>
        <div class="wide lg-act"><button class="btn btn-gold btn-sm" type="submit">Calculate</button><span class="auth-err" id="rkSizeErr" role="alert"></span></div>
        <div class="wide" id="rkSizeOut"></div>
      </form></div>
    <details class="rs-defs"><summary>How this is computed</summary><pre class="lg-pre" id="rkMethod"></pre></details>
  </div>`;
  const $r = (id) => document.getElementById(id);
  const lims = getL();
  root.querySelectorAll('[data-l]').forEach((i) => { if (lims[i.dataset.l] != null) i.value = lims[i.dataset.l]; });

  const LV = { high: 'High', medium: 'Check', info: 'Note' };
  function render(d) {
    $r('rkMethod').textContent = d.method;
    const t = d.totals;
    const tile = (lab, v, sub, cls) => `<div class="mi-tile"><div class="t-lab">${lab}</div><div class="t-val ${cls || ''}">${v}</div><div class="t-sub">${sub || ''}</div></div>`;
    const over = (v, lim) => (v != null && v > lim ? 'dn' : '');
    const corr = d.correlation;
    const cell = (v) => (v == null ? '<td class="n muted">—</td>' : `<td class="n cc" style="--c:${Math.max(0, v).toFixed(2)};--n:${Math.max(0, -v).toFixed(2)}">${v.toFixed(2)}</td>`);
    $r('rkBody').innerHTML = `
      <div class="mi-tiles rk-tiles">
        ${tile('Equity', n2(d.equity), d.equity_basis === 'settings' ? 'from your risk settings' : 'sum of positions: no equity set in Holdings')}
        ${tile('Invested', t.invested_pct == null ? '—' : n2(t.invested_pct, 1) + '%', n2(t.value) + ' in positions')}
        ${tile('Open risk to stops', t.open_risk_pct == null ? '—' : n2(t.open_risk_pct) + '%', n2(t.open_risk) + ' · limit ' + d.limits.max_portfolio_risk_pct + '%', over(t.open_risk_pct, d.limits.max_portfolio_risk_pct))}
        ${tile('Largest position', t.largest_weight == null ? '—' : n2(t.largest_weight, 1) + '%', 'limit ' + d.limits.max_position_pct + '%', over(t.largest_weight, d.limits.max_position_pct))}
        ${tile('Without a stop', String(t.unprotected), t.unprotected ? 'loss not defined' : d.positions.length ? 'every priced position has one' : 'no positions', t.unprotected ? 'dn' : '')}
      </div>
      <div class="mi-block"><div class="sec">Limit breaches and notes <span class="tag">${d.warnings.length}</span><span class="mi-note">conditions against your own limits, not instructions</span></div>
        <div class="mi-card">${d.warnings.length ? `<ul class="rk-warn">${d.warnings.map((w) => `<li class="lv-${w.level}"><span>${LV[w.level]}</span>${e(w.message)}</li>`).join('')}</ul>` : (() => { const n = d.positions.length, un = d.positions.filter((p) => p.price == null).length;
          if (!n) return '<div class="mi-empty">No positions to check. Nothing was evaluated.</div>';
          if (un === n) return '<div class="mi-empty">Could not check: no current price for any position. This is not a clean result.</div>';
          return `<div class="mi-empty">Checked ${n - un} of ${n} positions against your limits: none outside them.${un ? ' ' + un + ' not checked (no price).' : ''}</div>`; })()}</div></div>
      <div class="rk-grid">
        <div class="mi-block"><div class="sec">Positions</div><div class="mi-card scr-table"><table class="mi-t scr-t"><thead><tr><th class="sticky">Symbol</th><th class="n">Weight</th><th class="n">Price</th><th class="n">Stop</th><th class="n">Open risk</th><th class="n">Stop in ATR</th></tr></thead><tbody>
          ${d.positions.map((p) => `<tr data-t="${e(p.ticker)}" tabindex="0"><td class="sticky"><b>${e(p.ticker)}</b><small>${e(p.sector)}</small></td>
          <td class="n ${over(p.weight, d.limits.max_position_pct)}">${p.weight == null ? '—' : n2(p.weight, 1) + '%'}</td><td class="n">${n2(p.price)}</td>
          <td class="n">${p.stop ? n2(p.stop) : '<span class="dn">none</span>'}</td>
          <td class="n ${over(p.risk_pct, d.limits.max_trade_risk_pct)}">${p.open_risk == null ? '—' : n2(p.open_risk) + ' <small>' + n2(p.risk_pct) + '%</small>'}</td>
          <td class="n ${p.stop_atr != null && (p.stop_atr < 1 || p.stop_atr > 4) ? 'warn' : ''}">${p.stop_atr == null ? '—' : n2(p.stop_atr)}</td></tr>`).join('')}</tbody></table></div></div>
        <div class="mi-block"><div class="sec">Sectors</div><div class="mi-card rk-sec">${d.sectors.map((s) => `<div class="rk-bar"><span>${e(s.sector)}<small>${e(s.tickers.join(', '))}</small></span>
          <div class="meter"><i style="width:${Math.min(100, s.weight || 0)}%" class="${s.weight > d.limits.max_sector_pct && s.sector !== 'Other' ? 'over' : ''}"></i><b style="left:${Math.min(100, d.limits.max_sector_pct)}%"></b></div>
          <em class="${s.weight > d.limits.max_sector_pct && s.sector !== 'Other' ? 'dn' : ''}">${n2(s.weight, 1)}%</em></div>`).join('')}
          <p class="mi-foot">The mark on each bar is your ${d.limits.max_sector_pct}% sector limit.</p></div></div>
      </div>
      ${corr.tickers.length > 1 ? `<div class="mi-block"><div class="sec">Correlation <span class="tag">60 DAILY RETURNS</span></div><div class="mi-card scr-table"><table class="mi-t rk-corr"><thead><tr><th></th>${corr.tickers.map((x) => `<th class="n">${e(x)}</th>`).join('')}</tr></thead><tbody>
        ${corr.tickers.map((a, i) => `<tr><th>${e(a)}</th>${corr.matrix[i].map(cell).join('')}</tr>`).join('')}</tbody></table></div>
        <p class="mi-foot">1 = moved identically, 0 = unrelated, −1 = opposite. Pairs at 0.80 or above are listed in the findings.</p></div>` : ''}`;
  }

  async function load() {
    const body = $r('rkBody');
    body.innerHTML = '<div class="spinner"></div>';
    try {
      const signed = typeof S !== 'undefined' && S.user;
      const req = { limits: getL() };
      if (!signed && typeof store !== 'undefined') { req.positions = await store.getPf(); req.settings = await store.getSettings(); }
      const d = await api('/api/risk/review', { method: 'POST', body: JSON.stringify(req) });
      if (!d.ok) { body.innerHTML = `<div class="mi-empty">${e(d.reason)}</div>`; return; }
      render(d);
      const eq = $r('rkSize').equity;
      if (!eq.value && d.equity) eq.value = d.equity;
    } catch (err) {
      body.innerHTML = `<div class="mi-empty">${e((err && err.error) || 'The risk review is unavailable right now.')}</div>`;
    }
  }

  $r('rkApply').addEventListener('click', () => {
    const v = {};
    root.querySelectorAll('[data-l]').forEach((i) => { if (i.value !== '') v[i.dataset.l] = Number(i.value); });
    setL(v);
    load();
  });
  $r('rkSize').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const f = new FormData(ev.target);
    const body = {};
    for (const [k, v] of f.entries()) body[k] = k === 'side' ? v : (v === '' ? null : Number(v));
    $r('rkSizeErr').textContent = '';
    try {
      const s = await api('/api/risk/size', { method: 'POST', body: JSON.stringify(body) });
      $r('rkSizeOut').innerHTML = `<div class="rk-res"><div><span>Shares</span><b>${s.qty.toLocaleString('en-US')}</b></div>
        <div><span>Risk if the stop is hit</span><b>${n2(s.risk)}</b><small>${n2(s.risk_pct, 2)}% of equity</small></div>
        <div><span>Position value</span><b>${n2(s.position_value)}</b><small>${n2(s.position_pct, 1)}% of equity</small></div>
        <div><span>Stop distance</span><b>${n2(s.stop_pct)}%</b><small>${n2(s.risk_per_share, 2)} per share</small></div></div>
        ${s.capped_by_position_limit ? '<p class="mi-foot">Reduced to stay within the largest-position limit; the risk is below the budget.</p>' : ''}
        <p class="mi-foot">Shares = equity × risk % ÷ |entry − stop|, rounded down. Gaps can move past a stop, so the loss can be larger.</p>`;
    } catch (err) { $r('rkSizeErr').textContent = (err && err.error) || 'Could not calculate.'; }
  });
  root.addEventListener('click', (ev) => { const tr = ev.target.closest('tr[data-t]'); if (tr && typeof openChart === 'function') openChart(tr.dataset.t); });

  const start = () => { if (root.classList.contains('on')) load(); };
  new MutationObserver(start).observe(root, { attributes: true, attributeFilter: ['class'] });
  start();
})();
