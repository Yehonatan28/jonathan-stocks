/* Jonathan Stocks · Alerts (Quant & Risk)
   Price, change, RSI, moving-average crosses, volume, earnings and stop proximity. Checked by the
   server on opening and every two minutes while the app is open (/api/alerts/evaluate). Alerts
   live in the account, or in this browser for a guest; the trigger history stays in this browser. */
(function () {
  'use strict';
  const root = document.getElementById('v-alertsx');
  if (!root) return;
  const e = (t) => String(t == null ? '' : t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const KINDS = [['above', 'Price rises above', 'price', 100], ['below', 'Price falls below', 'price', 100],
    ['chg_above', 'Day change above (%)', '%', 3], ['chg_below', 'Day change below (%)', '%', -3],
    ['rsi_above', 'RSI(14) above', 'level', 70], ['rsi_below', 'RSI(14) below', 'level', 30],
    ['cross_above_ma', 'Close crosses above MA', 'period', 50], ['cross_below_ma', 'Close crosses below MA', 'period', 50],
    ['relvol_above', 'Relative volume above (×)', 'ratio', 2], ['earnings_within', 'Earnings within (trading days)', 'days', 5],
    ['near_stop', 'Within % of my stop', '%', 3]];
  const HKEY = 'js.alert.history';
  const hist = { get() { try { return JSON.parse(localStorage.getItem(HKEY) || '[]'); } catch (_) { return []; } },
    add(x) { try { const h = [x].concat(hist.get()).slice(0, 100); localStorage.setItem(HKEY, JSON.stringify(h)); } catch (_) { /* blocked */ } } };
  const label = (c) => { const [k, p] = String(c).split(':'); const f = KINDS.find((x) => x[0] === k); return f ? f[1] + (p ? ' ' + p : '') : c; };

  root.innerHTML = `<div class="wrap alw">
    <div class="ph"><h1>Alerts</h1><p>Price, change, RSI, moving-average crosses, volume, earnings and distance to your stops. Checked while the app is open; nothing is sent by email.</p></div>
    <form class="lg-form mi-card al-form" id="alxForm" autocomplete="off">
      <label>Symbol<input name="ticker" maxlength="15" placeholder="AAPL" spellcheck="false" required></label>
      <label>When<select name="kind">${KINDS.map(([k, l]) => `<option value="${k}">${e(l)}</option>`).join('')}</select></label>
      <label>Value<input name="value" type="number" step="any" required inputmode="decimal"></label>
      <div class="lg-act"><button class="btn btn-gold btn-sm" type="submit">Add alert</button><span class="auth-err" id="alxErr" role="alert"></span></div>
    </form>
    <div class="mi-block"><div class="sec">Your alerts <span class="mi-note" id="alxChecked"></span>
      <button class="btn btn-ghost btn-sm" id="alxNotify" type="button">Browser notifications</button><button class="btn btn-ghost btn-sm" id="alxCheck" type="button">Check now</button></div>
      <div class="mi-card scr-table" id="alxList"><div class="spinner"></div></div></div>
    <div class="mi-block"><div class="sec">Triggered <span class="mi-note">kept in this browser</span></div><div class="mi-card scr-table" id="alxHist"></div></div>
    <details class="rs-defs"><summary>How alerts are checked</summary><pre class="lg-pre" id="alxMethod"></pre></details>
  </div>`;
  const $a = (id) => document.getElementById(id);
  const form = $a('alxForm');
  const syncDefault = () => { const k = KINDS.find((x) => x[0] === form.kind.value); form.value.value = k[3]; };
  form.kind.addEventListener('change', syncDefault);
  syncDefault();

  const was = {};
  function renderHist() {
    const h = hist.get();
    $a('alxHist').innerHTML = h.length ? `<table class="mi-t"><thead><tr><th>When</th><th>Symbol</th><th>Alert</th><th>At the time</th></tr></thead><tbody>
      ${h.map((x) => `<tr><td>${e(new Date(x.at).toLocaleString())}</td><td><b>${e(x.ticker)}</b></td><td>${e(x.label)}</td><td>${e(x.detail)}</td></tr>`).join('')}</tbody></table>`
      : '<div class="mi-empty">Nothing has triggered yet.</div>';
  }

  async function check() {
    let list = [];
    try { list = await store.getAlerts(); } catch (_) { list = []; }
    if (!list.length) { $a('alxList').innerHTML = '<div class="mi-empty">No alerts yet. Add one above.</div>'; return; }
    let res;
    try {
      const signed = typeof S !== 'undefined' && S.user;
      res = await api('/api/alerts/evaluate', { method: 'POST', body: JSON.stringify(signed ? {} : { alerts: list, positions: await store.getPf() }) });
    } catch (err) { $a('alxList').innerHTML = `<div class="mi-empty">${e((err && err.error) || 'Alerts could not be checked right now.')}</div>`; return; }
    $a('alxMethod').textContent = res.method;
    $a('alxChecked').textContent = 'checked ' + new Date(res.checked_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const byId = {};
    res.results.forEach((r) => { byId[String(r.id)] = r; });
    $a('alxList').innerHTML = `<table class="mi-t scr-t"><thead><tr><th class="sticky">Symbol</th><th>Alert</th><th class="n">Value</th><th>Status</th><th>Now</th><th></th></tr></thead><tbody>
      ${list.map((a) => { const r = byId[String(a.id)] || {}; const st = r.met === true ? '<span class="al-on">Triggered</span>' : r.met === false ? '<span class="al-off">Waiting</span>' : '<span class="muted">No data</span>';
        return `<tr data-t="${e(a.ticker)}" class="${r.met ? 'mine' : ''}"><td class="sticky"><b>${e(a.ticker)}</b></td><td>${e(label(a.condition))}</td><td class="n">${e(a.price)}</td><td>${st}</td><td class="muted">${e(r.detail || '')}</td>
        <td class="n"><button class="x" data-del="${a.id}" aria-label="Delete this alert">×</button></td></tr>`; }).join('')}</tbody></table>`;
    res.results.forEach((r) => {
      const k = String(r.id);
      if (r.met && was[k] === false) {
        const msg = `${r.ticker}: ${label(r.condition)} ${r.price} (${r.detail})`;
        hist.add({ at: Date.now(), ticker: r.ticker, label: label(r.condition) + ' ' + r.price, detail: r.detail });
        if (typeof toast === 'function') toast(msg, 'ok');
        try { if (window.Notification && Notification.permission === 'granted') new Notification('Jonathan Stocks alert', { body: msg }); } catch (_) { /* unsupported */ }
      }
      if (r.met && was[k] === undefined) hist.get().some((x) => x.ticker === r.ticker && x.label === label(r.condition) + ' ' + r.price) || hist.add({ at: Date.now(), ticker: r.ticker, label: label(r.condition) + ' ' + r.price, detail: r.detail });
      was[k] = !!r.met;
    });
    renderHist();
  }

  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    $a('alxErr').textContent = '';
    const kind = form.kind.value, v = Number(form.value.value);
    const cond = kind.includes('_ma') ? `${kind}:${Math.round(v)}` : kind;
    // the same limits the server applies to signed-in users, so a guest cannot store a rule that never evaluates
    const unit = KINDS.find((x) => x[0] === kind)[2];
    const bad = !Number.isFinite(v) ? 'Enter a number'
      : unit === 'price' && v <= 0 ? 'The price must be above zero'
      : unit === 'level' && !(v > 0 && v < 100) ? 'The RSI level must be between 0 and 100'
      : unit === 'period' && !(v >= 5 && v <= 250) ? 'The moving average period must be between 5 and 250'
      : (unit === 'ratio' || unit === 'days') && v <= 0 ? 'The value must be above zero' : '';
    if (bad) { $a('alxErr').textContent = bad; return; }
    try {
      await store.addAlert({ ticker: form.ticker.value.trim().toUpperCase(), condition: cond, price: v });
      form.ticker.value = '';
      if (typeof S !== 'undefined') S.alerts = await store.getAlerts();
      check();
    } catch (err) { $a('alxErr').textContent = (err && err.error) || 'Could not add the alert.'; }
  });
  root.addEventListener('click', async (ev) => {
    const d = ev.target.closest('[data-del]');
    if (d) { await store.delAlert(d.dataset.del).catch(() => {}); if (typeof S !== 'undefined') S.alerts = await store.getAlerts(); check(); return; }
    if (ev.target.id === 'alxCheck') { check(); return; }
    if (ev.target.id === 'alxNotify') {
      if (!window.Notification) { toast && toast('This browser does not support notifications', 'err'); return; }
      const p = await Notification.requestPermission();
      ev.target.textContent = p === 'granted' ? 'Notifications on' : 'Notifications blocked';
      return;
    }
    const tr = ev.target.closest('tr[data-t]'); if (tr && typeof openChart === 'function') openChart(tr.dataset.t);
  });
  renderHist();
  let timer = null;
  const start = () => {
    if (root.classList.contains('on')) { check(); if (!timer) timer = setInterval(() => { if (!document.hidden) check(); }, 120000); }
  };
  new MutationObserver(start).observe(root, { attributes: true, attributeFilter: ['class'] });
  start();
})();
