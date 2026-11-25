/* Jonathan Stocks · application shell
   Five workspaces, each a group of modules. Desktop: a sidebar. Tablet: an icon rail. Phone: a bottom
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

  const WORKSPACES = [
    { id: 'market', name: 'Market Intelligence', short: 'Markets', modules: [
      { v: 'home', name: 'Market Overview' },
      { v: 'heatmap', name: 'Market Heatmap' } ] },
    { id: 'research', name: 'Equity Research', short: 'Research', modules: [
      { v: 'compare', name: 'Stock Comparison' } ] },
    { id: 'portfolio', name: 'Portfolio', short: 'Portfolio', modules: [
      { v: 'portfolio', name: 'Holdings' },
      { v: 'watchlist', name: 'Watchlist' } ] },
    { id: 'quant', name: 'Quant & Risk', short: 'Quant', modules: [
      { v: 'command', name: 'Risk Engine' },
      { v: 'gaps', name: 'Gap Detection' },
      { v: 'backtest', name: 'Backtesting' },
      { v: 'alerts', name: 'Price Alerts' } ] },
    { id: 'intel', name: 'Intelligence', short: 'Intel', modules: [
      { v: 'news', name: 'Market News' } ] },
  ];
  const byView = {};
  WORKSPACES.forEach((w) => w.modules.forEach((m) => { byView[m.v] = { ws: w, mod: m }; }));
  const $ = (id) => document.getElementById(id);

  function renderSide() {
    const side = $('side');
    if (!side) return;
    side.innerHTML =
      '<a class="side-brand" href="#/home" aria-label="Jonathan Stocks home"><span class="mark">JS</span>' +
      '<div><b>Jonathan Stocks</b><small>Financial intelligence</small></div></a>' +
      WORKSPACES.map((w) => `<nav class="ws" data-ws="${w.id}" aria-label="${w.name}">
        <div class="ws-h" title="${w.name}" data-first="${w.modules[0].v}">${svg(w.id)}<span>${w.name}</span></div>
        ${w.modules.map((m) => `<a href="#/${m.v}" data-v="${m.v}">${m.name}</a>`).join('')}</nav>`).join('') +
      '<div class="side-foot">Market data: delayed or end-of-day unless marked live. Information only, not investment advice.</div>';
    side.querySelectorAll('.ws-h').forEach((h) => h.addEventListener('click', () => { location.hash = '#/' + h.dataset.first; }));
  }

  function renderTabbar() {
    const bar = $('tabbar');
    if (!bar) return;
    bar.innerHTML = WORKSPACES.map((w) => `<button type="button" data-ws="${w.id}" aria-label="${w.name}">${svg(w.id)}<span>${w.short}</span></button>`).join('');
    bar.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => {
      const w = WORKSPACES.find((x) => x.id === b.dataset.ws);
      if (w.modules.length === 1) { closeSheet(); location.hash = '#/' + w.modules[0].v; return; }
      openSheet(w);
    }));
  }

  function openSheet(w) {
    const sh = $('sheet');
    const cur = (location.hash.match(/^#\/([a-z]+)/) || [])[1];
    sh.innerHTML = `<h4>${w.name}</h4>` + w.modules.map((m) => `<a href="#/${m.v}" class="${m.v === cur ? 'on' : ''}">${m.name}</a>`).join('');
    sh.classList.add('open');
    sh.querySelectorAll('a').forEach((a) => a.addEventListener('click', closeSheet));
  }
  function closeSheet() { const sh = $('sheet'); if (sh) sh.classList.remove('open'); }

  function mark(v) {
    const hit = byView[v];
    document.querySelectorAll('.ws a').forEach((a) => a.classList.toggle('on', a.dataset.v === v));
    document.querySelectorAll('.ws').forEach((n) => n.classList.toggle('on', hit && n.dataset.ws === hit.ws.id));
    document.querySelectorAll('.tabbar button').forEach((b) => b.classList.toggle('on', hit && b.dataset.ws === hit.ws.id));
    const c = $('crumbs');
    if (c && hit) c.innerHTML = `<span>${hit.ws.name}</span><i>/</i><b>${hit.mod.name}</b>`;
    if (hit) document.title = `${hit.mod.name} · Jonathan Stocks`;
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
  function route() {
    const v = (location.hash.match(/^#\/([a-z]+)/) || [])[1];
    if (!v || !byView[v]) return false;
    fromHash = true;
    try { window.go(v); } finally { fromHash = false; }
    return true;
  }
  window.addEventListener('hashchange', route);
  window.addEventListener('popstate', route);

  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeSheet(); });
  document.addEventListener('click', (e) => {
    const sh = $('sheet');
    if (sh && sh.classList.contains('open') && !sh.contains(e.target) && !e.target.closest('.tabbar')) closeSheet();
  });

  renderSide();
  renderTabbar();
  if (!route()) mark('home');
})();
