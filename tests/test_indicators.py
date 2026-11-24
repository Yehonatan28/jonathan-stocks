"""Every indicator against an independent result: a published worked example or a plain loop
written straight from the definition (no pandas smoothing)."""
import math

import numpy as np
import pandas as pd
import pytest

from quant import indicators as ind


def frame(rows):
    return pd.DataFrame(rows, columns=["High", "Low", "Close"])


# StockCharts' RSI worked example data (Wilder's method). StockCharts rounds the first averages to
# 0.24 and 0.10 before dividing and prints 70.53; unrounded, the definition gives avg gain 0.238571,
# avg loss 0.100000, RS 2.385714 and RSI 70.4641 (worked by hand below), then Wilder's recursion.
SC_CLOSES = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28,
             46.28, 46.00, 46.03]


def loop_rsi(c, n):
    d = [c[i] - c[i - 1] for i in range(1, len(c))]
    g = sum(max(x, 0) for x in d[:n]) / n
    l = sum(max(-x, 0) for x in d[:n]) / n
    out = [None] * len(c)
    out[n] = 100 - 100 / (1 + g / l)
    for i in range(n, len(d)):
        g = (g * (n - 1) + max(d[i], 0)) / n
        l = (l * (n - 1) + max(-d[i], 0)) / n
        out[i + 1] = 100 - 100 / (1 + g / l)
    return out


def test_rsi_matches_the_worked_example():
    r = ind.rsi(pd.Series(SC_CLOSES), 14)
    assert r.iloc[:14].isna().all()
    assert r.iloc[14] == pytest.approx(100 - 100 / (1 + 0.2385714285714 / 0.1), abs=1e-9)   # 70.4641
    want = loop_rsi(SC_CLOSES, 14)
    for i in range(14, len(SC_CLOSES)):
        assert r.iloc[i] == pytest.approx(want[i], rel=1e-12)
    assert round(r.iloc[14], 1) == 70.5            # agrees with the published example to its rounding


def test_sma_and_ema_by_hand():
    x = pd.Series([1.0, 2, 3, 4, 5, 6])
    assert ind.sma(x, 3).tolist()[2:] == [2.0, 3.0, 4.0, 5.0]
    e = ind.ema(x, 3)                                # seed 2.0, alpha 0.5
    assert math.isnan(e.iloc[1]) and e.iloc[2] == 2.0
    assert e.iloc[3] == pytest.approx(3.0) and e.iloc[4] == pytest.approx(4.0) and e.iloc[5] == pytest.approx(5.0)


def loop_atr(h, l, c, n):
    tr = [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))]
    out = [None] * len(c)
    a = sum(tr[:n]) / n
    out[n - 1] = a
    for i in range(n, len(c)):
        a = (a * (n - 1) + tr[i]) / n
        out[i] = a
    return out


def test_atr_against_a_loop_from_the_definition():
    rng = np.random.default_rng(3)
    c = 100 + np.cumsum(rng.normal(0, 1, 60))
    h = c + rng.uniform(0.1, 1.5, 60)
    lo = c - rng.uniform(0.1, 1.5, 60)
    got = ind.atr(pd.DataFrame({"High": h, "Low": lo, "Close": c}), 14)
    want = loop_atr(h, lo, c, 14)
    assert got.iloc[:13].isna().all()
    for i in range(13, 60):
        assert got.iloc[i] == pytest.approx(want[i], rel=1e-12)


def test_macd_is_ema_difference():
    rng = np.random.default_rng(5)
    c = pd.Series(50 + np.cumsum(rng.normal(0, 1, 120)))
    line, sig, hist = ind.macd(c)
    e12, e26 = ind.ema(c, 12), ind.ema(c, 26)
    assert line.iloc[60] == pytest.approx(e12.iloc[60] - e26.iloc[60])
    assert hist.iloc[100] == pytest.approx(line.iloc[100] - sig.iloc[100])
    assert line.iloc[:25].isna().all()


def test_bollinger_uses_population_sd():
    c = pd.Series([2.0, 4, 4, 4, 5, 5, 7, 9])                       # mean 5, population sd 2
    mid, up, lo, pb = ind.bollinger(c, 8, 2)
    assert mid.iloc[-1] == 5 and up.iloc[-1] == 9 and lo.iloc[-1] == 1
    assert pb.iloc[-1] == pytest.approx(1.0)


def test_rsi_edges():
    up = pd.Series(np.arange(1.0, 31.0))
    assert ind.rsi(up).iloc[-1] == 100.0                            # no losses
    flat = pd.Series([10.0] * 30)
    assert ind.rsi(flat).iloc[-1] == 50.0                           # no movement at all


def test_obv_vwap_stochastic_by_hand():
    close = pd.Series([10.0, 11, 10, 10, 12])
    vol = pd.Series([100.0, 200, 150, 120, 300])
    assert ind.obv(close, vol).tolist() == [0, 200, 50, 50, 350]
    df = pd.DataFrame({"High": [11.0, 12], "Low": [9.0, 10], "Close": [10.0, 11], "Volume": [100.0, 300]})
    assert ind.vwap(df).iloc[-1] == pytest.approx((10 * 100 + 11 * 300) / 400)
    s = pd.DataFrame({"High": [5.0, 6, 7, 8, 9, 10], "Low": [1.0, 2, 3, 4, 5, 6], "Close": [3.0, 5, 6, 7, 8, 9]})
    k, d = ind.stochastic(s, k=3, d=2, smooth=1)
    assert k.iloc[2] == pytest.approx(100 * (6 - 1) / (7 - 1))


def test_no_lookahead():
    rng = np.random.default_rng(9)
    c = pd.Series(100 + np.cumsum(rng.normal(0, 1, 200)))
    full = ind.rsi(c)
    cut = ind.rsi(c.iloc[:150])
    assert full.iloc[:150].equals(cut)                             # adding future bars never changes the past
