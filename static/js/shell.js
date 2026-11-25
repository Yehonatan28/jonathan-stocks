/* Jonathan Stocks · application shell
   Four areas (Market, Research, Portfolio, Lab), each a group of modules shown as tabs. Desktop: a sidebar. Tablet: an icon rail. Phone: a bottom
   tab bar whose workspace opens a sheet of its modules. Every module has an address (#/<module>) so it
   can be bookmarked or shared, and the browser's back button moves between modules.
   Only modules that exist and work are listed; new ones are added here as they ship. */
(function () {
  'use strict';

  const ICONS = {
    market: '<path d="M3 17l5-6 4 3 6-8 3 3"/><path d="M3 21h18"/>',
    research: '<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5.5 5.5"/><path d="M8 11l2-2 2 2"/>',
    portfolio: '<rect x="3" y="7" width="18" height="13" rx="1.5"/><path d="M8 7V5a1.5 1.5 0 0 1 1.5-1.5h5A1.5 1.5 0 0 1 16 5v2"/><path d="M3 12h18"/>',
    quant: '<path d="M4 20V10"/><path d="M10 20V4"/><path d="M16 20v-7"/><path d="M22 20H2"/>',
    intel: '<path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z"/><path d="M18 15l.9 2.1L21 18l-2.1.9L18 21l-.9-2.1L15 18l2.1-.9z"/>',
  };
  const svg = (k) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[k]}</svg>`;

  /* Four areas. Each module: v (view id, also its address), name (tab label), title (page heading),
     desc (one sentence: what you get here), act (the one primary action), sym (how the current
     symbol is carried into it: 't' = ?t=SYM, 's' = ?s=SYM). Old addresses keep working because
     view ids did not change. */
  const WORKSPACES = [
    { id: 'market', name: 'Market', short: 'Market', icon: 'market', modules: [
      { v: 'home', name: 'Overview', title: 'Market overview', desc: 'What moved today, how broad the move was, and what to look at next.', act: ['Search a company', 'search'] },
      { v: 'heatmap', name: 'Heatmap', title: 'Market heatmap', desc: 'Every S&P 500 member by sector, sized by market value and coloured by today’s change.', act: ['Search a company', 'search'] },
      { v: 'news', name: 'News', title: 'Market news', desc: 'Headlines from US and Israeli publishers, deduplicated, with a feed per symbol.', act: null },
      { v: 'calendar', name: 'Calendar', title: 'Calendar', desc: 'Earnings, economic releases and dividends for the next two weeks; your names are marked.', act: null } ] },
    { id: 'research', name: 'Research', short: 'Research', icon: 'research', modules: [
      { v: 'research', name: 'Company', title: 'Company research', desc: 'Statements as filed with the SEC, five years and eight quarters, every ratio with its formula.', act: ['Find a company', 'focus:#v-research input'], sym: 't' },
      { v: 'screener', name: 'Screener', title: 'Stock screener', desc: 'Filter the S&P 500 and Nasdaq-100; each filter shows how many names have the field.', act: ['Save this screen', 'click:#scrSave'] },
      { v: 'relative', name: 'Compare', title: 'Compare & correlate', desc: 'Up to eight symbols on the same days: return from 100, risk, drawdown, beta and correlation.', act: ['Add symbols', 'focus:#v-relative input'], sym: 's' },
      { v: 'compare', name: 'Trend view', title: 'Trend comparison', desc: 'Two symbols side by side on the trend engine’s daily reading.', act: ['Choose symbols', 'focus:#v-compare input'] },
      { v: 'assistant', name: 'Assistant', title: 'Research assistant', desc: 'Questions answered only from this site’s data, with sources, and every number checked.', act: ['Ask a question', 'focus:#v-assistant textarea'] } ] },
    { id: 'portfolio', name: 'Portfolio', short: 'Portfolio', icon: 'portfolio', modules: [
      { v: 'portfolio', name: 'Holdings', title: 'Holdings', desc: 'Your open positions with stops, value and profit at delayed prices.', act: ['Add a position', 'focus:#pfTicker'] },
      { v: 'ledger', name: 'Transactions', title: 'Transactions & P&L', desc: 'Buys, sells, dividends and splits; cost and gains first-in, first-out, per currency.', act: ['Record a transaction', 'focus:#v-ledger form input, #v-ledger form select'] },
      { v: 'watchlist', name: 'Watchlist', title: 'Watchlist', desc: 'Names you follow; the daily check scans them for technical setups.', act: ['Add a symbol', 'search'] },
      { v: 'command', name: 'Daily check', title: 'Daily check', desc: 'Your stop and exit rules evaluated on the last daily close, with what was and was not checked.', act: ['Run the check again', 'call:loadPlan'] },
      { v: 'risk', name: 'Risk', title: 'Portfolio risk', desc: 'Exposure and limit breaches first: weights, open risk to stops, sectors and correlation.', act: ['Size a position', 'focus:#rkSize select, #rkSize input'] },
      { v: 'alertsx', name: 'Alerts', title: 'Alerts', desc: 'Rules on price, RSI, averages, volume and earnings. Checked only while this site is open.', act: ['Create an alert', 'focus:#v-alertsx form input, #v-alertsx form select'] } ] },
    { id: 'lab', name: 'Lab', short: 'Lab', icon: 'quant', modules: [
      { v: 'lab', name: 'Strategy Lab', title: 'Strategy Lab', desc: 'Your entry and exit rules on daily history against buy and hold, with costs and next-open fills.', act: ['Run the backtest', 'click:#labForm [type=submit]'], sym: 't' },
      { v: 'backtest', name: 'Engine replay', title: 'Engine replay', desc: 'The daily check’s own rules replayed on one symbol’s history.', act: ['Choose a symbol', 'focus:#v-backtest input'] },
      { v: 'gaps', name: 'Gaps', title: 'Gap detection', desc: 'Overnight gaps measured in ATR, and whether the day filled them.', act: null } ] },
  ];
  const byView = {};
  WORKSPACES.forEach((w) => w.modules.forEach((m) => { byView[m.v] = { ws: w, mod: m }; }));
  const $ = (id) => document.getElementById(id);
  const T = (x) => (window.T ? window.T(x) : x);

  function renderSide() {
    const side = $('side');
    if (!side) return;
    side.innerHTML =
      '<a class="side-brand" href="#/home" aria-label="Jonathan Stocks home"><span class="mark">JS</span>' +
      '<div><b>Jonathan Stocks</b><small>Financial intelligence</small></div></a>' +
      WORKSPACES.map((w) => `<nav class="ws" data-ws="${w.id}" aria-label="${T(w.name)}">
        <div class="ws-h" title="${T(w.name)}" data-first="${w.modules[0].v}">${svg(w.icon)}<span>${T(w.name)}</span></div>
        ${w.modules.map((m) => `<a href="#/${m.v}" data-v="${m.v}">${T(m.name)}</a>`).join('')}</nav>`).join('') +
      '<div class="side-foot">Market data: delayed or end-of-day unless marked live. Information only, not investment advice.' +
      '<nav class="side-links" aria-label="About"><a href="/about">About</a><a href="/methodology">Methodology</a><a href="/privacy">Privacy</a><a href="/terms">Terms</a></nav></div>';
    side.querySelectorAll('.ws-h').forEach((h) => h.addEventListener('click', () => { location.hash = '#/' + h.dataset.first; }));
  }

  function renderTabbar() {
    const bar = $('tabbar');
    if (!bar) return;
    bar.innerHTML = WORKSPACES.map((w) => `<button type="button" data-ws="${w.id}" aria-label="${T(w.name)}">${svg(w.icon)}<span>${T(w.short)}</span></button>`).join('');
    bar.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => {
      const w = WORKSPACES.find((x) => x.id === b.dataset.ws);
      if (w.modules.length === 1) { closeSheet(); location.hash = '#/' + w.modules[0].v; return; }
      openSheet(w);
    }));
  }

  function openSheet(w) {
    const sh = $('sheet');
    const cur = (location.hash.match(/^#\/([a-z]+)/) || [])[1];
    sh.innerHTML = `<h4>${T(w.name)}</h4>` + w.modules.map((m) => `<a href="#/${m.v}" class="${m.v === cur ? 'on' : ''}">${T(m.name)}</a>`).join('');
    sh.classList.add('open');
    sh.querySelectorAll('a').forEach((a) => a.addEventListener('click', closeSheet));
  }
  function closeSheet() { const sh = $('sheet'); if (sh) sh.classList.remove('open'); }

  // ---- context carried between tools: the last symbol seen in an address (?t= or ?s=)
  const CTX_KEY = 'js.ctx.sym';
  function readCtx() {
    const m = location.hash.match(/[?&][ts]=([A-Za-z0-9.\-^=]+)/);
    if (m) { try { sessionStorage.setItem(CTX_KEY, decodeURIComponent(m[1]).split(',')[0].toUpperCase()); } catch (e) { /* private mode */ } }
    try { return sessionStorage.getItem(CTX_KEY) || ''; } catch (e) { return ''; }
  }
  const hrefOf = (m, sym) => '#/' + m.v + (sym && m.sym ? '?' + m.sym + '=' + encodeURIComponent(sym) : '');

  function runAct(spec) {
    const [kind, arg] = [spec.split(':')[0], spec.slice(spec.indexOf(':') + 1)];
    if (kind === 'search') { if (window.openSearch) window.openSearch(); else if (window.openCmdk) window.openCmdk(); return; }
    if (kind === 'call') { if (typeof window[arg] === 'function') window[arg](true); return; }
    const el = document.querySelector(arg);
    if (!el) return;
    el.scrollIntoView({ block: 'center', behavior: 'smooth' });
    if (kind === 'click') el.click(); else el.focus({ preventScroll: true });
  }

  // One header per screen: the area's tabs, the screen's title, what it is for, one primary action.
  function renderHead(v) {
    const ph = $('pagehead'), hit = byView[v];
    if (!ph || !hit) return;
    const sym = readCtx(), { ws, mod } = hit;
    ph.innerHTML = `<nav class="ph-tabs" aria-label="${T(ws.name)}">${ws.modules.map((m) =>
      `<a href="${hrefOf(m, sym)}"${m.v === v ? ' aria-current="page"' : ''}>${T(m.name)}</a>`).join('')}</nav>
      <div class="ph-row"><div class="ph-txt"><h1 id="pageTitle">${T(mod.title)}</h1><p>${T(mod.desc)}</p></div>
      ${mod.act ? `<button type="button" class="btn btn-gold btn-sm ph-act">${T(mod.act[0])}</button>` : ''}</div>`;
    const b = ph.querySelector('.ph-act');
    if (b) b.addEventListener('click', () => runAct(mod.act[1]));
    ph.querySelectorAll('.ph-tabs a').forEach((a) => a.addEventListener('mousedown', () => {
      const s2 = readCtx(); const m = ws.modules.find((x) => '#/' + x.v === a.getAttribute('href').split('?')[0]);
      if (m) a.setAttribute('href', hrefOf(m, s2));
    }));
  }

  function mark(v) {
    const hit = byView[v];
    renderHead(v);
    document.querySelectorAll('.ws a').forEach((a) => a.classList.toggle('on', a.dataset.v === v));
    document.querySelectorAll('.ws').forEach((n) => n.classList.toggle('on', hit && n.dataset.ws === hit.ws.id));
    document.querySelectorAll('.tabbar button').forEach((b) => b.classList.toggle('on', hit && b.dataset.ws === hit.ws.id));
    const c = $('crumbs');
    if (c && hit) c.innerHTML = `<span>${T(hit.ws.name)}</span><i>/</i><b>${T(hit.mod.title)}</b>`;
    if (hit) document.title = `${T(hit.mod.title)} · Jonathan Stocks`;
    if (hit) { curView = v; renderProv(); }
  }

  // The existing modules switch with go(view). Route every switch through the address bar, and
  // follow the address bar back into go(), so links, bookmarks and the back button all work.
  const legacyGo = window.go;
  let fromHash = false;
  window.go = function (v) {
    legacyGo(v);
    mark(v);
    if (!fromHash && location.hash !== '#/' + v) history.pushState(null, '', '#/' + v);
  };
  const MOVED = { alerts: 'alertsx', quant: 'command', intel: 'assistant' };   // old addresses
  function route() {
    let v = (location.hash.match(/^#\/([a-z]+)/) || [])[1];
    if (v && MOVED[v]) { v = MOVED[v]; history.replaceState(null, '', '#/' + v); }
    if (!v || !byView[v]) return false;
    fromHash = true;
    try { window.go(v); } finally { fromHash = false; }
    return true;
  }
  window.addEventListener('hashchange', route);
  window.addEventListener('popstate', route);

  // ---- data provenance: every data answer carries its source, status and retrieval time in
  // headers (see provenance.py). Each screen lists the datasets it loaded while it was open.
  const PROV = {};          // dataset id -> {source, status, at}
  // which datasets each screen shows; a dataset appears once this browser has loaded it
  const VIEW_DATA = { home: ['quotes', 'feargreed', 'breadth', 'sectors', 'snapshot', 'digest'], heatmap: ['heatmap', 'treemap'],
    compare: ['stock', 'quotes', 'chart', 'profile'], portfolio: ['quotes'], watchlist: ['quotes'],
    command: ['engine', 'quotes'], gaps: ['gaps'], backtest: ['engine', 'chart'], alerts: ['quotes'], news: ['news'], screener: ['scan'], research: ['company', 'quotes'], ledger: ['ledger'], risk: ['risk'], lab: ['lab'], relative: ['relative', 'company'], calendar: ['calendar'], alertsx: ['alerts'], assistant: ['assistant'] };
  let curView = 'home';
  const STATUS = { delayed: 'Delayed', eod: 'End of day', reported: 'As filed', estimated: 'Estimated', stale: 'Stale', published: 'As published',
    scheduled: 'Schedule', derived: 'From site data', reference: 'Reference', unavailable: 'Unavailable', live: 'Live' };
  // the badge shows the least fresh price status on the screen; non-price statuses rank after prices
  const RANK = { unavailable: 0, stale: 0.5, estimated: 1, delayed: 2, eod: 3, reported: 4, published: 5, scheduled: 6, derived: 7, reference: 8, live: 9 };
  const NAMES = { quotes: 'Quotes', heatmap: 'Heatmap', treemap: 'Sector map', gaps: 'Gap scan', chart: 'Price history',
    stock: 'Trend analysis', engine: 'Risk engine', feargreed: 'Fear & Greed', earnings: 'Earnings',
    analyst: 'Analyst estimates', profile: 'Company profile', news: 'News', search: 'Symbol search',
    company: 'Company financials', ledger: 'Portfolio valuation', risk: 'Holdings and daily bars', lab: 'Strategy backtest', relative: 'Comparison', calendar: 'Calendar', alerts: 'Alerts', digest: 'Your names today', assistant: 'Research assistant', breadth: 'Market breadth', sectors: 'Sector performance', snapshot: 'Rates, FX, commodities', scan: 'Stock scanner' };
  const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const hhmm = (d) => d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  function age(d) {
    const s = Math.max(0, (Date.now() - d.getTime()) / 1000);
    if (s < 60) return 'just now';
    if (s < 3600) return Math.round(s / 60) + ' min ago';
    if (s < 86400) return Math.round(s / 3600) + ' h ago';
    return Math.round(s / 86400) + ' d ago';
  }
  window.noteProv = function (r) {
    const id = r.headers.get('X-Data-Set');
    if (!id || id === 'search') return;
    const at = new Date(r.headers.get('X-Data-Retrieved') || Date.now());
    const ob = r.headers.get('X-Data-Observed');
    PROV[id] = { source: r.headers.get('X-Data-Source') || '', status: r.headers.get('X-Data-Status') || 'delayed', at, observed: ob || null };
    renderProv();
    document.dispatchEvent(new CustomEvent('prov', { detail: id }));
  };
  window.provOf = (id) => PROV[id] || null;      // for screens that print a basis line
  setTimeout(() => { (window.__provQ || []).splice(0).forEach((r) => window.noteProv(r)); }, 0);
  function renderProv() {
    const btn = $('prov'), pop = $('provPop');
    if (!btn) return;
    const ids = (VIEW_DATA[curView] || []).filter((id) => PROV[id]);
    if (!ids.length) { btn.hidden = true; pop.classList.remove('open'); return; }
    const rows = ids.map((id) => ({ id, ...PROV[id] })).sort((a, b) => RANK[a.status] - RANK[b.status]);
    let worst = rows[0].status;
    const oldest = rows.reduce((m, r) => (r.at < m ? r.at : m), rows[0].at);
    // delayed quotes fetched more than 30 minutes ago are called stale, not delayed
    const stale = rows.some((r) => r.status === 'delayed' && Date.now() - r.at.getTime() > 30 * 60000);
    if (stale && worst !== 'unavailable') worst = 'stale';
    const sources = Array.from(new Set(rows.map((r) => r.source.replace(/ (quotes|daily bars)$/, ''))));
    btn.hidden = false;
    btn.className = 'prov st-' + worst;
    btn.innerHTML = `<i></i><b>${STATUS[worst] || worst}</b><span>${hhmm(oldest)}</span>`;
    btn.title = `${STATUS[worst] || worst} · ${sources.join(', ')} · click for details`;
    btn.setAttribute('aria-label', `Data status: ${STATUS[worst] || worst}, from ${sources.join(', ')}. Show details`);
    pop.innerHTML = '<h5>Data on this screen</h5>' + rows.map((r) =>
      `<div class="pr"><i class="st-${r.status}"></i><div><b>${NAMES[r.id] || esc(r.id)}</b><small>${esc(r.source)}</small></div>` +
      `<div class="pr-r"><span>${STATUS[r.status] || esc(r.status)}</span>${r.observed ? `<small>data from ${esc(r.observed.slice(0, 10))}</small>` : ''}<small>retrieved ${hhmm(r.at)} · ${age(r.at)}</small></div></div>`).join('') +
      '<p><b>Data from</b> is the session or period the numbers belong to; <b>retrieved</b> is when this site fetched them. ' +
      'Nothing here is a real-time exchange feed: delayed quotes may lag by 15 minutes or more, end-of-day figures come from daily closing bars, ' +
      'news and calendars are shown as published. Information only, not investment advice.</p>';
  }
  function toggleProv(open) {
    const pop = $('provPop'), btn = $('prov');
    const on = open === undefined ? !pop.classList.contains('open') : open;
    pop.classList.toggle('open', on);
    btn.setAttribute('aria-expanded', on ? 'true' : 'false');
    if (on) renderProv();
  }
  if ($('prov')) $('prov').addEventListener('click', (e) => { e.stopPropagation(); toggleProv(); });
  document.addEventListener('click', (e) => { if (!e.target.closest('.prov-wrap')) toggleProv(false); });
  setInterval(() => { if ($('provPop') && $('provPop').classList.contains('open')) renderProv(); }, 30000);

  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { closeSheet(); toggleProv(false); } });
  document.addEventListener('click', (e) => {
    const sh = $('sheet');
    if (sh && sh.classList.contains('open') && !sh.contains(e.target) && !e.target.closest('.tabbar')) closeSheet();
  });

  // Section titles are drawn as styled divs by many modules; give them heading semantics (level 2,
  // under the page's h1) so a screen reader can move through a screen by its sections.
  const headify = (root) => root.querySelectorAll('.sec:not([role]), .b-label:not([role])').forEach((el) => {
    if (el.closest('h1,h2,h3,h4,button,a,summary')) return;
    el.setAttribute('role', 'heading'); el.setAttribute('aria-level', el.classList.contains('b-label') ? '3' : '2');
  });
  const content = $('content');
  if (content) { headify(content); new MutationObserver(() => headify(content)).observe(content, { childList: true, subtree: true }); }

  renderSide();
  renderTabbar();
  if (!route()) mark('home');
  document.addEventListener('langchange', () => { renderSide(); renderTabbar(); mark(curView); });
})();
