"""Dashboard data: weather score, waterfall, week line, MAGS, and a full build from demo state."""
import json
from datetime import date, datetime

from newsroom import scheduler as sch
from newsroom.config import Config
from newsroom.context import Context
from newsroom.processing import weather
from newsroom.site import build
from newsroom.tools import demo


def test_weather_extremes_and_missing_inputs():
    calm = weather.components(12, 1.5, 10, 11, -5, -0.2, 3)
    panic = weather.components(38, -3.5, 1, 11, 18, 1.2, -9)
    assert weather.score(calm) >= 80 and weather.state_of(weather.score(calm))["key"] == "sunny"
    assert weather.score(panic) <= 15 and weather.state_of(weather.score(panic))["key"] == "storm"
    only_vix = weather.components(20, None, None, None, None, None, None)
    assert weather.score(only_vix) == 60            # weights re-normalised, nothing invented
    assert weather.state_of(None)["key"] == "unknown"


def demo_ctx(tmp_path):
    now = datetime(2026, 11, 10, 13, 40, tzinfo=sch.NY).astimezone(sch.UTC)
    st = demo.make_state(tmp_path, now)
    return Context(Config.load(), st, now=now)


def test_full_build_from_demo_state(tmp_path):
    ctx = demo_ctx(tmp_path)
    d = build.build_data(ctx)
    json.dumps(d, ensure_ascii=False)                # serialisable
    assert d["weather"]["score"] is not None
    assert {r["symbol"] for r in d["indices"]} == {"SPY", "QQQ", "DIA", "IWM"}
    w = d["waterfall"]
    assert abs(sum(i["contribution"] for i in w["items"]) + w["residual"] - w["total"]) < 0.01
    assert d["stories"] and d["stories"][0]["score"] >= d["stories"][-1]["score"]
    assert any(c["name"] == "נפט" for c in d["chains"])
    assert d["mags"]["held_count"] == 6 and d["mags"]["etf_held"]
    assert d["intraday"]["series"]["NVDA"] and d["intraday"]["pins"]
    for comp in d["weather"]["components"]:
        assert "source" in comp and "asof" in comp      # every number carries its source and time


def test_week_line_marks_holiday_and_early_close(tmp_path):
    cfg = Config.load()
    wk = build.week_block(cfg, {"macro_upcoming": [], "earnings": []}, date(2026, 11, 24))
    days = {x["date"]: x for x in wk["days"]}
    assert days["2026-11-26"]["closed"] and days["2026-11-26"]["holiday"] == "Thanksgiving"
    assert days["2026-11-27"]["early"] and days["2026-11-27"]["close_il"] == "20:00"
    assert days["2026-11-24"]["today"] and days["2026-11-23"]["past"]


def test_maybe_build_throttles_and_writes_locally(tmp_path, monkeypatch):
    ctx = demo_ctx(tmp_path)
    out = tmp_path / "out" / "data.json"
    monkeypatch.setattr(build, "LOCAL_OUT", out)
    for k in ("CLOUDFLARE_ACCOUNT_ID", "CF_KV_NAMESPACE_ID", "CLOUDFLARE_API_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    assert build.maybe_build(ctx) is True and out.exists()
    assert build.maybe_build(ctx) is False            # within min_push_minutes
    assert build.maybe_build(ctx, force=True) is True
