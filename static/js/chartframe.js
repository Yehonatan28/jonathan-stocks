/* Jonathan Stocks · chart frame
   Every chart says what it shows: the metric, its units, the range, the source and the data time;
   its legend is a row of real buttons (keyboard, screen reader, aria-pressed) that hide and show
   series; and the same numbers are one press away as a table, which is also what a screen reader
   is offered. Used by Research, Compare, Strategy Lab and Transactions. */
(function () {
  'use strict';
  const e = (t) => String(t == null ? '' : t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  /* opts: {id, title, metric, units, range, source, asOf, note, height}
     returns the HTML; the caller then draws into #<id>-c and calls fill(). */
  function html(o) {
    const meta = [o.metric, o.units && 'in ' + o.units, o.range, o.source && 'Source: ' + o.source, o.asOf && 'data to ' + o.asOf].filter(Boolean).join(' · ');
    return `<figure class="cf" id="${o.id}" aria-labelledby="${o.id}-t">
      <div class="cf-head"><div><figcaption class="cf-t" id="${o.id}-t">${e(o.title)}</figcaption><p class="cf-m">${e(meta)}</p></div>
        <div class="cf-views" role="group" aria-label="${e(o.title)}: view">
          <button type="button" class="cf-v" data-view="chart" aria-pressed="true">Chart</button>
          <button type="button" class="cf-v" data-view="table" aria-pressed="false">Table</button></div></div>
      <div class="cf-legend" id="${o.id}-l" role="group" aria-label="Series shown"></div>
      <div class="cf-body" style="height:${o.height || 260}px"><canvas id="${o.id}-c" role="img" aria-label="${e(o.title)}. The same data is available as a table."></canvas></div>
      <div class="cf-table" id="${o.id}-tb" hidden></div>
      ${o.note ? `<p class="cf-note">${e(o.note)}</p>` : ''}</figure>`;
  }

  /* chart: a Chart.js instance; cols: column labels; rows: [{label, values, fmt}] (one per series) */
  function fill(id, chart, cols, rows) {
    const fig = document.getElementById(id);
    if (!fig) return;
    const lg = document.getElementById(id + '-l');
    if (chart && lg) {
      lg.innerHTML = chart.data.datasets.map((ds, i) => `<button type="button" class="cf-key" data-i="${i}" aria-pressed="true">
        <i style="background:${e(ds.borderColor && typeof ds.borderColor === 'string' ? ds.borderColor : ds.backgroundColor)}${ds.borderDash ? ';background:none;border-top:2px dashed ' + e(ds.borderColor) : ''}"></i>${e(ds.label)}</button>`).join('');
      lg.onclick = (ev) => {
        const b = ev.target.closest('.cf-key'); if (!b) return;
        const i = +b.dataset.i, on = chart.isDatasetVisible(i);
        chart.setDatasetVisibility(i, !on); chart.update();
        b.setAttribute('aria-pressed', String(!on));
      };
    }
    const tb = document.getElementById(id + '-tb');
    tb.innerHTML = `<div class="scr-table"><table class="mi-t"><caption class="sr-only">${e(fig.querySelector('.cf-t').textContent)}</caption>
      <thead><tr><th scope="col">Series</th>${cols.map((c) => `<th scope="col" class="n">${e(c)}</th>`).join('')}</tr></thead>
      <tbody>${rows.map((r) => `<tr><th scope="row" class="nm">${e(r.label)}</th>${r.values.map((v) => `<td class="n">${v == null ? '—' : e(r.fmt ? r.fmt(v) : v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
    fig.querySelector('.cf-views').onclick = (ev) => {
      const b = ev.target.closest('.cf-v'); if (!b) return;
      const table = b.dataset.view === 'table';
      fig.querySelectorAll('.cf-v').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
      fig.querySelector('.cf-body').hidden = table;
      if (lg) lg.hidden = table;
      tb.hidden = !table;
    };
  }

  /* Long daily series make a table of hundreds of columns; sample to month ends for the table. */
  function monthly(labels) {
    const idx = [];
    for (let i = 0; i < labels.length; i++) if (i === labels.length - 1 || String(labels[i]).slice(0, 7) !== String(labels[i + 1]).slice(0, 7)) idx.push(i);
    return idx;
  }

  // shared Chart.js look: theme tokens, exact values in the tooltip
  function base(fmt) {
    const css = getComputedStyle(document.documentElement);
    const c = (n, fb) => (css.getPropertyValue(n) || fb).trim();
    const tx = c('--tx3', '#889');
    return { responsive: true, maintainAspectRatio: false, animation: false, interaction: { mode: 'index', intersect: false },
      plugins: { legend: { display: false },
        tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y == null ? '—' : fmt ? fmt(ctx.parsed.y) : ctx.parsed.y}` } } },
      scales: { x: { grid: { display: false }, ticks: { color: tx, maxTicksLimit: 8 } },
        y: { grid: { color: c('--grid', 'rgba(255,255,255,.06)') }, ticks: { color: tx, callback: fmt ? (v) => fmt(v) : undefined } } } };
  }

  window.ChartFrame = { html, fill, monthly, base };
})();
