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
  const unavailable = (box, msg) => { if (box) box.innerHTML = `<div class="mi-empty" role="status">${e(msg || 'Unavailable right now. Nothing is shown in its place.')} <button type="button" class="btn btn-ghost btn-sm mi-retry">Retry</button></div>`; };
  document.addEventListener('click', (ev) => { if (ev.target.closest('#v-home .mi-retry')) { ev.target.closest('.mi-empty').innerHTML = '<div class="spinner"></div>'; load(true); } });

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

  // ---- today in brief: at most three descriptive sentences, each with the numbers behind it
  let brData = null, snapData = null;
  const STATUS = { delayed: 'delayed', eod: 'end of day', reported: 'as filed', live: 'live', unavailable: 'unavailable' };
  const basis = (ids) => ids.map((id) => { const p = window.provOf && window.provOf(id); return p ? `${p.source} · ${STATUS[p.status] || p.status} · retrieved ${p.at.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : ''; }).filter(Boolean).join('; ');
  function insights() {
    const box = el('hInsights');
    if (!box) return;
    const out = [];
    if (brData) {
      const b = brData, tot = b.advancers + b.decliners + b.unchanged, sh = tot ? b.advancers / tot * 100 : null;
      const cw = b.cap_weighted_chg, ew = b.equal_weighted_chg;
      let gap = '';
      if (cw != null && ew != null && Math.abs(cw - ew) >= 0.3) gap = cw > ew ? ' The largest companies did better than the typical member.' : ' The typical member did better than the largest companies.';
      const gapHe = gap ? (cw > ew ? ' לחברות הגדולות היו ביצועים טובים יותר מאשר לחברה הטיפוסית במדד.' : ' לחברה הטיפוסית במדד היו ביצועים טובים יותר מאשר לחברות הגדולות.') : '';
      if (sh != null) out.push({ k: 'Breadth', t: `${b.advancers} of ${tot} S&P 500 members rose today (${num(sh, 0)}%).${gap}`,
        he: `${b.advancers} מתוך ${tot} חברות S&P 500 עלו היום (${num(sh, 0)}%).${gapHe}`,
        bhe: `עולות ${b.advancers}, יורדות ${b.decliners}, ללא שינוי ${b.unchanged}, מתוך ${b.priced} חברות עם מחיר (מתוך ${b.members}). ממוצע משוקלל שווי <span dir="ltr">${pct(cw)}</span>, ממוצע שווה משקל <span dir="ltr">${pct(ew)}</span>.`,
        b: `Advancers ${b.advancers}, decliners ${b.decliners}, unchanged ${b.unchanged}, of ${b.priced} priced members out of ${b.members}. Cap-weighted average move ${pct(cw)}, equal-weighted ${pct(ew)}.`, src: basis(['breadth']) });
    }
    if (secData && secData.sectors && secData.sectors.length) {
      const rows = secData.sectors.filter((r) => r.returns['1D'] != null).sort((a, z) => z.returns['1D'] - a.returns['1D']);
      if (rows.length >= 2) {
        const hi = rows[0], lo = rows[rows.length - 1], sp = secData.benchmark.returns['1D'];
        out.push({ k: 'Sectors', t: `${hi.sector} led the sector funds (${pct(hi.returns['1D'])}); ${lo.sector} trailed (${pct(lo.returns['1D'])}). The S&P 500 fund moved ${pct(sp)}.`,
          bhe: `השינוי היומי במחיר של 11 קרנות הסקטורים של SPDR (הגבוה <span dir="ltr">${hi.etf}</span>, הנמוך <span dir="ltr">${lo.etf}</span>) ושל SPY, עד הסגירה של <span dir="ltr">${e(rows[0].as_of || '')}</span>.`,
          he: `<span dir="ltr">${e(hi.sector)}</span> הוביל את קרנות הסקטורים (<span dir="ltr">${pct(hi.returns['1D'])}</span>); <span dir="ltr">${e(lo.sector)}</span> פיגר (<span dir="ltr">${pct(lo.returns['1D'])}</span>). קרן S&P 500 זזה <span dir="ltr">${pct(sp)}</span>.`,
          b: `One-day price change of the 11 SPDR sector funds (${hi.etf} highest, ${lo.etf} lowest) and SPY, to the close of ${e(rows[0].as_of || 'the last session')}.`, src: basis(['sectors']) });
      }
    }
    const vix = (window.IDXQ || []).find((q) => q.ticker === '^VIX');
    if (vix && vix.price != null && vix.chg != null) {
      out.push({ k: 'Volatility', t: `The VIX ${vix.chg >= 0 ? 'rose' : 'fell'} ${num(Math.abs(vix.chg))}% to ${num(vix.price)}: options on the S&P 500 are pricing ${vix.chg >= 0 ? 'more' : 'less'} movement over the next 30 days than yesterday.`,
        bhe: `מדד התנודתיות של CBOE: <span dir="ltr">${num(vix.price)}</span>, שינוי <span dir="ltr">${pct(vix.chg)}</span> מול הסגירה הקודמת. VIX גבוה יותר פירושו תנודות צפויות גדולות יותר לשני הכיוונים; הוא לא מנבא כיוון.`,
        he: `מדד VIX ${vix.chg >= 0 ? 'עלה' : 'ירד'} ב־${num(Math.abs(vix.chg))}% ל־${num(vix.price)}: האופציות על S&P 500 מתמחרות תנועה ${vix.chg >= 0 ? 'גדולה' : 'קטנה'} יותר ב־30 הימים הבאים לעומת אתמול.`,
        b: `CBOE Volatility Index ${num(vix.price)}, change ${pct(vix.chg)} on the previous close. A higher VIX means larger expected swings in either direction; it is not a forecast of direction.`, src: basis(['quotes']) });
    } else if (snapData) {
      const y = snapData.find((r) => r.kind === 'yield' && r.chg_bp != null);
      if (y) out.push({ k: 'Rates', t: `${y.label} ${y.chg_bp >= 0 ? 'rose' : 'fell'} ${num(Math.abs(y.chg_bp), 1)} bp to ${num(y.price, 3)}%.`,
        b: `${y.label} (${y.symbol}) ${num(y.price, 3)}%, change ${num(y.chg_bp, 1)} basis points on the previous close.`, src: basis(['snapshot']) });
    }
    const he = window.LANG && LANG() === 'he', T = window.T || String;
    if (he) out.forEach((i) => { if (i.he) { i.t = i.he; i.b = i.bhe || i.b; } });
    box.innerHTML = out.length ? out.slice(0, 3).map((i) => `<li class="ins"><span class="ins-k">${T(i.k)}</span><p>${i.t}</p>
        <details><summary>${T('Basis')}</summary><p>${i.b}</p>${i.src ? `<p class="muted">${he ? 'מקור' : 'Source'}: <span dir="ltr">${e(i.src)}</span></p>` : ''}</details></li>`).join('')
      : '<li class="ins"><p class="muted">Not enough of today’s data has arrived to describe the session. The sections below show what is available.</p></li>';
  }

  // ---- loading
  let loadedAt = 0;
  async function load(force) {
    if (!force && Date.now() - loadedAt < 60000) return;
    loadedAt = Date.now();
    const get = (u) => api(u).then((j) => ({ ok: true, j })).catch((j) => ({ ok: false, j }));
    renderSectors();
    const [br, sec, snap] = await Promise.all([get('/api/market/breadth?index=sp500'), get('/api/market/sectors'), get('/api/market/snapshot')]);
    if (br.ok && br.j.ok) { brData = br.j; renderBreadth(br.j); } else { unavailable(el('brTiles')); unavailable(el('leaders')); unavailable(el('laggards')); if (el('pulseSub')) el('pulseSub').textContent = 'Breadth unavailable right now'; }
    if (sec.ok && sec.j.ok) { secData = sec.j; renderSectors(); } else unavailable(el('secTable'));
    if (snap.ok && snap.j.ok) { snapData = snap.j.instruments; renderSnapshot(snap.j.instruments); } else unavailable(el('snapTable'));
    insights();
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
  // ---- your names today (holdings and watchlist)
  const KIND = { stop: 'Stop', earnings: 'Earnings', move: 'Move', volume: 'Volume', range: '52-week', trend: 'Trend' };
  async function digestLoad() {
    const box = el('dgList');
    if (!box) return;
    try {
      const signed = typeof S !== 'undefined' && S.user;
      const body = signed ? {} : { positions: typeof store !== 'undefined' ? await store.getPf() : [], watch: typeof store !== 'undefined' ? await store.getWatch() : [] };
      if (!signed && body.watch) body.watch = body.watch.map((w) => (typeof w === 'string' ? w : w.ticker));
      const d = await api('/api/digest', { method: 'POST', body: JSON.stringify(body) });
      if (!d.symbols) {
        const T = window.T || String;
        box.innerHTML = `<div class="mi-empty h-cta"><p>${T('Follow a few names and this space lists what is notable about them today: large moves, unusual volume, 52-week extremes, a stop nearby, a report this week.')}</p>
          <div class="h-cta-b"><button type="button" class="btn btn-gold btn-sm" onclick="openSearch()">${T('Find a company to follow')}</button>
          <a class="btn btn-ghost btn-sm" href="#/portfolio">${T('Add a holding')}</a></div></div>`;
        el('dgNote').textContent = ''; return;
      }
      el('dgNote').textContent = `${d.symbols} names checked`;
      box.innerHTML = d.items.length ? `<ul class="dg-list">${d.items.map((i) => `<li class="lv-${i.level}" data-t="${e(i.ticker)}" tabindex="0">
          <span class="dg-k">${KIND[i.kind] || ''}</span><b>${e(i.ticker)}</b>${i.held ? '<small>held</small>' : ''}<span class="dg-t">${e(i.text)}</span></li>`).join('')}</ul>`
        : '<div class="mi-empty">Nothing notable in your names today: no large move, unusual volume, 52-week extreme, stop nearby or report this week.</div>';
    } catch (err) { box.innerHTML = '<div class="mi-empty">Unavailable right now.</div>'; }
  }
  document.addEventListener('click', (ev) => { const li = ev.target.closest('.dg-list li[data-t]'); if (li && typeof openChart === 'function') openChart(li.dataset.t); });
  window.MarketIntel = { load, digest: digestLoad, insights };
  // session line: market state from the top bar and the time the quotes were retrieved
  function session() {
    const box = el('hSession'); if (!box) return;
    const st = (el('mktTxt') || {}).textContent || '';
    const q = window.provOf && window.provOf('quotes');
    const he = window.LANG && LANG() === 'he', tm = q ? (window.HM ? HM(q.at) : q.at.toLocaleTimeString()) : '';
    box.textContent = [st, q ? (he ? `מחירים ${q.status === 'delayed' ? 'מושהים' : 'סוף יום'}, נמשכו ב־${tm}` : `quotes ${STATUS[q.status] || q.status}, retrieved ${tm}`) : ''].filter(Boolean).join(' · ');
  }
  document.addEventListener('langchange', () => { insights(); session(); digestLoad(); });
  document.addEventListener('prov', (ev) => { session(); if (['breadth', 'sectors', 'quotes', 'snapshot'].includes(ev.detail)) insights(); });
  setInterval(session, 30000);
  setTimeout(digestLoad, 400);
  if (el('v-home')) load(true);
  setInterval(() => { const v = el('v-home'); if (v && v.classList.contains('on') && !document.hidden) load(true); }, 120000);
})();
