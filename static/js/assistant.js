/* Jonathan Stocks · Research Assistant (Intelligence)
   Questions answered from the platform's own data by a language model, with source ids, and every
   number checked against the data sent (/api/assistant). Holdings are included only when the
   consent box is ticked for that question; it resets after each answer. */
(function () {
  'use strict';
  const root = document.getElementById('v-assistant');
  if (!root) return;
  const e = (t) => String(t == null ? '' : t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const EXAMPLES = ['How did Microsoft’s margins change over the last three years? MSFT', 'Compare free cash flow of AAPL and GOOGL',
    'How broad is the market today, and which sectors lead this year?', 'איך השתנתה הצמיחה בהכנסות של NVDA?'];

  root.innerHTML = `<div class="wrap asw">
    <div class="ph"><h1>Research Assistant</h1><p>Ask about companies and the market. Answers use only this site’s data, cite their sources, and every number is checked against that data.</p></div>
    <form id="asForm" class="mi-card as-form" autocomplete="off">
      <label for="asQ" class="sr-only">Your question</label>
      <textarea id="asQ" dir="auto" maxlength="500" rows="3" placeholder="e.g. How did MSFT's operating margin change since FY2022?" required></textarea>
      <div class="as-row">
        <label class="as-consent"><input type="checkbox" id="asConsent"> Include my holdings in this question <small>(they are sent to Google Gemini; unticked after each answer)</small></label>
        <button class="btn btn-gold btn-sm" type="submit" id="asGo">Ask</button>
      </div>
      <div class="rs-quick">${EXAMPLES.map((x) => `<button type="button" class="chip-btn" dir="auto" data-q="${e(x)}">${e(x)}</button>`).join('')}</div>
    </form>
    <div id="asOut" aria-live="polite"></div>
    <p class="mi-foot">Written by a language model from the data listed under each answer. It can still be wrong: check anything that matters against the cited source. Information only, not investment advice.</p>
    <details class="rs-defs"><summary>How the assistant works</summary><pre class="lg-pre" id="asMethod"></pre></details>
  </div>`;
  const $q = (id) => document.getElementById(id);

  function srcLink(id) {
    const m = id.match(/^SEC:([A-Z.\-]+):FY(\d+)/);
    if (m) return `<a class="chip-btn" href="#/research?t=${encodeURIComponent(m[1])}">${e(id)}</a>`;
    const p = id.match(/^PRICE:([A-Z.\-]+)/);
    if (p) return `<button type="button" class="chip-btn" data-t="${e(p[1])}">${e(id)}</button>`;
    if (id.startsWith('BREADTH') || id === 'SECTORS') return `<a class="chip-btn" href="#/home">${e(id)}</a>`;
    return `<span class="chip-btn">${e(id)}</span>`;
  }
  function render(q, d) {
    let text = e(d.answer).replace(/\[([A-Z]+:[^\]]+|SECTORS|PORTFOLIO)\]/g, '<sup class="as-cite">$1</sup>').replace(/\n/g, '<br>');
    (d.unverified || []).forEach((n) => { text = text.split(e(n)).join(`<mark class="as-unv" title="Not found in the data sent">${e(n)}</mark>`); });
    const card = document.createElement('div');
    card.className = 'mi-card as-ans';
    card.innerHTML = `<div class="as-q" dir="auto">${e(q)}</div><div class="as-a" dir="auto">${text}</div>
      ${d.unverified && d.unverified.length ? `<p class="as-warn">Not found in the data sent, so unverified: ${d.unverified.map(e).join(', ')}.</p>` : '<p class="as-ok">Every number in this answer was found in the data sent.</p>'}
      <div class="as-src"><span>Data used:</span>${(d.context_ids || []).map(srcLink).join('') || '<span class="muted">none</span>'}</div>
      <div class="as-meta">${d.portfolio_shared ? 'Your holdings were included (you consented). ' : 'Your holdings were not shared. '}Model: ${e(d.model)}.</div>`;
    $q('asOut').prepend(card);
    $q('asMethod').textContent = d.method;
  }

  async function ask(q) {
    const consent = $q('asConsent').checked;
    $q('asGo').disabled = true;
    const wait = document.createElement('div');
    wait.className = 'mi-card as-ans'; wait.innerHTML = `<div class="as-q">${e(q)}</div><div class="spinner"></div>`;
    $q('asOut').prepend(wait);
    try {
      const body = { question: q, consent };
      if (consent && !(typeof S !== 'undefined' && S.user) && typeof store !== 'undefined') body.positions = await store.getPf();
      const d = await api('/api/assistant', { method: 'POST', body: JSON.stringify(body) });
      wait.remove();
      render(q, d);
    } catch (err) {
      wait.innerHTML = `<div class="as-q">${e(q)}</div><div class="mi-empty">${e((err && err.error) || 'The assistant is unavailable right now.')}</div>`;
    } finally {
      $q('asConsent').checked = false;
      $q('asGo').disabled = false;
    }
  }
  $q('asForm').addEventListener('submit', (ev) => { ev.preventDefault(); const q = $q('asQ').value.trim(); if (q.length >= 3) ask(q); });
  root.addEventListener('click', (ev) => {
    const x = ev.target.closest('[data-q]'); if (x) { $q('asQ').value = x.dataset.q; $q('asQ').focus(); return; }
    const t = ev.target.closest('[data-t]'); if (t && typeof openChart === 'function') openChart(t.dataset.t);
  });
})();
