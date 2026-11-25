/* Jonathan Stocks · Holdings and Transactions, reconciled
   Two records with two jobs. Holdings carry stops and targets and drive the Daily check, Risk and
   Alerts; Transactions carry the trade history and drive P&L and performance. No screen adds one
   to the other, so nothing is counted twice. This panel compares the quantities per symbol and
   offers one safe migration: opening buys for holdings that have no transactions. It only adds
   records, shows exactly what it will add first, and never edits or deletes either side. */
(function () {
  'use strict';
  const e = (t) => String(t == null ? '' : t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const signedIn = () => typeof S !== 'undefined' && !!S.user;
  const fmtQ = (v) => Number(v).toLocaleString('en-US', { maximumFractionDigits: 4 });

  async function holdings() { try { return await store.getPf(); } catch (x) { return []; } }
  async function transactions() {
    if (signedIn()) { try { return await api('/api/transactions'); } catch (x) { return null; } }
    try { return JSON.parse(localStorage.getItem('js_tx') || '[]'); } catch (x) { return []; }
  }
  // quantity per symbol from the history: buys add, sells subtract, a split multiplies what is held
  function ledgerQty(txs) {
    const q = {};
    txs.slice().sort((a, b) => String(a.date).localeCompare(String(b.date))).forEach((t) => {
      const k = (t.ticker || '').toUpperCase();
      if (!k) return;
      if (t.type === 'buy') q[k] = (q[k] || 0) + Number(t.qty || 0);
      else if (t.type === 'sell') q[k] = (q[k] || 0) - Number(t.qty || 0);
      else if (t.type === 'split' && q[k]) q[k] *= Number(t.ratio || 1);
    });
    Object.keys(q).forEach((k) => { if (Math.abs(q[k]) < 1e-9) delete q[k]; });
    return q;
  }

  async function compute() {
    const [pf, txs] = await Promise.all([holdings(), transactions()]);
    if (txs === null) return { error: true };
    const h = {};
    pf.forEach((p) => { const k = (p.ticker || '').toUpperCase(); h[k] = (h[k] || 0) + Number(p.qty || 0); });
    const l = ledgerQty(txs);
    const all = Array.from(new Set([...Object.keys(h), ...Object.keys(l)])).sort();
    const same = [], diff = [], onlyH = [], onlyL = [];
    all.forEach((k) => {
      if (h[k] != null && l[k] != null) (Math.abs(h[k] - l[k]) < 1e-6 ? same : diff).push(k);
      else if (h[k] != null) onlyH.push(k); else onlyL.push(k);
    });
    return { pf, txs, h, l, same, diff, onlyH, onlyL };
  }

  function html(r, where) {
    if (r.error) return '<p class="mi-foot">Could not read your transactions right now, so Holdings and Transactions were not compared.</p>';
    if (!r.pf.length && !Object.keys(r.l).length) return '';
    const parts = [];
    if (r.same.length) parts.push(`${r.same.length} match (${r.same.join(', ')})`);
    if (r.diff.length) parts.push(`${r.diff.length} differ: ${r.diff.map((k) => `${k} holdings ${fmtQ(r.h[k])}, transactions ${fmtQ(r.l[k])}`).join('; ')}`);
    if (r.onlyH.length) parts.push(`only in Holdings: ${r.onlyH.join(', ')}`);
    if (r.onlyL.length) parts.push(`only in Transactions: ${r.onlyL.join(', ')}`);
    const migr = r.onlyH.filter((k) => !/\.TA$/.test(k));
    const ta = r.onlyH.filter((k) => /\.TA$/.test(k));
    return `<details class="rc" ${r.diff.length ? 'open' : ''}><summary><b>Holdings and Transactions</b> <span class="rc-s">${e(parts.length ? parts[0] + (parts.length > 1 ? ' · …' : '') : 'nothing to compare')}</span></summary>
      <p>Holdings keep stops and drive the Daily check, Risk and Alerts. Transactions keep the trade history and drive P&amp;L and performance. They are separate records and no screen adds them together.</p>
      <ul>${parts.map((p) => `<li>${e(p)}</li>`).join('')}</ul>
      ${migr.length && where === 'ledger' ? `<p><button type="button" class="btn btn-ghost btn-sm" data-rc-migrate="${e(migr.join(','))}">Record opening buys for ${e(migr.join(', '))}</button> <small>Adds one buy per holding at its entry price, dated when it was opened (or today). Nothing is changed or removed.</small></p>` : ''}
      ${ta.length && where === 'ledger' ? `<p class="mi-foot">${e(ta.join(', '))}: Tel Aviv prices are in agorot; record these by hand in shekels so the currency is right.</p>` : ''}
      ${migr.length && where === 'portfolio' ? '<p class="mi-foot">To track P&amp;L for holdings with no transactions, open Transactions: it can record opening buys for them.</p>' : ''}
    </details>`;
  }

  async function render(where) {
    const box = document.getElementById(where === 'ledger' ? 'rcLedger' : 'rcPf');
    if (!box) return;
    box.innerHTML = html(await compute(), where);
  }

  document.addEventListener('click', async (ev) => {
    const b = ev.target.closest('[data-rc-migrate]');
    if (!b) return;
    const r = await compute();
    const want = b.dataset.rcMigrate.split(',');
    const items = r.pf.filter((p) => want.includes((p.ticker || '').toUpperCase())).map((p) => ({
      type: 'buy', date: (p.opened_at || '').slice(0, 10) || new Date().toISOString().slice(0, 10), ticker: p.ticker.toUpperCase(),
      qty: Number(p.qty), price: Number(p.entry), fee: 0, currency: 'USD', note: 'opening buy from Holdings' }));
    if (!items.length) return;
    const list = items.map((i) => `${i.ticker}: buy ${fmtQ(i.qty)} at ${i.price} on ${i.date}`).join('\n');
    if (!window.confirm(`Add these ${items.length} transactions?\n\n${list}\n\nNothing else is changed.`)) return;
    try {
      if (signedIn()) await api('/api/transactions', { method: 'POST', body: JSON.stringify({ items }) });
      else {
        const next = JSON.parse(localStorage.getItem('js_tx') || '[]').concat(items);
        await api('/api/ledger', { method: 'POST', body: JSON.stringify({ transactions: next }) });   // validates first
        localStorage.setItem('js_tx', JSON.stringify(next));
      }
      if (typeof toast === 'function') toast(`Recorded ${items.length} opening buys`, 'ok');
      document.dispatchEvent(new CustomEvent('ledgerchange'));
      render('ledger');
    } catch (err) { if (typeof toast === 'function') toast((err && err.error) || 'Could not record them', 'err'); }
  });

  // refresh whenever either screen is shown
  const watch = (id, where) => {
    const v = document.getElementById(id);
    if (!v) return;
    new MutationObserver(() => { if (v.classList.contains('on')) render(where); }).observe(v, { attributes: true, attributeFilter: ['class'] });
  };
  document.addEventListener('DOMContentLoaded', () => { watch('v-portfolio', 'portfolio'); watch('v-ledger', 'ledger'); });
  window.Reconcile = { render, ledgerQty };
})();
