/* Jonathan Stocks · global search
   One dialog for companies and symbols, opened from the top bar, from any "Search" action and with
   Ctrl/⌘ K. ARIA combobox + listbox: arrows move, Enter opens the default destination, Escape closes
   and focus returns to where it was. Every state is spelled out: recent names, searching, results,
   partial results (the wider provider did not answer), nothing found, and failure. A newer keystroke
   cancels the request still in flight, so a slow answer never overwrites a newer one. */
(function () {
  'use strict';
  const dlg = document.getElementById('gsearch');
  if (!dlg) return;
  const input = document.getElementById('gsInput');
  const list = document.getElementById('gsList');
  const status = document.getElementById('gsStatus');
  const acts = document.getElementById('gsActs');
  const T = (x) => (window.T ? window.T(x) : x);
  const e = (t) => String(t == null ? '' : t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const RECENT = 'js.gs.recent';
  let items = [], sel = -1, ctrl = null, timer = null, back = null;

  const recent = () => { try { return JSON.parse(localStorage.getItem(RECENT) || '[]'); } catch (x) { return []; } };
  function remember(it) {
    try {
      const r = recent().filter((x) => x.symbol !== it.symbol);
      r.unshift({ symbol: it.symbol, name: it.name, exch: it.exch, type: it.type });
      localStorage.setItem(RECENT, JSON.stringify(r.slice(0, 6)));
    } catch (x) { /* storage blocked: search still works */ }
  }

  // US-listed equities have filings, so Research is the default; anything else opens the chart.
  const isUsEquity = (it) => /equity/i.test(it.type || 'Equity') && !/[.=^]/.test(it.symbol);
  const DEST = {
    research: (s) => { location.hash = '#/research?t=' + encodeURIComponent(s); },
    chart: (s) => { if (typeof openChart === 'function') openChart(s); },
    compare: (s) => { location.hash = '#/relative?s=' + encodeURIComponent(s + ',SPY'); },
    lab: (s) => { location.hash = '#/lab?t=' + encodeURIComponent(s); },
    watch: (s) => { if (typeof toggleWatch === 'function') toggleWatch(s); },
  };

  function render(state, msg) {
    status.textContent = msg || '';
    status.className = 'gs-status' + (state === 'error' ? ' err' : state === 'partial' ? ' warn' : '');
    list.innerHTML = items.map((it, i) => `<li role="option" id="gs-o-${i}" aria-selected="${i === sel}" data-i="${i}">
      <b class="gs-sym">${e(it.symbol)}</b><span class="gs-nm" dir="auto">${e(it.name || '')}</span>
      <span class="gs-meta">${e([it.exch, it.type, it.index].filter(Boolean).join(' · '))}</span></li>`).join('');
    input.setAttribute('aria-expanded', items.length ? 'true' : 'false');
    if (sel >= 0 && items[sel]) input.setAttribute('aria-activedescendant', 'gs-o-' + sel);
    else input.removeAttribute('aria-activedescendant');
    renderActs();
  }
  function renderActs() {
    const it = items[sel];
    if (!it) { acts.innerHTML = ''; acts.hidden = true; return; }
    const watched = typeof S !== 'undefined' && S.watch && S.watch.includes(it.symbol);
    const b = (k, label) => `<button type="button" class="btn btn-ghost btn-sm" data-act="${k}">${label}</button>`;
    acts.hidden = false;
    acts.setAttribute('aria-label', 'Actions for ' + it.symbol);
    acts.innerHTML = (isUsEquity(it) ? b('research', 'Research <kbd>Enter</kbd>') + b('chart', 'Chart') : b('chart', 'Chart <kbd>Enter</kbd>'))
      + b('compare', 'Compare with SPY') + b('lab', 'Backtest') + b('watch', watched ? 'Remove from watchlist' : 'Add to watchlist');
  }
  function move(d) {
    if (!items.length) return;
    sel = (sel + d + items.length) % items.length;
    render('results', status.textContent);
    const li = document.getElementById('gs-o-' + sel);
    if (li) li.scrollIntoView({ block: 'nearest' });
  }
  function choose(it, act) {
    if (!it) return;
    remember(it);
    close(false);
    DEST[act || (isUsEquity(it) ? 'research' : 'chart')](it.symbol);
  }

  function idle() {
    items = recent(); sel = items.length ? 0 : -1;
    render('idle', items.length ? T('Recent') : (window.LANG && LANG() === 'he' ? 'הקלידו שם חברה או סימול. מניות בתל אביב מסתיימות ב־‎.TA (למשל TEVA.TA).' : 'Type a company name or a symbol. Tel Aviv listings end in .TA (e.g. TEVA.TA).'));
  }
  async function query(q) {
    if (ctrl) ctrl.abort();
    ctrl = new AbortController();
    status.textContent = T('Searching…'); status.className = 'gs-status';
    try {
      const r = await fetch('/api/search?q=' + encodeURIComponent(q), { signal: ctrl.signal });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      items = await r.json(); sel = items.length ? 0 : -1;
      const partial = r.headers.get('X-Search-Partial') === '1';
      if (!items.length) render('empty', `Nothing matches “${q}”. Try the company name, or the exact symbol with its exchange suffix (e.g. TEVA.TA). Enter opens “${q.toUpperCase()}” as typed.`);
      else render(partial ? 'partial' : 'results', `${items.length} result${items.length > 1 ? 's' : ''}` + (partial ? ' · index and SEC names only: the wider search did not answer, so funds and other exchanges may be missing' : ''));
    } catch (err) {
      if (err.name === 'AbortError') return;
      items = []; sel = -1;
      render('error', 'Search is unavailable right now. Enter still opens an exact symbol as typed.');
    }
  }

  function open() {
    back = document.activeElement;
    dlg.hidden = false;
    document.body.classList.add('gs-open');
    input.value = '';
    idle();
    input.focus();
  }
  function close(restore = true) {
    if (dlg.hidden) return;
    if (ctrl) ctrl.abort();
    dlg.hidden = true;
    document.body.classList.remove('gs-open');
    if (restore && back && back.focus) back.focus();
  }
  window.openSearch = open;
  window.closeSearch = close;
  window.openCmdk = open;            // older buttons and shortcuts
  window.closeCmdk = () => close();

  input.addEventListener('input', () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (!q) { if (ctrl) ctrl.abort(); idle(); return; }
    timer = setTimeout(() => query(q), 180);
  });
  input.addEventListener('keydown', (ev) => {
    if (ev.key === 'ArrowDown') { ev.preventDefault(); move(1); }
    else if (ev.key === 'ArrowUp') { ev.preventDefault(); move(-1); }
    else if (ev.key === 'Enter') {
      ev.preventDefault();
      if (items[sel]) choose(items[sel]);
      else if (input.value.trim()) choose({ symbol: input.value.trim().toUpperCase(), type: 'Equity' });
    } else if (ev.key === 'Escape') { ev.preventDefault(); ev.stopPropagation(); close(); }
  });
  list.addEventListener('mousedown', (ev) => ev.preventDefault());       // keep focus in the input
  list.addEventListener('click', (ev) => { const li = ev.target.closest('[data-i]'); if (li) choose(items[+li.dataset.i]); });
  acts.addEventListener('click', (ev) => {
    const b = ev.target.closest('[data-act]');
    if (!b || !items[sel]) return;
    if (b.dataset.act === 'watch') { DEST.watch(items[sel].symbol); setTimeout(renderActs, 400); return; }
    choose(items[sel], b.dataset.act);
  });
  dlg.addEventListener('click', (ev) => { if (ev.target === dlg) close(); });
  dlg.addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape') { ev.preventDefault(); close(); return; }
    if (ev.key !== 'Tab') return;                                         // keep Tab inside the dialog
    const f = Array.from(dlg.querySelectorAll('input, button:not([hidden])')).filter((x) => x.offsetParent !== null);
    if (!f.length) return;
    if (ev.shiftKey && document.activeElement === f[0]) { ev.preventDefault(); f[f.length - 1].focus(); }
    else if (!ev.shiftKey && document.activeElement === f[f.length - 1]) { ev.preventDefault(); f[0].focus(); }
  });
  const x = document.getElementById('gsClose');
  if (x) x.addEventListener('click', () => close());
})();
