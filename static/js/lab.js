/* Jonathan Stocks · Strategy Lab (Quant & Risk)
   Build a long-only rule set from entry and exit conditions, stops, targets, a trailing stop and
   costs, run it on one symbol's daily history (/api/lab) and compare with buy-and-hold.
   Fills at the next open; method shown on the page. */
(function () {
  'use strict';
  const root = document.getElementById('v-lab');
  if (!root) return;
  const e = (t) => String(t == null ? '' : t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const n2 = (v, d = 2) => (v == null ? '—' : Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }));
  const pc = (v) => (v == null ? '—' : (v > 0 ? '+' : '') + n2(v) + '%');
  const tone = (v) => (v == null || v === 0 ? '' : v > 0 ? 'up' : 'dn');
  const ENTRY = [['rsi_below', 'RSI(14) below', 'value', 30], ['rsi_above', 'RSI(14) above', 'value', 55],
    ['close_above_ma', 'Close above MA', 'period', 200], ['close_below_ma', 'Close below MA', 'period', 50],
    ['ma_cross_up', '50-day crosses above 200-day', null], ['macd_cross_up', 'MACD crosses above signal', null],
    ['breakout', 'Close above highest high of last', 'period', 20]];
  const EXIT = [['rsi_above', 'RSI(14) above', 'value', 70], ['close_below_ma', 'Close below MA', 'period', 50],
    ['ma_cross_down', '50-day crosses below 200-day', null], ['macd_cross_down', 'MACD crosses below signal', null],
    ['bars_held', 'Held for N bars', 'period', 20]];
  const PRESETS = {
    'Trend pullback': { entry: [['close_above_ma', 200], ['rsi_below', 40]], exit: [['rsi_above', 70]], stop_atr: 2.5, trail_atr: 3 },
    'Breakout': { entry: [['breakout', 55]], exit: [['close_below_ma', 50]], stop_atr: 2 },
    'Golden cross': { entry: [['ma_cross_up']], exit: [['ma_cross_down']] },
    'MACD with trend filter': { entry: [['macd_cross_up'], ['close_above_ma', 200]], exit: [['macd_cross_down']], stop_atr: 3 },
  };
  const condRow = (list, kind) => list.map(([k, label, f, d]) => `<label class="lab-c"><input type="checkbox" data-${kind}="${k}">
      <span>${e(label)}</span>${f ? `<input type="number" step="any" data-${kind}v="${k}" value="${d}" aria-label="${e(label)} value">` : ''}</label>`).join('');

  root.innerHTML = `<div class="wrap labw">
    <div class="ph"><h1>Strategy Lab</h1><p>Test your own entry and exit rules on daily history. Signals on the close, fills at the next open, costs on both sides, no look-ahead.</p></div>
    <form id="labForm" class="mi-card lab-form" autocomplete="off">
      <div class="lab-top"><label>Symbol<input name="ticker" value="SPY" maxlength="15" spellcheck="false"></label>
        <label>Years<select name="years"><option>1</option><option>3</option><option selected>5</option><option>10</option></select></label>
        <label>Preset<select id="labPreset"><option value="">Custom</option>${Object.keys(PRESETS).map((p) => `<option>${e(p)}</option>`).join('')}</select></label></div>
      <div class="lab-cols"><fieldset><legend>Enter when all of these hold</legend>${condRow(ENTRY, 'en')}</fieldset>
        <fieldset><legend>Exit when any of these holds</legend>${condRow(EXIT, 'ex')}</fieldset>
        <fieldset><legend>Risk and costs</legend>
          <label class="lab-n">Stop (× ATR)<input type="number" step="0.1" min="0" name="stop_atr" placeholder="none"></label>
          <label class="lab-n">Target (× ATR)<input type="number" step="0.1" min="0" name="target_atr" placeholder="none"></label>
          <label class="lab-n">Trailing stop (× ATR)<input type="number" step="0.1" min="0" name="trail_atr" placeholder="none"></label>
          <label class="lab-n">Commission (bps per side)<input type="number" step="0.5" min="0" name="commission_bps" value="5"></label>
          <label class="lab-n">Slippage (bps per side)<input type="number" step="0.5" min="0" name="slippage_bps" value="5"></label>
        </fieldset></div>
      <div class="lg-act"><button class="btn btn-gold btn-sm" type="submit">Run backtest</button><span class="auth-err" id="labErr" role="alert"></span></div>
    </form>
    <div id="labOut"></div>
    <details class="rs-defs"><summary>How the backtest works</summary><pre class="lg-pre" id="labMethod"></pre></details>
  </div>`;
  const $b = (id) => document.getElementById(id);
  const form = $b('labForm');
  let charts = [];

  function applyPreset(name) {
    const p = PRESETS[name];
    if (!p) return;
    root.querySelectorAll('[data-en],[data-ex]').forEach((c) => { c.checked = false; });
    const set = (kind, [k, v]) => { const c = root.querySelector(`[data-${kind}="${k}"]`); c.checked = true; const i = root.querySelector(`[data-${kind}v="${k}"]`); if (i && v != null) i.value = v; };
    p.entry.forEach((x) => set('en', x));
    p.exit.forEach((x) => set('ex', x));
    ['stop_atr', 'target_atr', 'trail_atr'].forEach((k) => { form[k].value = p[k] != null ? p[k] : ''; });
  }
  $b('labPreset').addEventListener('change', (ev) => applyPreset(ev.target.value));
  root.addEventListener('change', (ev) => { if (ev.target.matches('[data-en],[data-ex],[data-env],[data-exv]')) $b('labPreset').value = ''; });
  applyPreset('Trend pullback');
  $b('labPreset').value = 'Trend pullback';

  function collect() {
    const pick = (kind, table) => table.filter(([k]) => root.querySelector(`[data-${kind}="${k}"]`).checked).map(([k, , f]) => {
      const o = { type: k };
      if (f) o[f] = Number(root.querySelector(`[data-${kind}v="${k}"]`).value);
      return o;
    });
    const num = (k) => (form[k].value === '' ? null : Number(form[k].value));
    return { ticker: form.ticker.value.trim().toUpperCase(), years: Number(form.years.value),
      strategy: { entry: pick('en', ENTRY), exit: pick('ex', EXIT), stop_atr: num('stop_atr'), target_atr: num('target_atr'),
        trail_atr: num('trail_atr'), commission_bps: num('commission_bps'), slippage_bps: num('slippage_bps') } };
  }

  function render(r) {
    const s = r.stats;
    const tile = (lab, v, sub, cls) => `<div class="mi-tile"><div class="t-lab">${lab}</div><div class="t-val ${cls || ''}">${v}</div><div class="t-sub">${sub || ''}</div></div>`;
    const months = Object.keys(r.monthly);
    const years = Array.from(new Set(months.map((m) => m.slice(0, 4))));
    const heat = (v) => (v == null ? '' : `style="background:color-mix(in srgb, var(${v >= 0 ? '--up' : '--dn'}) ${Math.min(60, Math.abs(v) * 6)}%, transparent)"`);
    $b('labOut').innerHTML = `
      <div class="mi-block"><div class="sec">${e(r.ticker)} · ${e(r.start)} to ${e(r.end)} <span class="tag">${r.bars} BARS</span></div>
      <div class="mi-tiles">
        ${tile('Strategy return', pc(s.total_return), 'buy and hold ' + pc(s.buy_hold_return), tone(s.total_return))}
        ${tile('Annualised', pc(s.cagr), s.cagr == null ? 'needs a year' : '')}
        ${tile('Max drawdown', n2(s.max_drawdown) + '%', 'buy and hold ' + n2(s.buy_hold_max_drawdown) + '%', 'dn')}
        ${tile('Closed trades', String(s.trades) + (r.open_trade ? ' <small>+1 open</small>' : ''), s.win_rate == null ? '' : `${n2(s.win_rate, 1)}% won · avg ${n2(s.avg_bars, 1)} bars`)}
        ${tile('Average win / loss', `${pc(s.avg_win)} / ${pc(s.avg_loss)}`, 'profit factor ' + (s.profit_factor == null ? '—' : n2(s.profit_factor)))}
        ${tile('Time in the market', s.exposure_pct == null ? '—' : n2(s.exposure_pct, 1) + '%', 'Sharpe ' + (s.sharpe == null ? '—' : n2(s.sharpe)))}
      </div></div>
      ${r.open_trade ? `<p class="mi-foot">Still in a trade at the end: entered ${e(r.open_trade.entry_date)} at ${n2(r.open_trade.entry)}, ${pc(r.open_trade.unrealised_pct)} open. It is in the return, not in the trade list.</p>` : ''}
      <div class="mi-block"><div class="sec">Equity and drawdown <span class="tag">INDEXED TO 100</span></div>
        <div class="mi-card rs-chart lab-chart"><canvas id="labEq" role="img" aria-label="Strategy against buy and hold"></canvas></div>
        <div class="mi-card rs-chart lab-dd"><canvas id="labDd" role="img" aria-label="Strategy drawdown"></canvas></div></div>
      <div class="mi-block"><div class="sec">Monthly returns</div><div class="mi-card scr-table"><table class="mi-t lab-heat"><thead><tr><th>Year</th>
        ${['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'].map((m) => `<th class="n">${m}</th>`).join('')}</tr></thead><tbody>
        ${years.map((y) => `<tr><th>${y}</th>${Array.from({ length: 12 }, (_, i) => { const v = r.monthly[`${y}-${String(i + 1).padStart(2, '0')}`]; return `<td class="n" ${heat(v)}>${v == null ? '' : n2(v, 1)}</td>`; }).join('')}</tr>`).join('')}
      </tbody></table></div></div>
      <div class="mi-block"><div class="sec">Trades <span class="tag">${r.trades.length}</span></div><div class="mi-card scr-table">${r.trades.length ? `<table class="mi-t scr-t"><thead><tr>
        <th>Entry</th><th class="n">Price</th><th>Exit</th><th class="n">Price</th><th>Reason</th><th class="n">Bars</th><th class="n">Return</th></tr></thead><tbody>
        ${r.trades.slice().reverse().map((t) => `<tr><td>${e(t.entry_date)}</td><td class="n">${n2(t.entry)}</td><td>${e(t.exit_date)}</td><td class="n">${n2(t.exit)}</td>
        <td>${e(t.reason)}</td><td class="n">${t.bars}</td><td class="n ${tone(t.return_pct)}">${pc(t.return_pct)}</td></tr>`).join('')}</tbody></table>`
        : `<div class="mi-empty">${r.open_trade ? 'No trade closed in this window; one is still open (above).' : 'The rules never entered in this window.'}</div>`}</div></div>`;
    $b('labMethod').textContent = r.method;
    charts.forEach((c) => c.destroy()); charts = [];
    if (typeof Chart === 'undefined') return;
    const css = getComputedStyle(document.documentElement);
    const c = (n, fb) => (css.getPropertyValue(n) || fb).trim();
    const labels = r.curve.map((x) => x.date);
    const axes = (fmt) => ({ x: { ticks: { color: c('--tx3', '#889'), maxTicksLimit: 7 }, grid: { display: false } },
      y: { ticks: { color: c('--tx3', '#889'), callback: fmt }, grid: { color: c('--line', '#222') } } });
    const base = { responsive: true, maintainAspectRatio: false, animation: false, interaction: { mode: 'index', intersect: false },
      plugins: { legend: { labels: { color: c('--tx3', '#889'), boxWidth: 10, font: { size: 11 } } } } };
    charts.push(new Chart($b('labEq'), { type: 'line', data: { labels, datasets: [
      { label: 'Strategy', data: r.curve.map((x) => x.strategy), borderColor: c('--accent', '#5b8def'), pointRadius: 0, borderWidth: 2, tension: 0 },
      { label: 'Buy and hold ' + r.ticker, data: r.curve.map((x) => x.buy_hold), borderColor: c('--tx3', '#889'), borderDash: [4, 3], pointRadius: 0, borderWidth: 1.5, tension: 0 }] },
      options: { ...base, scales: axes((v) => v) } }));
    charts.push(new Chart($b('labDd'), { type: 'line', data: { labels, datasets: [
      { label: 'Drawdown', data: r.curve.map((x) => x.drawdown), borderColor: c('--dn', '#e5566c'), backgroundColor: 'rgba(229,86,108,.15)', fill: true, pointRadius: 0, borderWidth: 1, tension: 0 }] },
      options: { ...base, plugins: { legend: { display: false } }, scales: axes((v) => v + '%') } }));
  }

  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    $b('labErr').textContent = '';
    $b('labOut').innerHTML = '<div class="spinner"></div>';
    try { render(await api('/api/lab', { method: 'POST', body: JSON.stringify(collect()) })); }
    catch (err) { $b('labOut').innerHTML = ''; $b('labErr').textContent = (err && err.error) || 'The backtest could not run.'; }
  });
})();
