from datetime import date, datetime

import pytest

from newsroom import scheduler as sch

MORNING = {"time": "07:00", "earliest_minutes_before": 5, "latest": "12:00",
           "weekdays": ["mon", "tue", "wed", "thu", "fri", "sat"]}


def il(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=sch.IL)


# ---------------------------------------------------------------- holidays ---

def test_easter():
    assert sch.easter(2026) == date(2026, 4, 5)
    assert sch.easter(2027) == date(2027, 3, 28)


def test_nyse_holidays_2026():
    h = sch.nyse_holidays(2026)
    expected = [date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3),
                date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7),
                date(2026, 11, 26), date(2026, 12, 25)]
    assert sorted(h) == expected


def test_nyse_holidays_2027_observed_rules():
    h = sch.nyse_holidays(2027)
    assert date(2027, 6, 18) in h          # Juneteenth on Saturday -> Friday
    assert date(2027, 7, 5) in h           # July 4 on Sunday -> Monday
    assert date(2027, 12, 24) in h         # Christmas on Saturday -> Friday
    assert date(2027, 3, 26) in h          # Good Friday
    assert date(2027, 1, 18) in h and date(2027, 2, 15) in h   # MLK, Presidents (during the trip)


def test_saturday_new_year_not_observed():
    assert date(2027, 12, 31) not in sch.nyse_holidays(2027)
    assert date(2027, 12, 31) not in sch.nyse_holidays(2028)
    assert sch.is_trading_day(date(2027, 12, 31))


def test_early_closes():
    assert set(sch.nyse_early_closes(2026)) == {date(2026, 11, 27), date(2026, 12, 24)}
    s = sch.session(date(2026, 11, 27))
    assert s[1].hour == 13
    # 2027: Christmas Eve is the observed holiday, so no early close that day
    assert date(2027, 12, 24) not in sch.nyse_early_closes(2027)


def test_extra_closures():
    assert not sch.is_trading_day(date(2026, 11, 10), ["2026-11-10"])


def test_previous_trading_day_over_weekend_and_holiday():
    assert sch.previous_trading_day(date(2026, 11, 30)) == date(2026, 11, 27)
    assert sch.previous_trading_day(date(2026, 11, 27)) == date(2026, 11, 25)   # skips Thanksgiving


# ------------------------------------------------------- time zones / DST ---

def test_open_in_israel_normal_and_dst_gap_weeks():
    # Normal: both on summer time or both on winter time -> 16:30
    assert sch.market_open_in_israel(date(2026, 11, 9)).strftime("%H:%M") == "16:30"
    assert sch.market_open_in_israel(date(2026, 6, 15)).strftime("%H:%M") == "16:30"
    # US moved to DST on 2026-03-08, Israel only on 2026-03-27 -> 15:30
    assert sch.market_open_in_israel(date(2026, 3, 16)).strftime("%H:%M") == "15:30"
    # Israel back to winter on 2026-10-25, US only on 2026-11-01 -> 15:30
    assert sch.market_open_in_israel(date(2026, 10, 27)).strftime("%H:%M") == "15:30"


def test_last_completed_session():
    # 07:00 Israel on Saturday -> Friday's session
    assert sch.last_completed_session(il(2026, 11, 14, 7, 0)) == date(2026, 11, 13)
    # 07:00 Israel on Tuesday -> Monday
    assert sch.last_completed_session(il(2026, 11, 10, 7, 0)) == date(2026, 11, 9)
    # Friday after Thanksgiving, morning in Israel -> Wednesday
    assert sch.last_completed_session(il(2026, 11, 27, 7, 0)) == date(2026, 11, 25)
    # during the session itself, the last *completed* one is the previous day
    assert sch.last_completed_session(il(2026, 11, 10, 18, 0)) == date(2026, 11, 9)


def test_et_to_il_cpi_time():
    assert sch.et_to_il(date(2026, 11, 10), "08:30").strftime("%H:%M") == "15:30"
    assert sch.et_to_il(date(2026, 3, 11), "08:30").strftime("%H:%M") == "14:30"


# ----------------------------------------------------------- morning due ---

@pytest.mark.parametrize("when,sent,due", [
    (il(2026, 11, 10, 6, 54), None, False),          # too early
    (il(2026, 11, 10, 6, 56), None, True),           # within the 5 minute lead
    (il(2026, 11, 10, 7, 40), None, True),           # cron was late: still sent
    (il(2026, 11, 10, 7, 40), "2026-11-10", False),  # already sent today
    (il(2026, 11, 10, 7, 40), "2026-11-09", True),   # yesterday's mark does not block
    (il(2026, 11, 10, 12, 1), None, False),          # past the give-up time
    (il(2026, 11, 8, 7, 0), None, False),            # Sunday: weekly summary day
])
def test_morning_due(when, sent, due):
    assert sch.morning_due(when, MORNING, sent) is due


def test_morning_due_across_dst_switch():
    # The same 07:00 local target is used before and after Israel's clock change
    assert sch.morning_due(il(2026, 3, 26, 7, 0), MORNING, None)
    assert sch.morning_due(il(2026, 3, 27, 7, 0), MORNING, None)
    assert sch.morning_due(il(2026, 10, 26, 7, 0), MORNING, None)


def test_utc_input_is_converted():
    utc = datetime(2026, 11, 10, 5, 0, tzinfo=sch.UTC)      # 07:00 in Israel (UTC+2)
    assert sch.morning_due(utc, MORNING, None)
    utc_summer = datetime(2026, 6, 16, 4, 0, tzinfo=sch.UTC)  # 07:00 in Israel (UTC+3)
    assert sch.morning_due(utc_summer, MORNING, None)


def test_quiet_hours_wrap_midnight():
    assert sch.in_quiet_hours(il(2026, 11, 10, 23, 45), "23:30", "06:30")
    assert sch.in_quiet_hours(il(2026, 11, 10, 3, 0), "23:30", "06:30")
    assert not sch.in_quiet_hours(il(2026, 11, 10, 6, 30), "23:30", "06:30")
    assert not sch.in_quiet_hours(il(2026, 11, 10, 12, 0), "23:30", "06:30")
