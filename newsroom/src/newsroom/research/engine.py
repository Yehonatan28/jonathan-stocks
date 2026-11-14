"""🔬 The technical research engine.

For every symbol in the universe it measures what professional US swing/position traders look at,
picks the setup that fits (if any), and computes levels: a trigger, an invalidation level, a first
target, and the reward/risk ratio. Then it scores everything 0-100 and explains the score.

Methods (all public, all classic):
  * Trend template (Mark Minervini, "Trade Like a Stock Market Wizard"): 8 conditions on the
    50/150/200-day averages, the 52-week range and relative strength.
  * Relative strength rating (IBD style): weighted 3/6/9/12-month performance (40/20/20/20),
    ranked against the whole universe, 1-99. Plus the RS line vs. SPY and vs. the sector ETF.
  * Volatility contraction (VCP): successive pullbacks inside the base get shallower, volume dries up.
  * Bollinger squeeze (John Bollinger): band width in the lowest percentile of its 6-month range.
  * Pocket pivot (Gil Morales & Chris Kacher): an up day whose volume beats every down day of the
    prior 10 sessions, near the 10-day / 50-day average.
  * Breakout volume (William O'Neil): the pivot is cleared on volume >= 40% above the 50-day average.
  * Pullback to a rising 21-day EMA / 50-day SMA inside an uptrend, on lighter volume.
  * Short-term oversold in a long-term uptrend (Larry Connors, RSI(2) < 10 above the 200-day).
  * 200-day reclaim / golden cross.
Risk rules: liquidity floor, "too extended to chase" filter, stop distance cap, earnings-event flag.

Information and analysis only. Never a recommendation to buy or sell.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from . import indicators as ta

ETF_SKIP = {"SPY", "QQQ", "DIA", "IWM", "XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU", "XLB", "XLRE", "XLC"}

SETUP_HE = {
    "breakout": "פריצה מבסיס",
    "near_pivot": "מתקרבת לנקודת פריצה",
    "pullback": "נסיגה לממוצע עולה",
    "squeeze": "כיווץ תנודתיות",
    "pocket_pivot": "פוקט פיבוט",
    "oversold_uptrend": "מכירת יתר בתוך מגמה עולה",
    "reclaim_200": "חזרה מעל ממוצע 200",
}


@dataclass
class Analysis:
    symbol: str
    ok: bool
    reason: str = ""
    metrics: dict = field(default_factory=dict)
    setup: str | None = None
    levels: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    score: float = 0.0
    breakdown: dict = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    link: dict = field(default_factory=dict)
    candles: list[list] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["setup_he"] = SETUP_HE.get(self.setup or "", None)
        return d


def _r(x, n=2):
    return None if x is None else round(float(x), n)


# ------------------------------------------------------------------ measure ---

def measure(rows: list[list], spy: list[list] | None = None, sector: list[list] | None = None) -> dict | None:
    """All the numbers for one symbol. rows = [[date, o, h, l, c, v], ...] oldest first."""
    if len(rows) < 60:
        return None
    d = [r[0] for r in rows]
    o = [r[1] for r in rows]
    h = [r[2] for r in rows]
    lo = [r[3] for r in rows]
    c = [r[4] for r in rows]
    v = [float(r[5]) for r in rows]
    n = len(c)
    last = n - 1
    s50, s150, s200 = ta.sma(c, 50), ta.sma(c, 150), ta.sma(c, 200)
    e10, e21 = ta.ema(c, 10), ta.ema(c, 21)
    s5 = ta.sma(c, 5)
    atr14 = ta.atr(h, lo, c, 14)
    rsi14, rsi2 = ta.rsi(c, 14), ta.rsi(c, 2)
    _, _, hist = ta.macd(c)
    bbw = ta.bb_width(c, 20)
    v50 = ta.sma(v, 50)
    w52 = min(n, 252)
    hi52, lo52 = max(h[-w52:]), min(lo[-w52:])

    def at(series, i=last):
        return series[i] if 0 <= i < len(series) else None

    s200_prev = at(s200, last - 21)
    s50_prev = at(s50, last - 10)
    e21_prev = at(e21, last - 5)

    # RS line vs SPY (aligned by date)
    rs_line_high = rs_line_up = None
    rs_vs_spy_63 = None
    if spy:
        sm = {r[0]: r[4] for r in spy}
        pairs = [(c[i], sm[d[i]]) for i in range(n) if d[i] in sm and sm[d[i]]]
        if len(pairs) >= 63:
            line = [a / b for a, b in pairs]
            rs_line_high = line[-1] >= max(line[-min(len(line), 252):]) * 0.995
            rs_line_up = line[-1] > line[-22]
            rs_vs_spy_63 = (line[-1] / line[-64] - 1) * 100
    sector_rs_63 = None
    if sector and len(sector) >= 64:
        sector_rs_63 = ((sector[-1][4] / sector[-64][4]) / (spy[-1][4] / spy[-64][4]) - 1) * 100 if spy and len(spy) >= 64 else None

    # base: the highest high of the last 65 sessions (excluding today) is the pivot
    look = min(65, n - 1)
    window = h[n - 1 - look: n - 1]
    off = max(range(len(window)), key=lambda i: window[i])
    pivot_idx = n - 1 - look + off
    pivot = h[pivot_idx]
    base_len = last - pivot_idx
    base_low = min(lo[pivot_idx: n]) if base_len > 0 else lo[last]
    base_depth = (pivot - base_low) / pivot * 100 if pivot else None
    # contraction: the base split in three; each third's range should shrink
    contractions = []
    if base_len >= 9:
        seg = base_len // 3
        for k in range(3):
            a = pivot_idx + k * seg
            b = pivot_idx + (k + 1) * seg if k < 2 else n
            hh, ll = max(h[a:b]), min(lo[a:b])
            contractions.append((hh - ll) / hh * 100 if hh else 0)
    vcp = len(contractions) == 3 and contractions[0] > contractions[1] > contractions[2] and contractions[2] < 12
    last_third_low = min(lo[pivot_idx + 2 * (base_len // 3): n]) if base_len >= 9 else min(lo[-10:])

    # volume behaviour
    vol_ratio = v[last] / v50[last] if v50[last] else None
    dry_up = (sum(v[-10:]) / 10) / v50[last] if v50[last] else None
    up_vol = sum(v[i] for i in range(n - 50, n) if c[i] > c[i - 1])
    dn_vol = sum(v[i] for i in range(n - 50, n) if c[i] < c[i - 1])
    ud_ratio = up_vol / dn_vol if dn_vol else None

    def pocket_pivot(i: int) -> bool:
        if i < 11 or c[i] <= c[i - 1]:
            return False
        downs = [v[j] for j in range(i - 10, i) if c[j] < c[j - 1]]
        near_ma = any(m and abs(c[i] / m - 1) <= 0.04 for m in (e10[i], s50[i]))
        return bool(downs) and v[i] > max(downs) and near_ma
    pp_recent = any(pocket_pivot(i) for i in (last, last - 1, last - 2))

    bbw_rank = ta.pct_rank(bbw[last], bbw[-126:]) if bbw[last] is not None else None
    rng = [h[i] - lo[i] for i in range(n)]
    nr7 = rng[last] <= min(rng[-7:])
    adv_usd = (sum(c[i] * v[i] for i in range(n - 20, n)) / 20) if n >= 20 else 0

    rets = {k: ta.ret(c, k) for k in (21, 63, 126, 189, 252)}
    rs_raw = None
    if rets[63] is not None:
        parts = [(0.4, rets[63]), (0.2, rets[126]), (0.2, rets[189]), (0.2, rets[252])]
        parts = [(w, r) for w, r in parts if r is not None]
        rs_raw = sum(w * r for w, r in parts) / sum(w for w, _ in parts)

    m = {
        "date": d[last], "close": _r(c[last]), "open": _r(o[last]), "high": _r(h[last]), "low": _r(lo[last]),
        "change_pct": _r((c[last] / c[last - 1] - 1) * 100),
        "sma50": _r(s50[last]), "sma150": _r(at(s150)), "sma200": _r(at(s200)), "ema21": _r(e21[last]),
        "ema10": _r(e10[last]), "sma5": _r(s5[last]),
        "sma200_rising": bool(at(s200) and s200_prev and at(s200) > s200_prev),
        "sma50_rising": bool(s50[last] and s50_prev and s50[last] > s50_prev),
        "ema21_rising": bool(e21[last] and e21_prev and e21[last] > e21_prev),
        "atr": _r(atr14[last]), "atr_pct": _r(atr14[last] / c[last] * 100 if atr14[last] else None),
        "rsi14": _r(rsi14[last], 1), "rsi2": _r(rsi2[last], 1),
        "macd_hist": _r(hist[last], 3), "macd_turn_up": bool(hist[last] is not None and hist[last - 1] is not None
                                                             and hist[last] > hist[last - 1] and hist[last - 1] < 0),
        "high52": _r(hi52), "low52": _r(lo52),
        "from_high52_pct": _r((c[last] / hi52 - 1) * 100), "above_low52_pct": _r((c[last] / lo52 - 1) * 100),
        "pivot": _r(pivot), "base_len": base_len, "base_depth_pct": _r(base_depth),
        "dist_to_pivot_pct": _r((pivot / c[last] - 1) * 100),
        "contractions_pct": [_r(x, 1) for x in contractions], "vcp": vcp, "last_third_low": _r(last_third_low),
        "vol_ratio": _r(vol_ratio), "dry_up": _r(dry_up), "updown_vol": _r(ud_ratio),
        "pocket_pivot": pp_recent, "bbw_rank": _r(bbw_rank, 0), "nr7": nr7,
        "ext_ema21_pct": _r((c[last] / e21[last] - 1) * 100 if e21[last] else None),
        "ext_sma50_pct": _r((c[last] / s50[last] - 1) * 100 if s50[last] else None),
        "ret_1m": _r((rets[21] or 0) * 100), "ret_3m": _r((rets[63] or 0) * 100), "ret_6m": _r((rets[126] or 0) * 100),
        "rs_raw": rs_raw, "rs_line_high": rs_line_high, "rs_line_up": rs_line_up,
        "rs_vs_spy_3m": _r(rs_vs_spy_63), "sector_rs_3m": _r(sector_rs_63),
        "adv_usd_m": _r(adv_usd / 1e6, 1), "rows": n,
        "low_10": _r(min(lo[-10:])), "low_5": _r(min(lo[-5:])), "low_3": _r(min(lo[-3:])),
        "high_10": _r(max(h[-11:-1])), "high_20": _r(max(h[-21:-1])),
        "crossed_200_recent": bool(at(s200) and any(at(s200, i) and c[i] > at(s200, i) and c[i - 1] <= at(s200, i - 1)
                                                    for i in range(last - 4, last + 1) if at(s200, i - 1))),
        "golden_cross_recent": bool(at(s200) and any(s50[i] and at(s200, i) and at(s200, i - 1) and s50[i - 1]
                                                     and s50[i] > at(s200, i) and s50[i - 1] <= at(s200, i - 1)
                                                     for i in range(last - 9, last + 1))),
    }
    return m


def trend_template(m: dict, rs_rating: float | None) -> tuple[int, list[str]]:
    c, s50, s150, s200 = m["close"], m["sma50"], m["sma150"], m["sma200"]
    checks = [
        ("מעל ממוצעי 150 ו-200", bool(s150 and s200 and c > s150 and c > s200)),
        ("ממוצע 150 מעל ממוצע 200", bool(s150 and s200 and s150 > s200)),
        ("ממוצע 200 עולה", m["sma200_rising"]),
        ("ממוצע 50 מעל 150 ו-200", bool(s50 and s150 and s200 and s50 > s150 and s50 > s200)),
        ("מעל ממוצע 50", bool(s50 and c > s50)),
        ("לפחות 30% מעל שפל 52 שבועות", (m["above_low52_pct"] or 0) >= 30),
        ("בטווח 25% משיא 52 שבועות", (m["from_high52_pct"] or -100) >= -25),
        ("חוזק יחסי 70 ומעלה", bool(rs_rating and rs_rating >= 70)),
    ]
    return sum(ok for _, ok in checks), [name for name, ok in checks if ok]


# ------------------------------------------------------------------- setups ---

def pick_setup(m: dict, tt: int, max_ext: float) -> tuple[str | None, dict, list[str]]:
    """The best-fitting setup with its levels, or None. Order = how much pros trust each pattern."""
    c, atr = m["close"], m["atr"] or 0
    tags: list[str] = []
    if m["vcp"]:
        tags.append("VCP")
    if (m["bbw_rank"] or 100) <= 15:
        tags.append("Squeeze")
    if m["pocket_pivot"]:
        tags.append("Pocket pivot")
    if m["nr7"]:
        tags.append("NR7")
    if m["rs_line_high"]:
        tags.append("RS line בשיא")
    if (m["dry_up"] or 9) < 0.8:
        tags.append("ייבוש מחזורים")

    def lv(trigger, stop, target_hint=None):
        stop = min(stop, trigger * 0.995)
        risk = trigger - stop
        if risk <= 0:
            return None
        resistance = m["high52"] if m["high52"] and m["high52"] > trigger * 1.02 else None
        measured = trigger + (m["pivot"] * (m["base_depth_pct"] or 0) / 100 if m["base_depth_pct"] else 2 * risk)
        target = target_hint or resistance or measured
        target = max(target, trigger + 1.5 * risk)
        return {"trigger": _r(trigger), "stop": _r(stop), "target": _r(target),
                "risk_pct": _r(risk / trigger * 100), "rr": _r((target - trigger) / risk, 1),
                "target_2r": _r(trigger + 2 * risk), "target_3r": _r(trigger + 3 * risk)}

    ext = m["ext_ema21_pct"] or 0
    uptrend = tt >= 6
    # 1. breakout from a proper base, confirmed by volume, not yet extended
    if (uptrend and m["base_len"] >= 10 and (m["base_depth_pct"] or 99) <= 35 and c > m["pivot"]
            and c <= m["pivot"] * 1.05 and (m["vol_ratio"] or 0) >= 1.4):
        return "breakout", lv(m["pivot"], max(m["last_third_low"], m["pivot"] - 2 * atr)), tags + ["נפח פריצה"]
    if ext > max_ext:
        return None, {}, tags + ["מתוחה"]
    # 2. tight base just under the pivot (the classic "in the pocket before the breakout")
    if (uptrend and m["base_len"] >= 10 and (m["base_depth_pct"] or 99) <= 35
            and 0 <= (m["dist_to_pivot_pct"] or 99) <= 5 and (m["vcp"] or (m["dry_up"] or 9) < 0.85 or m["nr7"])):
        return "near_pivot", lv(m["pivot"] * 1.001, max(m["last_third_low"], m["pivot"] - 2.5 * atr)), tags
    # 3. pocket pivot inside an uptrend
    if m["pocket_pivot"] and tt >= 5 and m["sma50"] and c > m["sma50"]:
        return "pocket_pivot", lv(m["high"] * 1.001, min(m["low_3"], (m["ema10"] or c) * 0.97)), tags
    # 4. pullback to a rising 21 EMA / 50 SMA on lighter volume
    for ma, name in ((m["ema21"], "ema21"), (m["sma50"], "sma50")):
        rising = m["ema21_rising"] if name == "ema21" else m["sma50_rising"]
        if (uptrend and ma and rising and -1.5 <= (c / ma - 1) * 100 <= 3 and 38 <= (m["rsi14"] or 0) <= 60
                and (m["dry_up"] or 9) < 1.0):
            return "pullback", lv(m["high"] * 1.001, min(m["low_5"], ma * 0.98), m["high_20"]), tags + [f"תמיכה ב-{name.upper()}"]
    # 5. volatility squeeze above a rising 50-day
    if (m["bbw_rank"] or 100) <= 15 and m["sma50"] and c > m["sma50"] and m["sma50_rising"]:
        return "squeeze", lv(m["high_10"] * 1.001, m["low_10"]), tags
    # 6. 200-day reclaim / golden cross with volume
    if (m["crossed_200_recent"] or m["golden_cross_recent"]) and (m["vol_ratio"] or 0) >= 1.2 and m["sma200"]:
        return "reclaim_200", lv(m["high"] * 1.001, m["sma200"] * 0.97), tags
    # 7. short-term washout inside a long-term uptrend (mean reversion)
    if m["sma200"] and c > m["sma200"] and (m["rsi2"] or 100) < 10 and tt >= 5:
        return "oversold_uptrend", lv(m["high"] * 1.001, c - 1.5 * atr, m["ema21"]), tags
    return None, {}, tags


# -------------------------------------------------------------------- score ---

def score(a: Analysis, m: dict, tt: int, rs_rating: float | None, ctx: dict) -> None:
    br: dict[str, float] = {}
    br["trend"] = round(tt / 8 * 25, 1)
    rs = (rs_rating or 50) / 99 * 22 + (3 if m["rs_line_high"] else 0)
    br["rs"] = round(min(rs, 25), 1)
    q = 0.0
    q += 8 if m["vcp"] else 0
    q += 5 if (m["dry_up"] or 9) < 0.8 else 0
    q += 4 if (m["base_depth_pct"] or 99) <= 20 and m["base_len"] >= 10 else 0
    q += 3 if m["pocket_pivot"] else 0
    q += 4 if (m["bbw_rank"] or 100) <= 15 else 0
    q += 2 if m["nr7"] else 0
    q += 5 if a.setup == "breakout" else 0
    q += 2 if (m["updown_vol"] or 0) >= 1.3 else 0
    br["setup"] = round(min(q, 20), 1)
    lv = a.levels
    rr = lv.get("rr") or 0
    risk = lv.get("risk_pct") or 99
    br["risk_reward"] = round(0 if risk > 10 else min(rr / 3, 1) * 12 + (3 if risk <= 6 else 0), 1)
    cx = 0.0
    if (m["sector_rs_3m"] or 0) > 0:
        cx += 5
    if ctx.get("story_score", 0) >= 7:
        cx += 5
    link = a.link
    if link.get("held") or link.get("peer_of") or link.get("same_sector"):
        cx += 3
    if link.get("corr") is not None and link["corr"] < 0.3:
        cx += 2
    br["context"] = round(min(cx, 15), 1)
    total = sum(br.values())
    if "earnings" in ctx:
        total -= 10
    a.breakdown, a.score = br, round(max(0.0, min(100.0, total)), 1)


def reasons_he(a: Analysis, m: dict, tt: int, rs_rating: float | None) -> list[str]:
    r = []
    if tt >= 7:
        r.append(f"עומדת ב-{tt} מתוך 8 תנאי תבנית המגמה")
    if rs_rating and rs_rating >= 80:
        r.append(f"דירוג חוזק יחסי {int(rs_rating)}")
    if m["rs_line_high"]:
        r.append("קו החוזק היחסי מול ה-S&P בשיא")
    if m["vcp"]:
        r.append("כיווץ תנודתיות: " + " ← ".join(f"{x:g}%" for x in m["contractions_pct"]))
    if (m["dry_up"] or 9) < 0.8:
        r.append(f"המחזורים התייבשו ל-{m['dry_up']:g} מהממוצע")
    if a.setup == "breakout" and m["vol_ratio"]:
        r.append(f"פריצה במחזור פי {m['vol_ratio']:g} מהממוצע")
    if m["pocket_pivot"]:
        r.append("פוקט פיבוט ב-3 הימים האחרונים")
    if (m["bbw_rank"] or 100) <= 15:
        r.append("רצועות בולינגר בצמצום חריג")
    if (m["sector_rs_3m"] or 0) > 0:
        r.append("הסקטור חזק מה-S&P ב-3 החודשים האחרונים")
    return r[:5]


# ------------------------------------------------------------------ analyze ---

def analyze_universe(data: dict[str, list[list]], cfg_research: dict, watchlist: list[str],
                     today: date, earnings: dict[str, str] | None = None,
                     story_scores: dict[str, float] | None = None) -> list[Analysis]:
    """data: symbol -> candles (must include SPY and the sector ETFs for relative strength)."""
    earnings, story_scores = earnings or {}, story_scores or {}
    sectors = cfg_research.get("sectors", {})
    peers = cfg_research.get("peers", {})
    max_ext = float(cfg_research.get("max_extension_pct", 8.0))
    warn_days = int(cfg_research.get("earnings_warning_days", 7))
    spy = data.get("SPY")
    measured: dict[str, dict] = {}
    out: list[Analysis] = []
    for sym, rows in data.items():
        m = measure(rows, spy, data.get(sectors.get(sym, ""))) if rows else None
        if m is None:
            out.append(Analysis(sym, False, "אין מספיק היסטוריה"))
            continue
        measured[sym] = m
    raws = sorted(m["rs_raw"] for m in measured.values() if m["rs_raw"] is not None)

    def rating(x):
        if x is None or not raws:
            return None
        return max(1, min(99, round(99 * sum(1 for r in raws if r <= x) / len(raws))))

    # portfolio basket: equal-weight daily returns of the watchlist, for correlation
    def rets(sym, k=60):
        rows = data.get(sym) or []
        return ta.daily_returns([r[4] for r in rows[-(k + 1):]])
    basket_members = [t for t in watchlist if len(data.get(t) or []) > 61]

    def basket_excluding(sym):
        series = [rets(t) for t in basket_members if t != sym]
        series = [s for s in series if len(s) == 60]
        if not series:
            return []
        return [sum(s[i] for s in series) / len(series) for i in range(60)]

    for sym, m in measured.items():
        a = Analysis(sym, True, metrics=m)
        rr = rating(m["rs_raw"])
        m["rs_rating"] = rr
        tt, passed = trend_template(m, rr)
        m["trend_template"] = tt
        m["trend_passed"] = passed
        sec = sectors.get(sym)
        held_same_sector = [t for t in watchlist if t != sym and sectors.get(t) == sec] if sec else []
        corr = ta.corr(rets(sym), basket_excluding(sym)) if len(rets(sym)) == 60 else None
        a.link = {
            "held": sym in watchlist,
            "peer_of": [t for t in watchlist if sym in peers.get(t, [])],
            "same_sector": held_same_sector[:4],
            "sector": sec,
            "corr": _r(corr),
        }
        if sym in ETF_SKIP and sym not in watchlist:
            a.ok, a.reason = False, "תעודת סל מדדית: בסיס להשוואה בלבד"
        elif m["close"] < 5 or (m["adv_usd_m"] or 0) < 20:
            a.ok, a.reason = False, "סחירות נמוכה"
        else:
            a.setup, a.levels, a.tags = pick_setup(m, tt, max_ext)
            if a.setup and not a.levels:
                a.setup = None
        ctx: dict = {"story_score": story_scores.get(sym, 0)}
        e = earnings.get(sym)
        if e:
            days = (date.fromisoformat(e) - today).days
            if 0 <= days <= warn_days:
                ctx["earnings"] = e
                a.flags.append(f"דוח בעוד {days} ימים: סיכון אירוע")
        if corr is not None and corr >= 0.75 and not a.link["held"]:
            a.flags.append("מתואמת מאוד לתיק: תגדיל ריכוזיות")
        if "מתוחה" in a.tags:
            a.flags.append(f"מתוחה {m['ext_ema21_pct']:g}% מעל ממוצע 21")
        score(a, m, tt, rr, ctx)
        if not a.setup:
            a.score = round(a.score * 0.6, 1)          # no actionable structure: ranked, never picked
        a.reasons = reasons_he(a, m, tt, rr)
        a.candles = (data.get(sym) or [])[-90:]
        out.append(a)
    return sorted(out, key=lambda x: -x.score)


def choose(analyses: list[Analysis], n: int, min_score: float, previous: list[str] | None = None,
           max_per_sector: int = 2) -> list[Analysis]:
    """Top setups, at most `max_per_sector` from one sector. Yesterday's picks that still qualify
    get a small continuity edge, so the list does not churn daily (no push to overtrade)."""
    previous = previous or []
    cands = [a for a in analyses if a.ok and a.setup and a.score >= min_score]
    cands.sort(key=lambda a: -(a.score + (3 if a.symbol in previous else 0)))
    out, per = [], {}
    for a in cands:
        s = a.link.get("sector") or a.symbol
        if per.get(s, 0) >= max_per_sector:
            continue
        per[s] = per.get(s, 0) + 1
        out.append(a)
        if len(out) >= n:
            break
    return out
