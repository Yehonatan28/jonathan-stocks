/* Jonathan Stocks · display preferences (theme and density), applied before the page paints.
   Loaded in <head> so a light-mode reader never sees a dark flash. Stored only in this browser. */
(function () {
  'use strict';
  const H = document.documentElement;
  const get = (k, d) => { try { return localStorage.getItem(k) || d; } catch (e) { return d; } };
  const put = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* storage blocked: applies until reload */ } };
  const mq = window.matchMedia ? matchMedia('(prefers-color-scheme: light)') : null;
  function apply() {
    const t = get('js.theme', 'dark');
    H.dataset.theme = t === 'system' ? (mq && mq.matches ? 'light' : 'dark') : t;
    H.dataset.density = get('js.density', 'comfortable');
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = H.dataset.theme === 'light' ? '#f6f7f9' : '#0a0d13';
  }
  apply();
  if (mq && mq.addEventListener) mq.addEventListener('change', () => { if (get('js.theme', 'dark') === 'system') { apply(); changed(); } });
  function changed() { document.dispatchEvent(new CustomEvent('themechange')); }

  window.Prefs = {
    get: (k) => get('js.' + k, k === 'theme' ? 'dark' : 'comfortable'),
    set(k, v) { put('js.' + k, v); apply(); changed(); },
  };

  // the Display menu in the top bar
  document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('dispBtn'), pop = document.getElementById('dispPop');
    if (!btn || !pop) return;
    const group = (key, label, opts) => `<fieldset><legend>${label}</legend>${opts.map(([v, l]) =>
      `<label><input type="radio" name="d-${key}" value="${v}" ${window.Prefs.get(key) === v ? 'checked' : ''}> ${l}</label>`).join('')}</fieldset>`;
    const render = () => {
      pop.innerHTML = group('theme', 'Theme', [['dark', 'Dark'], ['light', 'Light'], ['system', 'Match the system']])
        + group('density', 'Density', [['comfortable', 'Comfortable'], ['compact', 'Compact']]);
    };
    const open = (on) => {
      pop.hidden = !on; btn.setAttribute('aria-expanded', String(on));
      if (on) { render(); const f = pop.querySelector('input:checked'); if (f) f.focus(); }
    };
    btn.addEventListener('click', (e) => { e.stopPropagation(); open(pop.hidden); });
    pop.addEventListener('change', (e) => { const i = e.target; if (i.name) window.Prefs.set(i.name.slice(2), i.value); });
    document.addEventListener('click', (e) => { if (!pop.hidden && !e.target.closest('#dispPop')) open(false); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !pop.hidden) { open(false); btn.focus(); } });
    window.addEventListener('hashchange', () => open(false));
  });
})();
