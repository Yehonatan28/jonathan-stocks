"""The technical engine on synthetic textbook charts: each pattern must be recognised for the
right reason, and rejected when it is not there."""
import math
import random
from datetime import date, timedelta

import pytest

from newsroom.research import engine, indicators as ta

START = date(2025, 9, 1)


def candles(closes, vols=None, spread=0.012):
    rows, d = [], START
    for i, c in enumerate(closes):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        prev = closes[i - 1] if i else c
        hi, lo = max(c, prev) * (1 + spread / 2), min(c, prev) * (1 - spread / 2)
        rows.append([d.isoformat(), round(prev, 4), round(hi, 4), round(lo, 4), round(c, 4), int((vols or [1e6] * len(closes))[i])])
        d += timedelta(days=1)
    return rows


def uptrend(n=230, start=50.0, drift=0.0025, seed=1):
    rnd = random.Random(seed)
    out, c = [], start
    for _ in range(n):
        c *= 1 + drift + rnd.gauss(0, 0.008)
        out.append(c)
    return out


def textbook_base(pre, depth_steps=(0.12, 0.07, 0.03), seg=8):
    """After an uptrend: three pullbacks, each shallower (a VCP), ending just under the pivot."""
    top = pre[-1] * 1.02
    out = [top]
    for dep in depth_steps:
        lo = top * (1 - dep)
        half = seg // 2
        out += [top - (top - lo) * (k + 1) / half for k in range(half)]
        out += [lo + (top * 0.985 - lo) * (k + 1) / half for k in range(half)]
    return pre + out


# ------------------------------------------------------------- indicators ---

def test_indicator_basics():
    x = [1, 2, 3, 4, 5, 6]
    assert ta.sma(x, 3)[-1] == 5 and ta.sma(x, 3)[1] is None
    assert ta.rsi(list(range(1, 40)), 14)[-1] == 100.0
    assert ta.rsi(list(range(40, 1, -1)), 14)[-1] < 1
    h, lo, c = [11] * 30, [9] * 30, [10] * 30
    assert abs(ta.atr(h, lo, c, 14)[-1] - 2) < 1e-9
    assert ta.corr([1, 2, 3] * 10, [2, 4, 6] * 10) == pytest.approx(1.0)
    e = ta.ema([1.0] * 30, 10)
    assert e[-1] == pytest.approx(1.0)


def test_bb_width_detects_squeeze():
    wild = [100 + (5 if i % 2 else -5) for i in range(60)]
    calm = [100 + (0.2 if i % 2 else -0.2) for i in range(20)]
    w = ta.bb_width(wild + calm, 20)
    assert w[-1] < w[59] / 10


# ----------------------------------------------------------------- setups ---

def universe(extra):
    spy = candles(uptrend(260, 400, 0.0008, seed=9))
    sectors = {s: candles(uptrend(260, 100, 0.001, seed=k)) for k, s in enumerate(["XLK", "XLY", "XLE"])}
    return {"SPY": spy, **sectors, **extra}


RCFG = {"sectors": {"VCPX": "XLK", "BRKX": "XLK", "DOWN": "XLY", "EXTX": "XLE", "NVDA": "XLK"},
        "peers": {"NVDA": ["VCPX"]}, "max_extension_pct": 8, "earnings_warning_days": 7}


def vols_drying(n, base_from):
    return [2e6 if i < base_from else 2e6 * max(0.35, 1 - (i - base_from) / 30) for i in range(n)]


def test_vcp_base_under_pivot_is_found():
    pre = uptrend(230, seed=3)
    closes = textbook_base(pre)
    data = universe({"VCPX": candles(closes, vols_drying(len(closes), 230)), "NVDA": candles(uptrend(260, seed=4))})
    res = {a.symbol: a for a in engine.analyze_universe(data, RCFG, ["NVDA"], date(2026, 11, 13))}
    a = res["VCPX"]
    m = a.metrics
    assert m["vcp"], m["contractions_pct"]
    assert m["trend_template"] >= 6
    assert a.setup == "near_pivot"
    assert a.levels["trigger"] > m["close"] > a.levels["stop"]
    assert a.levels["rr"] >= 1.5
    assert "VCP" in a.tags
    assert a.link["peer_of"] == ["NVDA"] and a.link["sector"] == "XLK"


