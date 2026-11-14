"""Research run: timing, the honest track record, and the morning section."""
from datetime import datetime

from newsroom import scheduler as sch
from newsroom.config import Config
from newsroom.context import Context
from newsroom.editions.morning import research_section
from newsroom.research import run as rr
from newsroom.storage.state import State


def pick(**kw):
    p = {"symbol": "AMD", "date": "2026-11-02", "trigger": 100.0, "stop": 95.0, "target": 110.0, "rr": 2.0,
         "status": "watching"}
    p.update(kw)
    return p


def c(d, h, lo, close=None):
    return [d, lo, h, lo, close if close is not None else (h + lo) / 2, 1e6]


def test_track_record_target_hit():
    rows = {"AMD": [c("2026-11-03", 99, 97), c("2026-11-04", 101, 98), c("2026-11-05", 111, 104)]}
    p = rr.update_log([pick()], rows)[0]
    assert p["status"] == "target" and p["triggered_on"] == "2026-11-04" and p["r"] == 2.0


def test_track_record_stop_and_cancel_and_same_day_rule():
    stopped = rr.update_log([pick()], {"AMD": [c("2026-11-03", 101, 98), c("2026-11-04", 99, 94)]})[0]
    assert stopped["status"] == "stopped" and stopped["r"] == -1.0
    cancelled = rr.update_log([pick()], {"AMD": [c("2026-11-03", 99, 94)]})[0]
    assert cancelled["status"] == "cancelled" and "r" not in cancelled
    both = rr.update_log([pick()], {"AMD": [c("2026-11-03", 101, 98), c("2026-11-04", 112, 94)]})[0]
    assert both["status"] == "stopped"                 # touching stop and target on one day = stop


def test_track_record_is_incremental():
    log_rows = rr.update_log([pick()], {"AMD": [c("2026-11-03", 101, 98, 100.5)]})
    assert log_rows[0]["status"] == "triggered" and log_rows[0]["checked"] == "2026-11-03"
    log_rows = rr.update_log(log_rows, {"AMD": [c("2026-11-03", 101, 98), c("2026-11-04", 104, 100, 103)]})
    assert log_rows[0]["open_r"] == 0.6


def test_stats():
    s = rr.stats([pick(status="target", r=2.0, triggered_on="x"), pick(status="stopped", r=-1.0, triggered_on="y"),
                  pick(status="watching")])
    assert s["closed"] == 2 and s["win_rate"] == 50 and s["avg_r"] == 0.5 and s["watching"] == 1


def ctx_at(tmp_path, when):
    return Context(Config.load(), State(tmp_path), now=when.astimezone(sch.UTC))


def test_due_after_the_close_only_once(tmp_path):
    before = ctx_at(tmp_path, datetime(2026, 11, 13, 17, 30, tzinfo=sch.NY))
    after = ctx_at(tmp_path, datetime(2026, 11, 13, 18, 20, tzinfo=sch.NY))
    assert not rr.due(before) and rr.due(after)
    after.state.set_cache("research", {"session": "2026-11-13"})
    assert not rr.due(after)
    # Saturday: Friday's research is what is due, and it is done
    sat = Context(after.cfg, after.state, now=datetime(2026, 11, 14, 10, 0, tzinfo=sch.NY).astimezone(sch.UTC))
    assert not rr.due(sat)


def test_morning_section_wording():
    res = {"picks": [{"symbol": "AMD", "setup_he": "מתקרבת לנקודת פריצה", "score": 80.0, "status": "חדש",
                      "levels": {"trigger": 142.27, "stop": 133.07, "rr": 2.3}}]}
    s = research_section(res, "https://dash")
    assert "לא ייעוץ" in s and "טריגר 142.27" in s and "ביטול 133.07" in s and "#lab" in s
    for word in ("קנה", "מכור", "כדאי"):
        assert word not in s
    assert research_section({}) is None
