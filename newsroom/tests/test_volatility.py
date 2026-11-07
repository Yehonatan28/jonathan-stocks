import math

from newsroom.processing import volatility as vol


def rows_from_returns(returns, start=100.0):
    closes, c = [start], start
    for r in returns:
        c *= 1 + r / 100
        closes.append(c)
    return [[f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", x] for i, x in enumerate(closes)]


def test_stdev_matches_definition():
    vals = [1.0, -1.0, 2.0, -2.0]
    assert math.isclose(vol.stdev(vals), math.sqrt(10 / 3))


def test_calm_stock_vs_wild_stock():
    calm = rows_from_returns([0.5, -0.5] * 40)          # WMT-like: ~0.5% a day
    wild = rows_from_returns([5.0, -5.0] * 40)          # MSTR-like: ~5% a day
    pc = vol.profile(calm, None, 60, 20, 3.0)
    pw = vol.profile(wild, None, 60, 20, 3.0)
    assert not pc.is_default and not pw.is_default
    # the same 5% move is an event for the calm one and ordinary for the wild one
    assert vol.sigma(5.0, pc) > 5
    assert abs(vol.sigma(5.0, pw)) < 1.2
    assert vol.threshold_pct(pc, 2.0) < vol.threshold_pct(pw, 2.0)


def test_short_history_falls_back_to_default():
    short = rows_from_returns([1.0, -1.0] * 5)          # a fresh IPO, 10 days
    p = vol.profile(short, None, 60, 20, 3.0)
    assert p.is_default and p.stdev_pct == 3.0 and p.days == 10


def test_judged_day_is_excluded_from_its_own_yardstick():
    rows = rows_from_returns([0.5, -0.5] * 40)
    rows.append(["2026-12-31", rows[-1][1] * 1.2])       # +20% day
    with_day = vol.profile(rows, None, 60, 20, 3.0)
    without = vol.profile(rows, "2026-12-31", 60, 20, 3.0)
    assert without.stdev_pct < with_day.stdev_pct


def test_lookback_limits_window():
    rows = rows_from_returns([10.0, -10.0] * 50 + [0.5, -0.5] * 40)
    p = vol.profile(rows, None, 60, 20, 3.0)
    assert p.stdev_pct < 1.0                              # old turbulence is outside the window


def test_flat_series_uses_default():
    rows = [["2026-01-%02d" % (i + 1), 100.0] for i in range(28)]
    assert vol.profile(rows, None, 60, 20, 3.0).is_default
