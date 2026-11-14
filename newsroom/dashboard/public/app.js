/* חדר החדשות · dashboard. Vanilla JS + SVG, no libraries. Every string from data goes in as text. */
(() => {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  const $ = (s, r = document) => r.querySelector(s);
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } },
  };

  function el(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === "class") n.className = v;
      else if (k === "text") n.textContent = v;
      else if (k === "style") n.style.cssText = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v);
    }
    for (const c of kids.flat()) if (c != null) n.append(c.nodeType ? c : document.createTextNode(String(c)));
    return n;
  }
  function sv(tag, attrs, ...kids) {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null) continue;
      if (k === "text") n.textContent = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v);
    }
    for (const c of kids.flat()) if (c) n.append(c);
    return n;
  }
  const clear = (n) => { while (n.firstChild) n.removeChild(n.firstChild); return n; };

  // ---------------------------------------------------------------- format --
  const tIL = new Intl.DateTimeFormat("he-IL", { timeZone: "Asia/Jerusalem", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  const dIL = new Intl.DateTimeFormat("he-IL", { timeZone: "Asia/Jerusalem", day: "numeric", month: "numeric" });
  function when(asof) {
    if (asof == null || asof === "") return "—";
    if (typeof asof === "string") { const [y, m, d] = asof.split("-"); return `סגירה ${+d}.${+m}`; }
    const dt = new Date(asof * 1000);
    const today = dIL.format(new Date()) === dIL.format(dt);
    return today ? tIL.format(dt) : `${dIL.format(dt)} ${tIL.format(dt)}`;
  }
  const cls = (x) => (x == null ? "flat" : x > 0.004 ? "up" : x < -0.004 ? "down" : "flat");
  function pctText(x, digits) {
    if (x == null) return "אין נתון";
    const d = digits ?? (Math.abs(x) < 10 ? 2 : 1);
    const v = Math.abs(x).toFixed(d);
    if (+v === 0) return `■ ${(0).toFixed(d)}%`;
    return x > 0 ? `▲ +${v}%` : `▼ −${v}%`;
  }
  const pctNode = (x, digits) => el("span", { class: `num ${cls(x)}`, text: pctText(x, digits) });
  // basis points: Hebrew unit + LTR number, isolated so the arrow, sign and unit never reorder
  const bpNode = (bp, style) => el("span", { class: cls(bp), style: style || "",
    text: `${bp > 0 ? "▲" : bp < 0 ? "▼" : "■"} \u2066${bp > 0 ? "+" : bp < 0 ? "−" : ""}${Math.abs(Math.round(bp))}\u2069 נ"ב` });
  const money = (x) => (x == null ? "—" : x >= 1000 ? `$${Math.round(x).toLocaleString("en-US")}` : `$${x.toFixed(2)}`);
  const ppText = (x) => `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x).toFixed(2)}`;
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  function tint(value, scale) {
    // polarity colour, intensity by |value| / scale, mixed into the neutral tile colour
    const p = Math.round(Math.min(Math.abs(value || 0) / scale, 1) * 100);
    const pole = (value || 0) >= 0 ? "var(--up)" : "var(--down)";
    return `color-mix(in oklab, ${pole} ${Math.max(p, 8)}%, var(--tile))`;
  }
  function source(node, parts) {
    clear(node);
    for (const [label, asof] of parts) if (label) node.append(el("span", { text: `${label} · ${when(asof)}` }));
  }

  let DATA = null;
  let SEL = null;

  // --------------------------------------------------------------- weather --
  const ICONS = {
    sunny: () => [sv("g", { class: "sun-rays" }, ...Array.from({ length: 8 }, (_, i) =>
      sv("line", { x1: 48, y1: 14, x2: 48, y2: 22, stroke: "var(--amber)", "stroke-width": 4, "stroke-linecap": "round", transform: `rotate(${i * 45} 48 44)` }))),
      sv("circle", { cx: 48, cy: 44, r: 16, fill: "var(--amber)" })],
    partly: () => [sv("circle", { cx: 58, cy: 36, r: 14, fill: "var(--amber)" }), cloud(18, 46, 1, "cloud-a")],
    cloudy: () => [cloud(26, 34, 0.8, "cloud-b", "var(--line-2)"), cloud(14, 48, 1, "cloud-a")],
    rain: () => [cloud(14, 36, 1, "cloud-a"), ...[30, 44, 58].map((x, i) =>
      sv("line", { class: "drop", x1: x, y1: 70, x2: x - 4, y2: 80, stroke: "var(--accent)", "stroke-width": 3, "stroke-linecap": "round", style: `animation-delay:${i * 0.35}s` }))],
    storm: () => [cloud(14, 34, 1, "cloud-a", "var(--line-2)"),
      sv("path", { class: "bolt", d: "M50 62 L40 80 L49 80 L44 94 L60 72 L51 72 L56 62 Z", fill: "var(--amber)" })],
    unknown: () => [cloud(14, 40, 1, "cloud-a", "var(--line-2)")],
  };
  function cloud(x, y, s, klass, fill) {
    return sv("path", { class: klass, fill: fill || "var(--ink-2)", transform: `translate(${x} ${y}) scale(${s})`,
      d: "M14 30h40a12 12 0 0 0 0-24 16 16 0 0 0-30-3A11 11 0 0 0 14 30z" });
  }

  function renderWeather(d) {
    const w = d.weather || {};
    const body = clear($("#weather-body"));
    const icon = sv("svg", { class: "w-icon", viewBox: "0 0 96 96", "aria-hidden": "true" }, ...(ICONS[w.key] || ICONS.unknown)());
    const gauge = el("div", { class: "w-gauge", role: "meter", "aria-valuemin": 0, "aria-valuemax": 100, "aria-valuenow": w.score ?? 0, "aria-label": "ציון מזג האוויר" },
      el("i", { style: `left:${w.score ?? 50}%` }));
    body.append(el("div", {},
      el("div", { class: "w-hero" }, icon, el("div", {},
        el("div", { class: "w-score num", text: w.score != null ? Math.round(w.score) : "—" }),
        el("div", { class: "w-label", text: w.label || "" }))),
      gauge,
      el("div", { class: "w-verdict", text: w.verdict || "" })));
    const comp = el("div", { class: "w-comp" });
    for (const c of w.components || []) {
      let v;
      if (c.display == null) v = el("span", { class: "muted", text: "אין נתון" });
      else if (c.pct) v = pctNode(c.display);
      else v = el("span", {}, el("span", { class: "num", text: c.display }),
        c.bp != null ? bpNode(c.bp, "font-size:12.5px;margin-inline-start:8px") : null);
      const sc = c.score;
      comp.append(el("div", { class: "wc", title: `ציון רכיב: ${sc ?? "—"} מתוך 100` },
        el("div", { class: "l", text: c.label }),
        el("div", { class: "v" }, v),
        el("div", { class: "bar" }, el("b", { style: `width:${sc ?? 0}%;background:${sc == null ? "transparent" : tint(sc - 50, 50)}` })),
        el("div", { class: "s", text: c.source ? `${c.source} · ${when(c.asof)}` : "" })));
    }
    body.append(comp);

    const idx = clear($("#indices"));
    for (const r of d.indices || []) {
      const ser = (d.intraday.series || {})[r.symbol] || [];
      idx.append(el("button", { class: "ix", onclick: () => selectSymbol(r.symbol, true) },
        el("div", { class: "n", text: `${r.name} (${r.symbol})` }),
        el("div", { class: "p" }, pctNode(r.change_pct)),
        spark(ser, r.change_pct)));
    }
    source($("#weather-src"), [["ציון מורכב: VIX, S&P 500, רוחב, אג\"ח, דולר, ביטקוין", d.market_updated]]);
  }

  function spark(ser, chg) {
    const s = sv("svg", { viewBox: "0 0 100 30", preserveAspectRatio: "none", "aria-hidden": "true" });
    if (ser.length < 2) return s;
    const ys = ser.map((p) => p[2]);
    const lo = Math.min(0, ...ys), hi = Math.max(0, ...ys), span = hi - lo || 1;
    const X = (i) => (i / (ser.length - 1)) * 100, Y = (v) => 28 - ((v - lo) / span) * 26;
    s.append(sv("line", { x1: 0, x2: 100, y1: Y(0), y2: Y(0), stroke: "var(--line-2)", "stroke-width": 1, "vector-effect": "non-scaling-stroke" }));
    s.append(sv("polyline", { points: ser.map((p, i) => `${X(i)},${Y(p[2])}`).join(" "), fill: "none",
      stroke: `var(--${cls(chg) === "flat" ? "muted" : cls(chg)})`, "stroke-width": 2, "vector-effect": "non-scaling-stroke", "stroke-linejoin": "round" }));
    return s;
  }

  // --------------------------------------------------------------- heatmap --
  function squarify(items, x, y, w, h) {
    const out = [];
    const total = items.reduce((a, b) => a + b.v, 0) || 1;
    let rest = items.map((it) => ({ ...it, a: (it.v / total) * w * h }));
    while (rest.length) {
      const short = Math.min(w, h);
      let row = [rest[0]], best = worst(row, short);
      let i = 1;
      for (; i < rest.length; i++) {
        const cand = row.concat(rest[i]), wr = worst(cand, short);
        if (wr > best) break;
        row = cand; best = wr;
      }
      const sum = row.reduce((a, b) => a + b.a, 0);
      if (w >= h) {
        const cw = sum / h; let cy = y;
        for (const r of row) { const rh = r.a / cw; out.push({ ...r, x, y: cy, w: cw, h: rh }); cy += rh; }
        x += cw; w -= cw;
      } else {
        const ch = sum / w; let cx = x;
        for (const r of row) { const rw = r.a / ch; out.push({ ...r, x: cx, y, w: rw, h: ch }); cx += rw; }
        y += ch; h -= ch;
      }
      rest = rest.slice(row.length);
    }
    return out;
  }
  function worst(row, short) {
    const s = row.reduce((a, b) => a + b.a, 0), mx = Math.max(...row.map((r) => r.a)), mn = Math.min(...row.map((r) => r.a));
    return Math.max((short * short * mx) / (s * s), (s * s) / (short * short * mn));
  }

  function renderHeat(d) {
    const box = clear($("#heat"));
    const rows = (d.watchlist || []).slice().sort((a, b) => Math.abs(b.sigma ?? 0) - Math.abs(a.sigma ?? 0));
    if (!rows.length) { box.append(el("div", { class: "empty", text: "אין עדיין נתונים לרשימה" })); return; }
    const W = box.clientWidth, H = box.clientHeight, GAP = 3;
    const tiles = squarify(rows.map((r) => ({ ...r, v: Math.min(Math.max(Math.abs(r.sigma ?? r.change_pct / 2), 0.35), 4) })), 0, 0, W, H);
    for (const t of tiles) {
      const z = t.sigma ?? t.change_pct / 2;
      const small = t.w < 92 || t.h < 70, tiny = t.w < 70 || t.h < 56, micro = t.w < 44 || t.h < 34;
      const strong = Math.abs(z) >= 1.2;
      const b = el("button", {
        class: `tile${small ? " small" : ""}${tiny ? " tiny" : ""}${micro ? " micro" : ""}${strong ? "" : " light-ink"}`,
        style: `left:${t.x + GAP / 2}px;top:${t.y + GAP / 2}px;width:${t.w - GAP}px;height:${t.h - GAP}px;background:${tint(z, 3)}`,
        "aria-label": `${t.symbol} ${pctText(t.change_pct)}${t.sigma != null ? `, ${Math.abs(t.sigma).toFixed(1)} סטיות תקן` : ""}${t.news ? `, ${t.news} ידיעות` : ""}`,
        onclick: () => selectSymbol(t.symbol, true),
      },
        el("div", {}, el("div", { class: "sym", text: t.symbol }), el("div", { class: "pc num", text: pctText(t.change_pct, tiny ? 1 : undefined) })),
        t.sigma != null ? el("div", { class: "sg num", text: `${Math.abs(t.sigma).toFixed(1)}σ` }) : null,
        t.news ? el("span", { class: "nw", text: `📰 ${t.news}` }) : null);
      box.append(b);
    }
    const tbl = $("#heat-tbl");
    tbl.querySelector("table")?.remove();
    tbl.append(el("table", {}, el("tr", {}, ...["סימול", "שינוי", "סטיות תקן", "תנועה רגילה", "ידיעות"].map((h) => el("th", { text: h }))),
      ...rows.map((r) => el("tr", {}, el("td", { text: r.symbol }), el("td", { class: "n", text: pctText(r.change_pct) }),
        el("td", { class: "n", text: r.sigma != null ? r.sigma.toFixed(2) : "—" }),
        el("td", { class: "n", text: r.stdev != null ? `${r.stdev.toFixed(1)}%` : "—" }), el("td", { class: "n", text: r.news || 0 })))));
    const t0 = rows[0];
    source($("#heat-src"), [[t0?.source || "Finnhub", t0?.asof], ["סף תנודתיות: Tiingo (60 ימי מסחר)", null]]);
  }

  // ----------------------------------------------------------- price chart --
  function chartSymbols(d) {
    const s = d.intraday.series || {};
    return [...(d.indices || []).map((r) => r.symbol), ...(d.watchlist || []).map((r) => r.symbol)].filter((x) => s[x]?.length);
  }
  function selectSymbol(sym, scroll) {
    SEL = sym;
    renderChart(DATA);
    if (scroll) $("#chart").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderChart(d) {
    const syms = chartSymbols(d);
    const row = clear($("#sym-row"));
    const svg = clear($("#price"));
    clear($("#pin-card"));
    if (!syms.length) { svg.append(sv("text", { x: 20, y: 120, fill: "var(--muted)", text: "הגרף יופיע אחרי ההרצה הראשונה בשעות המסחר" })); return; }
    if (!SEL || !syms.includes(SEL)) {
      const moved = (d.watchlist || []).filter((r) => syms.includes(r.symbol)).sort((a, b) => Math.abs(b.sigma ?? 0) - Math.abs(a.sigma ?? 0))[0];
      SEL = moved ? moved.symbol : syms[0];
    }
    for (const s of syms) row.append(el("button", { class: "chip-btn", "aria-pressed": s === SEL ? "true" : "false", text: s, onclick: () => selectSymbol(s) }));

    const ser = d.intraday.series[SEL];
    const W = svg.clientWidth || 600, H = svg.clientHeight || 240, P = { l: 8, r: 46, t: 14, b: 22 };
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    const t0 = ser[0][0], t1 = Math.max(ser[ser.length - 1][0], t0 + 6.5 * 3600);
    const pins = (d.intraday.pins || []).filter((p) => p.symbol === SEL);
    const ys = ser.map((p) => p[2]);
    let lo = Math.min(0, ...ys), hi = Math.max(0, ...ys);
    const pad = (hi - lo) * 0.12 || 0.5; lo -= pad; hi += pad;
    const X = (t) => P.l + ((Math.min(Math.max(t, t0), t1) - t0) / (t1 - t0)) * (W - P.l - P.r);
    const Y = (v) => P.t + (1 - (v - lo) / (hi - lo)) * (H - P.t - P.b);
    // grid: 3 horizontal hairlines with % labels, hourly ticks
    for (const v of niceTicks(lo, hi, 4)) {
      svg.append(sv("line", { x1: P.l, x2: W - P.r, y1: Y(v), y2: Y(v), stroke: v === 0 ? "var(--line-2)" : "var(--line)", "stroke-width": 1 }));
      svg.append(sv("text", { x: W - P.r + 6, y: Y(v) + 4, "font-size": 11, fill: "var(--muted)", text: `${v > 0 ? "+" : ""}${v.toFixed(Math.abs(hi - lo) < 2 ? 1 : 0)}%` }));
    }
    for (let t = Math.ceil(t0 / 3600) * 3600; t <= t1; t += 3600 * 2) {
      svg.append(sv("text", { x: X(t), y: H - 6, "font-size": 11, fill: "var(--muted)", "text-anchor": "middle", text: tIL.format(new Date(t * 1000)) }));
    }
    const last = ser[ser.length - 1][2];
    const col = `var(--${cls(last) === "flat" ? "muted" : cls(last)})`;
    const line = ser.map((p) => `${X(p[0]).toFixed(1)},${Y(p[2]).toFixed(1)}`).join(" L");
    svg.append(sv("path", { d: `M${X(ser[0][0])},${Y(0)} L${line} L${X(ser[ser.length - 1][0])},${Y(0)} Z`, fill: col, opacity: 0.1 }));
    svg.append(sv("path", { d: `M${line}`, fill: "none", stroke: col, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }));
    const lx = X(ser[ser.length - 1][0]), ly = Y(last);
    svg.append(sv("circle", { cx: lx, cy: ly, r: 4.5, fill: col, stroke: "var(--surface)", "stroke-width": 2 }));

    // news pins
    const at = (t) => {
      if (t <= ser[0][0]) return ser[0][2];
      for (let i = 1; i < ser.length; i++) if (ser[i][0] >= t) {
        const a = ser[i - 1], b = ser[i], f = (t - a[0]) / (b[0] - a[0] || 1);
        return a[2] + f * (b[2] - a[2]);
      }
      return ser[ser.length - 1][2];
    };
    pins.sort((a, b) => b.score - a.score).slice(0, 8).forEach((p) => {
      const px = X(p.ts), py = Y(at(p.ts));
      const pc = `var(--${p.sentiment > 0 ? "up" : p.sentiment < 0 ? "down" : "accent"})`;
      const g = sv("g", { tabindex: 0, role: "button", "aria-label": p.title, style: "cursor:pointer",
        onclick: () => showPin(p), onkeydown: (e) => { if (e.key === "Enter") showPin(p); } },
        sv("line", { x1: px, x2: px, y1: P.t, y2: py, stroke: pc, "stroke-width": 1, opacity: 0.5 }),
        sv("circle", { cx: px, cy: P.t + 2, r: 9, fill: "transparent" }),
        sv("circle", { cx: px, cy: P.t + 2, r: 5, fill: pc, stroke: "var(--surface)", "stroke-width": 2 }),
        sv("circle", { cx: px, cy: py, r: 3, fill: pc }));
      svg.append(g);
    });
    if (pins.length) showPin(pins.sort((a, b) => b.score - a.score)[0]);

    // crosshair
    const cross = sv("line", { y1: P.t, y2: H - P.b, stroke: "var(--ink-2)", "stroke-width": 1, opacity: 0 });
    const dot = sv("circle", { r: 4, fill: col, stroke: "var(--surface)", "stroke-width": 2, opacity: 0 });
    svg.append(cross, dot);
    const tip = $("#price-tip");
    const move = (e) => {
      const r = svg.getBoundingClientRect();
      const mx = ((e.clientX - r.left) / r.width) * W;
      let best = ser[0];
      for (const p of ser) if (Math.abs(X(p[0]) - mx) < Math.abs(X(best[0]) - mx)) best = p;
      const x = X(best[0]), y = Y(best[2]);
      cross.setAttribute("x1", x); cross.setAttribute("x2", x); cross.setAttribute("opacity", 0.5);
      dot.setAttribute("cx", x); dot.setAttribute("cy", y); dot.setAttribute("opacity", 1);
      clear(tip).append(el("b", { text: `${SEL} · ${tIL.format(new Date(best[0] * 1000))}` }), el("br"),
        el("span", { class: "num", text: money(best[1]) }), " ", pctNode(best[2]));
      tip.classList.add("on");
      const tx = (x / W) * r.width;
      tip.style.left = `${Math.min(Math.max(tx - 60, 0), r.width - 130)}px`;
      tip.style.top = `${Math.max((y / H) * r.height - 62, 0)}px`;
    };
    svg.onpointermove = move;
    svg.onpointerdown = move;
    svg.onpointerleave = () => { tip.classList.remove("on"); cross.setAttribute("opacity", 0); dot.setAttribute("opacity", 0); };
    const meta = [...(d.watchlist || []), ...(d.indices || [])].find((r) => r.symbol === SEL);
    source($("#chart-src"), [[`מחירים: ${meta?.source || "Finnhub"} (נקודה כל 15 דקות)`, ser[ser.length - 1][0]], ["סיכות: RSS, Finnhub", null]]);
  }

  function showPin(p) {
    const box = clear($("#pin-card"));
    box.append(el("div", { class: "pin-card" },
      el("a", { href: p.url, target: "_blank", rel: "noopener", text: p.title, dir: "ltr", style: "display:block;text-align:left" }),
      el("div", { class: "muted", style: "margin-top:4px;font-size:12px" },
        `${p.source} · ${when(p.ts)} · ציון חשיבות `, el("span", { class: "num", text: p.score.toFixed(1) }))));
  }

  function niceTicks(lo, hi, n) {
    const span = hi - lo, step0 = span / n, mag = Math.pow(10, Math.floor(Math.log10(step0)));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0) || mag * 10;
    const out = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(Math.round(v / step) * step);
    if (!out.some((v) => Math.abs(v) < 1e-9) && lo < 0 && hi > 0) out.push(0);
    return out;
  }

  // ------------------------------------------------------------- waterfall --
  function renderWaterfall(d) {
    const w = d.waterfall, box = clear($("#wf")), mega = clear($("#mega"));
    if (!w) { box.append(el("div", { class: "empty", text: "אין עדיין נתוני סקטורים" })); return; }
    const top = w.items.slice(0, 6), rest = w.items.slice(6);
    const rows = top.map((i) => ({ label: i.label, sym: i.symbol, v: i.contribution, chg: i.change_pct }));
    if (rest.length) rows.push({ label: "שאר הסקטורים", v: rest.reduce((a, b) => a + b.contribution, 0) });
    if (Math.abs(w.residual) >= 0.01) rows.push({ label: "לא מוסבר", v: w.residual, faint: true });
    let cum = 0;
    const segs = rows.map((r) => { const a = cum; cum += r.v; return { ...r, a, b: cum }; });
    const pts = [0, w.total, ...segs.flatMap((s) => [s.a, s.b])];
    const lo = Math.min(...pts), hi = Math.max(...pts), span = hi - lo || 1;
    const P = (v) => ((v - lo) / span) * 100;
    const mk = (r, total) => {
      const a = total ? 0 : r.a, b = total ? w.total : r.b;
      const left = P(Math.min(a, b)), width = Math.max(Math.abs(P(b) - P(a)), 0.8);
      const c = r.faint ? "var(--flat)" : `var(--${r.v >= 0 || (total && w.total >= 0) ? "up" : "down"})`;
      const color = total ? `var(--${w.total >= 0 ? "up" : "down"})` : c;
      return el("div", { class: `wf-row${total ? " total" : ""}`, title: r.chg != null ? `${r.label}: ${pctText(r.chg)} היום` : r.label },
        el("div", { class: "lb", text: r.label }),
        el("div", { class: "wf-track" },
          el("span", { class: "zero", style: `left:${P(0)}%` }),
          el("b", { style: `left:${left}%;width:${width}%;background:${color};opacity:${r.faint ? 0.55 : 1}` })),
        el("div", { class: "vl num", text: `${ppText(total ? w.total : r.v)}${total ? "%" : ""}` }));
    };
    for (const s of segs) box.append(mk(s, false));
    box.append(mk({ label: "S&P 500 (SPY)" }, true));
    if (w.megacaps?.length) {
      mega.append(el("span", { class: "muted", style: "border:0;background:none;padding-inline:0", text: "מניות הדגל:" }));
      for (const m of w.megacaps.slice(0, 6)) mega.append(el("span", {}, `${m.symbol} `, el("b", { class: `num ${cls(m.contribution)}`, text: ppText(m.contribution) })));
    }
    const tbl = $("#wf-tbl");
    tbl.querySelector("table")?.remove();
    tbl.append(el("table", {}, el("tr", {}, ...["סקטור", "משקל", "שינוי", "תרומה (נק' אחוז)"].map((h) => el("th", { text: h }))),
      ...w.items.map((i) => el("tr", {}, el("td", { text: `${i.label} (${i.symbol})` }), el("td", { class: "n", text: `${i.weight}%` }),
        el("td", { class: "n", text: pctText(i.change_pct) }), el("td", { class: "n", text: ppText(i.contribution) })))));
    source($("#wf-src"), [[w.source || "Finnhub", w.asof], [w.note, null]]);
  }

  // ----------------------------------------------------------------- river --
  function renderRiver(d) {
    const svg = clear($("#river-svg")), list = clear($("#river-list"));
    const st = (d.stories || []).filter((s) => s.score >= 4).sort((a, b) => b.score - a.score).slice(0, 7).sort((a, b) => a.first - b.first);
    if (!st.length) { svg.setAttribute("height", 40); svg.append(sv("text", { x: 10, y: 24, fill: "var(--muted)", "font-size": 13, text: "אין עדיין סיפורים היום" })); return; }
    const W = svg.clientWidth || 600, LANE = 44, TOP = 18, H = TOP + st.length * LANE + 24, TICK_W = 76;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("height", H);
    const tMin = Math.min(...st.map((s) => s.first)) - 1800, tMax = Math.max(d.generated, ...st.map((s) => s.last)) + 600;
    const X = (t) => 8 + ((t - tMin) / (tMax - tMin)) * (W - TICK_W - 40);
    for (let t = Math.ceil(tMin / 10800) * 10800; t <= tMax; t += 10800) {
      svg.append(sv("line", { x1: X(t), x2: X(t), y1: TOP - 6, y2: H - 20, stroke: "var(--line)", "stroke-width": 1 }));
      svg.append(sv("text", { x: X(t), y: H - 6, "font-size": 11, fill: "var(--muted)", "text-anchor": "middle", text: tIL.format(new Date(t * 1000)) }));
    }
    // ticker nodes on the right, the "now" side
    const tickers = [...new Set(st.flatMap((s) => (s.tickers.length ? s.tickers : ["שוק"])))].slice(0, 9);
    const tY = (i) => TOP + ((i + 0.5) * (H - TOP - 24)) / tickers.length;
    const wl = Object.fromEntries((d.watchlist || []).map((r) => [r.symbol, r]));
    const xT = W - TICK_W + 10;
    st.forEach((s, i) => {
      const y = TOP + i * LANE + LANE / 2, x0 = X(s.first), xe = Math.max(X(s.last) + 36, x0 + 60), th = 4 + s.score * 1.3;
      const col = `var(--${s.sentiment > 0 ? "up" : s.sentiment < 0 ? "down" : "accent"})`;
      const g = sv("g", { class: "stream", role: "link", tabindex: 0, "aria-label": s.title,
        onclick: () => window.open(s.url, "_blank", "noopener"), onkeydown: (e) => { if (e.key === "Enter") window.open(s.url, "_blank", "noopener"); } });
      g.append(sv("path", { fill: col, opacity: 0.85,
        d: `M${x0},${y} C${x0 + 24},${y} ${x0 + 24},${y - th / 2} ${x0 + 48},${y - th / 2} L${xe},${y - th / 2} L${xe},${y + th / 2} L${x0 + 48},${y + th / 2} C${x0 + 24},${y + th / 2} ${x0 + 24},${y} ${x0},${y} Z` }));
      const targets = s.tickers.length ? s.tickers.filter((t) => tickers.includes(t)) : ["שוק"];
      for (const t of targets) {
        const ty = tY(tickers.indexOf(t));
        g.append(sv("path", { d: `M${xe},${y} C${xe + 40},${y} ${xT - 40},${ty} ${xT - 6},${ty}`, fill: "none", stroke: col,
          "stroke-width": Math.max(1.5, th / targets.length / 1.6), opacity: 0.55, "stroke-linecap": "round" }));
      }
      const room = Math.max(xe - x0, Math.min(280, xT - 90 - x0));
      const maxChars = Math.max(10, Math.floor(room / 6.2));
      const label = s.title.length > maxChars ? s.title.slice(0, maxChars - 1) + "…" : s.title;
      g.append(sv("text", { x: x0 + 2, y: y - th / 2 - 5, "font-size": 11.5, fill: "var(--ink-2)", text: label }));
      g.append(sv("title", { text: `${s.title} · ${s.sources.length} מקורות · ציון ${s.score}` }));
      svg.append(g);
    });
    tickers.forEach((t, i) => {
      const r = wl[t], y = tY(i);
      svg.append(sv("circle", { cx: xT, cy: y, r: 4, fill: r ? `var(--${cls(r.change_pct) === "flat" ? "muted" : cls(r.change_pct)})` : "var(--muted)" }));
      svg.append(sv("text", { x: xT + 9, y: y + 4, "font-size": 12, "font-weight": 600, fill: "var(--ink)", text: t }));
      if (r) svg.append(sv("text", { x: xT + 9, y: y + 17, "font-size": 10.5, fill: "var(--muted)", text: pctText(r.change_pct, 1) }));
    });
    for (const s of st.slice().sort((a, b) => b.score - a.score).slice(0, 4)) {
      list.append(el("a", { href: s.url, target: "_blank", rel: "noopener" },
        el("span", { class: "sc num", text: s.score.toFixed(1) }),
        el("span", { class: "t", dir: "ltr", text: s.title }),
        el("span", { class: "muted", style: "font-size:12px;flex:none", text: `${s.sources.length} מקורות` })));
    }
    source($("#river-src"), [["RSS + Finnhub · ציון חשיבות 1–10", d.generated]]);
  }

  // ----------------------------------------------------------------- chain --
  function renderChains(d) {
    const box = clear($("#chains"));
    if (!(d.chains || []).length) { box.append(el("div", { class: "empty", text: "אין היום שרשרת השפעה בולטת על הרשימה שלך" })); return; }
    for (const c of d.chains) {
      const nodes = [];
      nodes.push(el("div", { class: "node ev" }, el("span", { class: "k", text: `📰 ${c.name}` }),
        c.event ? el("a", { href: c.event.url, target: "_blank", rel: "noopener", dir: "ltr", style: "text-align:left", text: c.event.title })
          : el("span", { class: "muted", text: "תנועת מחיר, בלי ידיעה בולטת" })));
      const step = (label, r) => el("div", { class: "node" }, el("span", { class: "k", text: label }),
        el("span", { class: "v" }, `${r.name} `, r.bp != null ? bpNode(r.bp) : pctNode(r.change_pct)));
      if (c.driver) nodes.push(step("גורם", c.driver));
      if (c.sector) nodes.push(step("סקטור", c.sector));
      nodes.push(el("div", { class: "node" }, el("span", { class: "k", text: "המניות שלי" }),
        el("div", { class: "holds" }, ...c.holdings.map((h) => el("span", {}, `${h.symbol} `, pctNode(h.change_pct, 1))))));
      const row = el("div", { class: "chain" });
      nodes.forEach((n, i) => { if (i) row.append(el("span", { class: "arrow", "aria-hidden": "true" })); row.append(n); });
      box.append(row);
    }
    source($("#chain-src"), [["כללי השרשרת: config/market.yaml · מחירים: Finnhub / Yahoo", d.market_updated]]);
  }

  // ----------------------------------------------------------------- train --
  function renderTrain(d) {
    const box = clear($("#train"));
    const days = d.week?.days || [];
    const done = days.filter((x) => x.past).length + (days.some((x) => x.today) ? 0.5 : 0);
    box.style.setProperty("--done", `${(done / Math.max(days.length, 1)) * 100}%`);
    const ICON = { fomc: "🏛", macro: "📊", earnings: "🧾" };
    for (const day of days) {
      const items = day.events.map((e) => el("li", {},
        el("span", { class: "t num", text: e.time && /\d/.test(e.time) ? e.time : "" }),
        el("span", { text: `${ICON[e.kind] || "•"} ${e.label}${e.kind === "earnings" && e.time && !/\d/.test(e.time) ? ` · ${e.time}` : ""}` }),
        e.mine ? el("span", { class: "tag-mine", text: "ברשימה" }) : null));
      if (day.closed) items.unshift(el("li", {}, el("span", { class: "muted", text: `🚫 הבורסה סגורה${day.holiday ? ` (${day.holiday})` : ""}` })));
      if (day.early) items.unshift(el("li", {}, el("span", { class: "muted", text: `⏱ יום מקוצר, סגירה ב-${day.close_il}` })));
      box.append(el("div", { class: `station${day.past ? " past" : ""}${day.today ? " today" : ""}${day.closed ? " closed" : ""}` },
        el("span", { class: "dot", "aria-hidden": "true" }),
        el("div", { class: "d" }, day.label, day.today ? el("small", { text: "היום" }) : null),
        items.length ? el("ul", {}, items) : el("div", { class: "muted", style: "font-size:12.5px", text: "אין אירועים מרכזיים" })));
    }
    source($("#week-src"), [["FRED (לוח פרסומים) · Finnhub (דוחות) · Federal Reserve", d.market_updated]]);
  }

  // ------------------------------------------------------------------ mags --
  function renderMags(d) {
    const m = d.mags, box = clear($("#mags-body"));
    if (!m) { box.append(el("div", { class: "empty", text: "MAGS לא ברשימה" })); return; }
    const S = 260, C = S / 2, R = 92;
    const svg = sv("svg", { viewBox: `0 0 ${S} ${S}`, role: "img", "aria-label": "חפיפה בין MAGS לרשימה" });
    m.members.forEach((x, i) => {
      const a = (i / m.members.length) * Math.PI * 2 - Math.PI / 2, nx = C + R * Math.cos(a), ny = C + R * Math.sin(a);
      svg.append(sv("line", { x1: C, y1: C, x2: nx, y2: ny, stroke: x.held ? "var(--accent)" : "var(--line-2)", "stroke-width": x.held ? 2 : 1, opacity: x.held ? 0.9 : 0.6 }));
    });
    svg.append(sv("circle", { cx: C, cy: C, r: 38, fill: "var(--surface-2)", stroke: m.etf_held ? "var(--accent)" : "var(--line-2)", "stroke-width": 2 }));
    svg.append(sv("text", { x: C, y: C - 2, "text-anchor": "middle", "font-size": 15, "font-weight": 700, fill: "var(--ink)", text: m.etf }));
    svg.append(sv("text", { x: C, y: C + 15, "text-anchor": "middle", "font-size": 11.5, fill: "var(--ink-2)", text: pctText(m.etf_change_pct, 1) }));
    m.members.forEach((x, i) => {
      const a = (i / m.members.length) * Math.PI * 2 - Math.PI / 2, nx = C + R * Math.cos(a), ny = C + R * Math.sin(a);
      const g = sv("g", {});
      g.append(sv("circle", { cx: nx, cy: ny, r: 25, fill: x.change_pct == null ? "var(--tile)" : tint(x.change_pct, 4),
        stroke: x.held ? "var(--accent)" : "var(--surface)", "stroke-width": x.held ? 3 : 2 }));
      g.append(sv("text", { x: nx, y: ny - 1, "text-anchor": "middle", "font-size": 11.5, "font-weight": 700, fill: "var(--ink)", text: x.symbol }));
      g.append(sv("text", { x: nx, y: ny + 12, "text-anchor": "middle", "font-size": 9.5, fill: "var(--ink)", text: x.change_pct == null ? "" : pctText(x.change_pct, 1) }));
      g.append(sv("title", { text: `${x.symbol}${x.held ? " · גם ישירות ברשימה" : ""}` }));
      svg.append(g);
    });
    const say = el("div", { class: "say" });
    say.append(el("p", {}, el("b", { text: `${m.held_count} מתוך ${m.basket}` }), " מניות MAGS נמצאות גם ישירות ברשימה שלך",
      m.etf_held ? ", ולכן החשיפה אליהן כפולה: דרך המניה ודרך תעודת הסל." : "."));
    if (m.together?.length >= 3) say.append(el("p", {}, `${m.direction === "up" ? "▲ עלו" : "▼ ירדו"} יחד היום: `, el("b", { text: m.together.join(", ") }),
      ". כשהן זזות יחד, התיק מרגיש את זה פעמיים."));
    say.append(el("p", { class: "muted", style: "font-size:12.5px", text: "עיגול עם מסגרת כחולה = מוחזקת גם ישירות. הספירה היא לפי סימולים בלבד, בלי סכומים." }));
    box.append(svg, say);
    source($("#mags-src"), [["הרכב MAGS: config/market.yaml · מחירים: Finnhub", d.market_updated]]);
  }

  // ------------------------------------------------------- alerts / editions --
  function renderAlerts(d) {
    const box = clear($("#alerts"));
    if (!(d.alerts || []).length) { box.append(el("div", { class: "empty", text: "אין התראות אחרונות. שקט זה טוב." })); return; }
    for (const a of d.alerts.slice(0, 6)) {
      box.append(el("div", { class: "al" }, el("div", { class: "h", text: a.headline }),
        el("div", { class: "m", text: a.what }), el("div", { class: "m", text: a.why }),
        el("div", { class: "t" }, when(a.ts), a.url ? " · " : "", a.url ? el("a", { href: a.url, target: "_blank", rel: "noopener", text: "מקור" }) : null)));
    }
  }

  const ED_NAMES = { morning: "☀️ בוקר", preopen: "🔔 לפני הפתיחה", close: "🌆 סגירה", weekly: "📅 שבועי" };
  function safeHTML(html) {
    // Telegram HTML subset only: b, i, u, s, code, a[href^=http]. Everything else becomes text.
    const doc = new DOMParser().parseFromString(`<div>${html}</div>`, "text/html");
    const walk = (node) => {
      const frag = document.createDocumentFragment();
      for (const c of node.childNodes) {
        if (c.nodeType === 3) frag.append(c.textContent);
        else if (c.nodeType === 1) {
          const tag = c.tagName.toLowerCase();
          if (["b", "i", "u", "s", "code"].includes(tag)) { const n = document.createElement(tag); n.append(walk(c)); frag.append(n); }
          else if (tag === "a" && /^https?:\/\//.test(c.getAttribute("href") || "")) {
            const n = el("a", { href: c.getAttribute("href"), target: "_blank", rel: "noopener" }); n.append(walk(c)); frag.append(n);
          } else frag.append(walk(c));
        }
      }
      return frag;
    };
    return walk(doc.body.firstChild);
  }
  function renderEditions(d, pick) {
    const tabs = clear($("#ed-tabs")), box = clear($("#edition"));
    const eds = d.editions || {};
    const names = Object.keys(ED_NAMES).filter((k) => eds[k]);
    if (!names.length) { box.append(el("div", { class: "empty", text: "המהדורה הראשונה תופיע כאן אחרי שתישלח" })); return; }
    const cur = pick && eds[pick] ? pick : names.reduce((a, b) => (eds[b].sent_at > eds[a].sent_at ? b : a));
    for (const n of names) tabs.append(el("button", { class: "chip-btn", "aria-pressed": n === cur ? "true" : "false", text: ED_NAMES[n], onclick: () => renderEditions(d, n) }));
    box.append(safeHTML(eds[cur].html));
  }

  // ------------------------------------------------------------- setup lab --
  const SETUP_COLOR = { breakout: "var(--a-chain)", near_pivot: "var(--a-lab)", pullback: "var(--a-chart)",
    squeeze: "var(--a-river)", pocket_pivot: "var(--a-mags)", oversold_uptrend: "var(--a-weather)", reclaim_200: "var(--a-week)" };
  const fmtN = (x) => (x == null ? "—" : Math.abs(x) >= 1000 ? Math.round(x).toLocaleString("en-US") : (+x).toFixed(2));
  let GID = 0;

  function ring(score) {
    const id = `rg${++GID}`, r = 21, C = 2 * Math.PI * r, v = Math.max(0, Math.min(100, score || 0));
    return sv("svg", { class: "ring", width: 56, height: 56, viewBox: "0 0 56 56", role: "img", "aria-label": `ציון ${v}` },
      sv("defs", {}, sv("linearGradient", { id, x1: 0, y1: 0, x2: 1, y2: 1 },
        sv("stop", { offset: "0%", "stop-color": "var(--a-lab)" }), sv("stop", { offset: "100%", "stop-color": "var(--a-mags)" }))),
      sv("circle", { cx: 28, cy: 28, r, fill: "none", stroke: "var(--line)", "stroke-width": 5 }),
      sv("circle", { cx: 28, cy: 28, r, fill: "none", stroke: `url(#${id})`, "stroke-width": 5, "stroke-linecap": "round",
        "stroke-dasharray": `${(C * v) / 100} ${C}`, transform: "rotate(-90 28 28)" }),
      sv("text", { x: 28, y: 33, "text-anchor": "middle", "font-size": 15, "font-weight": 800, fill: "var(--ink)", "font-family": "Rubik, Heebo, sans-serif", text: Math.round(v) }));
  }

  function maLine(closes, n, kind) {
    const out = new Array(closes.length).fill(null);
    if (closes.length < n) return out;
    if (kind === "sma") { let s = 0; closes.forEach((c, i) => { s += c; if (i >= n) s -= closes[i - n]; if (i >= n - 1) out[i] = s / n; }); return out; }
    const k = 2 / (n + 1); let e = closes.slice(0, n).reduce((a, b) => a + b, 0) / n; out[n - 1] = e;
    for (let i = n; i < closes.length; i++) { e = closes[i] * k + e * (1 - k); out[i] = e; }
    return out;
  }

  function candleChart(c, lv, color) {
    const svg = sv("svg", { class: "candles", role: "img", "aria-label": "גרף נרות יומי עם רמות" });
    if (!c || c.length < 10) return svg;
    requestAnimationFrame(() => drawCandles(svg, c, lv, color));
    return svg;
  }
  function drawCandles(svg, c, lv, color) {
    const W = svg.clientWidth || 340, H = svg.clientHeight || 190, VOL = 28, PR = Math.round(W * 0.2), PL = 4, PT = 8;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    const lows = c.map((r) => r[3]), highs = c.map((r) => r[2]);
    let lo = Math.min(...lows, lv.stop ?? Infinity), hi = Math.max(...highs, lv.target ?? -Infinity);
    const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
    const plotW = W - PL - PR, step = plotW / c.length, bw = Math.max(1.5, step * 0.62);
    const X = (i) => PL + i * step + step / 2, Y = (v) => PT + (1 - (v - lo) / (hi - lo)) * (H - PT - VOL - 6);
    const vmax = Math.max(...c.map((r) => r[5])) || 1;
    // future zone: risk (trigger -> stop) and reward (trigger -> target), like a position tool
    const fx = W - PR + 6, fw = PR - 10;
    if (lv.trigger && lv.stop) svg.append(sv("rect", { x: fx, y: Y(lv.trigger), width: fw, height: Math.max(1, Y(lv.stop) - Y(lv.trigger)), fill: "var(--down)", opacity: 0.16, rx: 3 }));
    if (lv.trigger && lv.target) svg.append(sv("rect", { x: fx, y: Y(lv.target), width: fw, height: Math.max(1, Y(lv.trigger) - Y(lv.target)), fill: "var(--up)", opacity: 0.16, rx: 3 }));
    // volume
    c.forEach((r, i) => {
      const h = (r[5] / vmax) * VOL;
      svg.append(sv("rect", { x: X(i) - bw / 2, y: H - h, width: bw, height: h, fill: r[4] >= r[1] ? "var(--up)" : "var(--down)", opacity: 0.28 }));
    });
    // moving averages
    const closes = c.map((r) => r[4]);
    for (const [ma, col] of [[maLine(closes, 21, "ema"), "var(--a-weather)"], [maLine(closes, 50, "sma"), "var(--a-river)"]]) {
      const pts = ma.map((v, i) => (v == null ? null : `${X(i).toFixed(1)},${Y(v).toFixed(1)}`)).filter(Boolean);
      if (pts.length > 1) svg.append(sv("polyline", { points: pts.join(" "), fill: "none", stroke: col, "stroke-width": 1.6, opacity: 0.9 }));
    }
    // candles
    c.forEach((r, i) => {
      const up = r[4] >= r[1], col = up ? "var(--up)" : "var(--down)";
      svg.append(sv("line", { x1: X(i), x2: X(i), y1: Y(r[2]), y2: Y(r[3]), stroke: col, "stroke-width": 1 }));
      const y1 = Y(Math.max(r[1], r[4])), y2 = Y(Math.min(r[1], r[4]));
      svg.append(sv("rect", { x: X(i) - bw / 2, y: y1, width: bw, height: Math.max(1, y2 - y1), fill: col, rx: 1 }));
    });
    // levels
    const level = (v, col, label) => {
      if (v == null) return;
      svg.append(sv("line", { x1: PL, x2: W - 4, y1: Y(v), y2: Y(v), stroke: col, "stroke-width": 1.4, opacity: 0.9 }));
      svg.append(sv("text", { x: W - 6, y: Y(v) - 4, "text-anchor": "end", "font-size": 10.5, "font-weight": 700, fill: col, text: `${label} ${fmtN(v)}` }));
    };
    level(lv.target, "var(--up)", "יעד");
    level(lv.trigger, "var(--a-chart)", "טריגר");
    level(lv.stop, "var(--down)", "ביטול");
    svg.append(sv("text", { x: PL + 2, y: H - VOL - 2, "font-size": 10, fill: "var(--muted)", text: "EMA21 (כתום) · SMA50 (תכלת)" }));
  }

  function linkLine(l) {
    const parts = [];
    if (l.held) parts.push("כבר ברשימה שלך");
    if (l.peer_of?.length) parts.push(`מתחרה/דומה ל-${l.peer_of.join(", ")}`);
    else if (l.same_sector?.length) parts.push(`אותו סקטור כמו ${l.same_sector.slice(0, 3).join(", ")}`);
    if (l.corr != null) parts.push(`מתאם לתיק \u2066${l.corr.toFixed(2)}\u2069${l.corr < 0.3 ? " (מפזר)" : l.corr > 0.75 ? " (חופף)" : ""}`);
    return parts.join(" · ");
  }

  function renderLab(d) {
    const res = d.research, box = clear($("#lab-picks")), more = clear($("#lab-more"));
    if (!res) { box.append(el("div", { class: "empty", text: "המחקר הראשון ירוץ הערב אחרי הסגירה בניו יורק" })); return; }
    $("#lab-meta").textContent = `נסרקו ${res.analyzed} מניות · מסחר ${res.session.split("-").reverse().slice(0, 2).join(".")}`;
    if (!res.picks.length) box.append(el("div", { class: "empty", text: "אין היום סטאפ שעובר את רף האיכות. גם זו תשובה: לא כל יום צריך לעשות משהו." }));
    res.picks.forEach((p, i) => {
      const color = SETUP_COLOR[p.setup] || "var(--a-lab)", lv = p.levels || {}, m = p.metrics || {};
      const bd = p.breakdown || {};
      const card = el("article", { class: "pick", style: `--pc:${color}` },
        el("div", { class: "pick-h" }, el("span", { class: "rank", text: i + 1 }),
          el("div", {}, el("div", { class: "sym", text: p.symbol }),
            el("div", { class: "px" }, el("span", { class: "num", text: money(m.close) }), " ", pctNode(m.change_pct),
              m.rs_rating ? el("span", { text: ` · RS ${m.rs_rating}` }) : null)),
          ring(p.score)),
        el("div", { class: "chips" }, el("span", { class: "chip setup", text: p.setup_he }),
          p.status === "חדש" ? el("span", { class: "chip new", text: "חדש היום" }) : el("span", { class: "chip", text: "ממשיך מאתמול" }),
          ...p.tags.slice(0, 4).map((t) => el("span", { class: "chip", text: t })),
          ...p.flags.map((f) => el("span", { class: "chip warn", text: `⚠ ${f}` }))),
        candleChart(p.candles, lv, color),
        el("div", { class: "levels" },
          el("div", { class: "trig" }, el("span", { class: "k", text: "טריגר" }), el("span", { class: "v num", text: fmtN(lv.trigger) })),
          el("div", { class: "stop" }, el("span", { class: "k", text: "ביטול" }), el("span", { class: "v num", text: fmtN(lv.stop) })),
          el("div", { class: "tgt" }, el("span", { class: "k", text: "יעד ראשון" }), el("span", { class: "v num", text: fmtN(lv.target) })),
          el("div", {}, el("span", { class: "k", text: "סיכוי/סיכון" }), el("span", { class: "v num", text: lv.rr != null ? `${lv.rr}:1` : "—" }))),
        el("div", { class: "thesis", text: p.thesis || "" }),
        el("div", { class: "cv" }, el("div", {}, el("b", { text: "✓ מה יאשר: " }), p.confirm || ""),
          el("div", {}, el("b", { text: "✕ מה יבטל: " }), p.invalidate || "")),
        el("div", { class: "linkline", text: `🔗 ${linkLine(p.link || {})}` }),
        el("div", { class: "bd" }, ...[["מגמה", bd.trend, 25], ["חוזק יחסי", bd.rs, 25], ["מבנה", bd.setup, 20], ["סיכוי/סיכון", bd.risk_reward, 15], ["הקשר", bd.context, 15]]
          .map(([k, v, max]) => el("div", { title: `${k}: ${v ?? 0} מתוך ${max}` }, el("i", {}, el("b", { style: `width:${((v || 0) / max) * 100}%` })), k))));
      box.append(card);
    });
    if (res.shortlist?.length) {
      more.append(el("div", { class: "sub-h", text: "ברשימה המורחבת" }),
        el("div", { class: "lab-row" }, ...res.shortlist.map((x) => el("div", { class: "mini" },
          el("b", { text: x.symbol }), ` · ${x.setup_he || ""} · `, el("span", { class: "num", text: Math.round(x.score) })))));
    }
    if (res.holdings?.length) {
      more.append(el("div", { class: "sub-h", text: "המניות שלך, בעין טכנית" }),
        el("div", { class: "holdings" }, ...res.holdings.map((h) => {
          const m = h.metrics || {}, tt = m.trend_template || 0;
          return el("div", { class: "hold" }, el("span", { class: "s", text: h.symbol }),
            el("div", {}, el("div", { class: "dots", title: `תבנית מגמה: ${tt} מתוך 8` }, ...Array.from({ length: 8 }, (_, k) => el("i", { class: k < tt ? "on" : "" }))),
              el("span", { class: "muted" }, `RS ${m.rs_rating ?? "—"}`,
                m.ext_ema21_pct != null ? ` · ${m.ext_ema21_pct >= 0 ? "מעל" : "מתחת ל"}-EMA21 ב-` : "",
                m.ext_ema21_pct != null ? el("span", { class: "num", text: `${Math.abs(m.ext_ema21_pct)}%` }) : null)),
            h.setup ? el("span", { class: "chip setup", style: `--pc:${SETUP_COLOR[h.setup] || "var(--a-lab)"}`, text: h.setup_he }) : el("span", { class: "muted", text: "אין סטאפ" }));
        })));
    }
    const t = res.track || {};
    more.append(el("div", { class: "sub-h", text: "מעקב ביצועים של המעבדה (כנות לפני הכול)" }),
      el("div", { class: "track-strip" },
        ...[["סטאפים שסומנו", t.picks], ["הטריגר הופעל", t.triggered], ["נסגרו", t.closed],
            ["אחוז הצלחה", t.win_rate != null ? `${t.win_rate}%` : "—"], ["ממוצע R", t.avg_r != null ? t.avg_r : "—"]]
          .map(([k, v]) => el("div", {}, el("span", { class: "k", text: k }), el("span", { class: "v num", text: v ?? 0 })))),
      t.closed ? null : el("div", { class: "muted", style: "font-size:12px;margin-top:6px", text: "המעקב מתחיל לצבור נתונים. כל סטאפ נבדק יום אחרי יום: הגיע ליעד, נעצר, או פג תוקף." }));
  }

  function renderTicker(d) {
    const wrap = $("#ticker"), track = clear($("#ticker-track"));
    const items = (d.headlines || []).slice(0, 10);
    wrap.hidden = !items.length;
    const mk = (h) => el("a", { href: h.url, target: "_blank", rel: "noopener" }, el("b", { text: h.score.toFixed(1) }), h.title);
    for (const round of [0, 1]) for (const h of items) { const a = mk(h); if (round) a.setAttribute("aria-hidden", "true"); track.append(a); }
  }

  // ------------------------------------------------------------------ boot --
  function renderAll(d) {
    DATA = d;
    $("#sub").textContent = `${d.today_label} · עודכן ${when(d.generated)}`;
    const live = $("#live");
    live.classList.toggle("on", !!d.market_open);
    live.lastChild.textContent = d.market_open ? "השוק פתוח" : "השוק סגור";
    const ban = $("#banner");
    const notes = [];
    if (d.demo) notes.push("נתוני הדגמה: כל המספרים בעמוד הזה מומצאים, לצורך בדיקת העיצוב בלבד.");
    if (d.offline) notes.push(`אין חיבור. מוצגים הנתונים האחרונים שנשמרו (${when(d.generated)}).`);
    if ((d.failed_sources || []).length) notes.push(`מקורות שלא ענו בהרצה האחרונה: ${d.failed_sources.join(", ")}`);
    ban.hidden = !notes.length;
    ban.firstElementChild.textContent = notes.join(" · ");
    const m = /t=([A-Z0-9.^=\-]+)/.exec(location.hash);
    if (m) SEL = m[1];
    const parts = [renderTicker, renderWeather, renderLab, renderHeat, renderChart, renderWaterfall, renderRiver, renderChains, renderTrain, renderMags, renderAlerts, (x) => renderEditions(x)];
    for (const f of parts) { try { f(d); } catch (e) { console.error(f.name, e); } }
    $("#foot-src").textContent = `מקורות: Finnhub, Tiingo, FRED, SEC EDGAR, Federal Reserve, CoinGecko, RSS${d.weather?.components?.some((c) => (c.source || "").startsWith("Yahoo")) ? ", Yahoo (גיבוי)" : ""} · עודכן ${when(d.generated)}`;
  }

  async function load() {
    try {
      const r = await fetch(`data.json?ts=${Date.now()}`, { cache: "no-store" });
      if (!r.ok) throw new Error(r.status);
      renderAll(await r.json());
    } catch (e) {
      try {
        const c = await caches.match("data.json", { ignoreSearch: true });
        if (c) { const d = await c.json(); d.offline = true; renderAll(d); return; }
      } catch (e2) { /* no cache */ }
      $("#sub").textContent = "לא הצלחתי לטעון נתונים";
    }
  }

  // theme / colour-blind toggles
  const root = document.documentElement;
  $("#theme").addEventListener("click", () => {
    root.dataset.theme = root.dataset.theme === "light" ? "dark" : "light";
    store.set("nr-theme", root.dataset.theme);
    document.querySelector('meta[name="theme-color"]').content = root.dataset.theme === "light" ? "#fbf7f2" : "#080b1a";
    if (DATA) renderAll(DATA);
  });
  const cvdBtn = $("#cvd");
  const syncCvd = () => cvdBtn.setAttribute("aria-pressed", root.dataset.cvd === "on" ? "true" : "false");
  syncCvd();
  cvdBtn.addEventListener("click", () => {
    root.dataset.cvd = root.dataset.cvd === "on" ? "off" : "on";
    store.set("nr-cvd", root.dataset.cvd); syncCvd();
    if (DATA) renderAll(DATA);
  });
  // nav highlight
  const links = [...document.querySelectorAll(".nav a")];
  const io = new IntersectionObserver((es) => es.forEach((e) => {
    if (e.isIntersecting) links.forEach((a) => a.classList.toggle("on", a.getAttribute("href") === `#${e.target.id}`));
  }), { rootMargin: "-40% 0px -55% 0px" });
  document.querySelectorAll("main > section").forEach((s) => io.observe(s));
  // redraw on resize (charts are sized to their containers)
  let rz;
  window.addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(() => DATA && renderAll(DATA), 150); });
  window.addEventListener("hashchange", () => DATA && renderAll(DATA));
  document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });
  setInterval(() => { if (!document.hidden) load(); }, 5 * 60 * 1000);
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
  load();
})();
