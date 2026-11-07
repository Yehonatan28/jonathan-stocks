"""Pre-open, close and weekly: timing and content."""
from datetime import date, datetime

import pytest

from newsroom import scheduler as sch
from newsroom.config import Config
from newsroom.editions import close, preopen, weekly
from newsroom.models import Quote
from newsroom.processing.volatility import VolProfile
from newsroom.snapshot import Snapshot
from newsroom.storage.state import State

PRE = {"minutes_before_open": 30, "window_minutes": 45}
CLO = {"minutes_after_close": 15, "window_minutes": 150}
WEEK = {"weekday": "sun", "time": "08:00", "latest": "14:00"}


def ny(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=sch.NY)


@pytest.mark.parametrize("when,due", [
    (ny(2026, 11, 10, 8, 56), False),
    (ny(2026, 11, 10, 8, 58), True),        # 09:00 ET target, 3 minutes early allowed
    (ny(2026, 11, 10, 9, 40), True),        # a late cron still catches it
    (ny(2026, 11, 10, 9, 50), False),
    (ny(2026, 11, 26, 9, 0), False),        # Thanksgiving: no session
    (ny(2026, 11, 14, 9, 0), False),        # Saturday
])
def test_preopen_due(when, due):
    assert sch.preopen_due(when, PRE, None) is due


def test_preopen_in_israel_time_follows_dst_gap():
    # 16 March 2026: US already on DST, Israel not -> 09:00 ET is 15:00 in Israel
    t = datetime(2026, 3, 16, 15, 0, tzinfo=sch.IL)
    assert sch.preopen_due(t, PRE, None)
    assert not sch.preopen_due(datetime(2026, 3, 16, 16, 0, tzinfo=sch.IL), PRE, None)


def test_close_due_and_early_close():
    assert not sch.close_due(ny(2026, 11, 10, 16, 10), CLO, None)
    assert sch.close_due(ny(2026, 11, 10, 16, 15), CLO, None)
    assert not sch.close_due(ny(2026, 11, 10, 16, 15), CLO, "2026-11-10")
    assert sch.close_due(ny(2026, 11, 27, 13, 20), CLO, None)     # day after Thanksgiving closes 13:00


def test_weekly_due():
    assert sch.weekly_due(datetime(2026, 11, 8, 8, 0, tzinfo=sch.IL), WEEK, None)
    assert not sch.weekly_due(datetime(2026, 11, 8, 8, 0, tzinfo=sch.IL), WEEK, "2026-11-08")
    assert not sch.weekly_due(datetime(2026, 11, 9, 8, 0, tzinfo=sch.IL), WEEK, None)


def test_week_bounds_with_monday_holiday():
    # week of 19.1.2027: Monday is MLK day -> previous week ended Friday 15.1
    assert sch.week_bounds(date(2027, 1, 22)) == (date(2027, 1, 15), date(2027, 1, 22))
    assert sch.week_bounds(date(2026, 11, 13)) == (date(2026, 11, 6), date(2026, 11, 13))


def test_weekly_change_and_sigma():
    rows = [[f"2026-10-{d:02d}", 100.0 + (d % 2) * 0.5] for d in range(1, 31)]
    rows += [["2026-11-06", 100.0], ["2026-11-09", 101.0], ["2026-11-13", 104.0]]
    assert weekly.weekly_change(rows, date(2026, 11, 6), date(2026, 11, 13)) == 4.0
    assert weekly.close_on(rows, date(2026, 11, 11)) == 101.0
    cfg = Config.load()
    assert weekly.weekly_sigma(rows, 4.0, date(2026, 11, 6), cfg) > 1


def test_premarket_only_prints_before_open():
    cfg = Config.load()
    cfg.watchlist = ["NVDA", "WMT", "AAPL"]
    s = Snapshot(date(2026, 11, 10), date(2026, 11, 10), date(2026, 11, 9))
    early = int(ny(2026, 11, 10, 8, 45).timestamp())
    s.quotes["NVDA"] = Quote("NVDA", 100, -3.0, 103, early, "Finnhub")
    s.quotes["WMT"] = Quote("WMT", 100, 0.2, 100, int(ny(2026, 11, 9, 16, 0).timestamp()), "Finnhub")  # yesterday
    s.sigmas = {"NVDA": -1.2, "WMT": 0.2}
    rows = preopen.premarket(s, cfg, ny(2026, 11, 10, 9, 0))
    assert [r["ticker"] for r in rows] == ["NVDA"]


class Ctx:
    def __init__(self, tmp):
        self.cfg = Config.load()
        self.cfg.watchlist = ["NVDA", "WMT"]
        self.state = State(tmp)
        self.failed_sources = []
        self.now = ny(2026, 11, 10, 16, 15)


def test_close_render(tmp_path):
    ctx = Ctx(tmp_path)
    s = Snapshot(date(2026, 11, 10), date(2026, 11, 10), date(2026, 11, 10))
    for sym, chg in {"SPY": 0.5, "QQQ": 0.8, "DIA": 0.1, "IWM": -0.3, "XLK": 1.2, "XLE": -0.9,
                     "NVDA": 4.0, "WMT": 0.1}.items():
        s.quotes[sym] = Quote(sym, 100, chg, 100, 0, "t")
    s.sigmas = {"NVDA": 1.6, "WMT": 0.1}
    facts = close.build(ctx.cfg, s)
    msg = close.render(ctx, s, facts, {"headline": "יום ירוק"}, "label", [])
    assert "🌆" in msg and "NVDA" in msg and "(1.6σ)" in msg
    assert "שאר הרשימה (1) בלי תנועה חריגה" in msg
    assert "▲ +0.50%" in msg


def test_weekly_render_without_model(tmp_path):
    ctx = Ctx(tmp_path)
    s = Snapshot(date(2026, 11, 15), date(2026, 11, 15), date(2026, 11, 13))
    for sym in ctx.cfg.index_symbols + ctx.cfg.sector_symbols + ctx.cfg.watchlist:
        ctx.state.set_history(sym, [[f"2026-10-{d:02d}", 100.0 + d * 0.1] for d in range(1, 31)]
                              + [["2026-11-06", 100.0], ["2026-11-13", 102.0]])
    facts = weekly.build(ctx, s)
    assert facts["indices_week"][0]["change_pct"] == 2.0
    msg = weekly.render(ctx, s, facts, None, "גיבוי")
    assert "📅" in msg and "🚉" in msg and "▲ +2.00%" in msg