def test_breakout_needs_volume():
    pre = uptrend(230, seed=3)
    closes = textbook_base(pre)
    pivot = max(closes[-25:])
    vols = vols_drying(len(closes), 230)
    quiet = closes + [pivot * 1.02]
    loud_vols = vols + [4e6]
    res_loud = {a.symbol: a for a in engine.analyze_universe(universe({"BRKX": candles(quiet, loud_vols)}), RCFG, [], date(2026, 11, 13))}
    res_quiet = {a.symbol: a for a in engine.analyze_universe(universe({"BRKX": candles(quiet, vols + [vols[-1]])}), RCFG, [], date(2026, 11, 13))}
    assert res_loud["BRKX"].setup == "breakout"
    assert res_quiet["BRKX"].setup != "breakout"


def test_downtrend_gets_no_setup_and_low_score():
    closes = uptrend(260, 100, -0.003, seed=5)
    res = {a.symbol: a for a in engine.analyze_universe(universe({"DOWN": candles(closes)}), RCFG, [], date(2026, 11, 13))}
    a = res["DOWN"]
    assert a.metrics["trend_template"] <= 2
    assert a.setup in (None, "oversold_uptrend") and a.score < 40


def test_extended_stock_is_not_chased():
    closes = uptrend(240, seed=6) + [None] * 0
    c = closes[-1]
    closes += [c * (1 + 0.035 * k) for k in range(1, 7)]       # +23% in six days
    res = {a.symbol: a for a in engine.analyze_universe(universe({"EXTX": candles(closes)}), RCFG, [], date(2026, 11, 13))}
    a = res["EXTX"]
    assert a.setup is None
    assert any("מתוחה" in f for f in a.flags)


def test_earnings_flag_and_penalty():
    pre = uptrend(230, seed=3)
    closes = textbook_base(pre)
    data = universe({"VCPX": candles(closes, vols_drying(len(closes), 230))})
    base = {a.symbol: a for a in engine.analyze_universe(data, RCFG, [], date(2026, 11, 13))}["VCPX"]
    flagged = {a.symbol: a for a in engine.analyze_universe(data, RCFG, [], date(2026, 11, 13),
                                                            earnings={"VCPX": "2026-11-17"})}["VCPX"]
    assert any("דוח בעוד 4 ימים" in f for f in flagged.flags)
    assert flagged.score == pytest.approx(base.score - 10, abs=0.2)


def test_rs_rating_orders_the_universe():
    strong = candles(uptrend(260, 50, 0.004, seed=7))
    weak = candles(uptrend(260, 50, -0.001, seed=8))
    res = {a.symbol: a for a in engine.analyze_universe(universe({"NVDA": strong, "DOWN": weak}), RCFG, [], date(2026, 11, 13))}
    assert res["NVDA"].metrics["rs_rating"] > res["DOWN"].metrics["rs_rating"]


def test_index_etfs_are_benchmarks_only():
    res = {a.symbol: a for a in engine.analyze_universe(universe({}), RCFG, [], date(2026, 11, 13))}
    assert not res["SPY"].ok and not res["XLK"].ok


def mk(sym, score, sector, setup="pullback"):
    a = engine.Analysis(sym, True, setup=setup, levels={"rr": 2}, score=score)
    a.link = {"sector": sector}
    return a


def test_choose_caps_sector_and_keeps_continuity():
    pool = [mk("A", 90, "XLK"), mk("B", 88, "XLK"), mk("C", 87, "XLK"), mk("D", 70, "XLE"), mk("E", 50, "XLE")]
    picks = engine.choose(pool, 3, 60)
    assert [p.symbol for p in picks] == ["A", "B", "D"]          # third XLK name skipped
    picks = engine.choose([mk("X", 80, "XLK"), mk("Y", 78, "XLE")], 1, 60, previous=["Y"])
    assert picks[0].symbol == "Y"                                # yesterday's pick keeps its place
    assert engine.choose([mk("Z", 55, "XLK")], 3, 60) == []      # below min_score: nothing forced
