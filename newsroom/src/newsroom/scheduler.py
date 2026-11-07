"""Time: the NYSE calendar, New York <-> Israel, and "is an edition due right now?".

Every time is derived from America/New_York and converted with zoneinfo. Nothing assumes a
fixed offset: Israel and the US switch clocks on different dates, so for a few weeks a year
the gap is 6 hours instead of 7.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
IL = ZoneInfo("Asia/Jerusalem")
UTC = ZoneInfo("UTC")

OPEN_ET = time(9, 30)
CLOSE_ET = time(16, 0)
EARLY_CLOSE_ET = time(13, 0)

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
HEB_DAYS = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]


# --------------------------------------------------------------- calendar ---

def easter(year: int) -> date:
    """Gregorian Easter Sunday (anonymous Gregorian algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    d = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def _observed(d: date) -> date:
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def nyse_holidays(year: int) -> dict[date, str]:
    h: dict[date, str] = {}
    ny = date(year, 1, 1)
    if ny.weekday() != 5:                 # NYSE skips a Saturday New Year (no Dec 31 close)
        h[_observed(ny)] = "New Year's Day"
    h[_nth_weekday(year, 1, 0, 3)] = "Martin Luther King Jr. Day"
    h[_nth_weekday(year, 2, 0, 3)] = "Presidents' Day"
    h[easter(year) - timedelta(days=2)] = "Good Friday"
    h[_last_weekday(year, 5, 0)] = "Memorial Day"
    if year >= 2022:
        h[_observed(date(year, 6, 19))] = "Juneteenth"
    h[_observed(date(year, 7, 4))] = "Independence Day"
    h[_nth_weekday(year, 9, 0, 1)] = "Labor Day"
    h[_nth_weekday(year, 11, 3, 4)] = "Thanksgiving"
    h[_observed(date(year, 12, 25))] = "Christmas"
    return h


def nyse_early_closes(year: int) -> dict[date, str]:
    e: dict[date, str] = {}
    jul3 = date(year, 7, 3)
    if jul3.weekday() <= 3:               # Mon-Thu; when Jul 3 is Fri it is the observed holiday
        e[jul3] = "Independence Day eve"
    e[_nth_weekday(year, 11, 3, 4) + timedelta(days=1)] = "Day after Thanksgiving"
    dec24 = date(year, 12, 24)
    if dec24.weekday() <= 3:
        e[dec24] = "Christmas Eve"
    return e


def is_trading_day(d: date, extra_closures: list | None = None) -> bool:
    if d.weekday() >= 5:
        return False
    if d in nyse_holidays(d.year):
        return False
    closures = {date.fromisoformat(str(x)) for x in (extra_closures or [])}
    return d not in closures


def holiday_name(d: date) -> str | None:
    return nyse_holidays(d.year).get(d)


def session(d: date, extra_closures: list | None = None) -> tuple[datetime, datetime] | None:
    """(open, close) of the regular session on NY date `d`, tz-aware in New York time."""
    if not is_trading_day(d, extra_closures):
        return None
    close = EARLY_CLOSE_ET if d in nyse_early_closes(d.year) else CLOSE_ET
    return datetime.combine(d, OPEN_ET, NY), datetime.combine(d, close, NY)


def previous_trading_day(d: date, extra_closures: list | None = None) -> date:
    d -= timedelta(days=1)
    while not is_trading_day(d, extra_closures):
        d -= timedelta(days=1)
    return d


def last_completed_session(now: datetime, extra_closures: list | None = None) -> date:
    """NY date of the most recent session whose close is already behind `now`."""
    ny_now = now.astimezone(NY)
    d = ny_now.date()
    s = session(d, extra_closures)
    if s and ny_now >= s[1]:
        return d
    return previous_trading_day(d, extra_closures)


def market_open_in_israel(d: date) -> datetime | None:
    s = session(d)
    return s[0].astimezone(IL) if s else None


# --------------------------------------------------------------- editions ---

def _hm(value: str) -> time:
    h, m = value.split(":")
    return time(int(h), int(m))


def morning_due(now: datetime, cfg: dict, sent_on: str | None) -> bool:
    """Is the morning edition due? `cfg` is settings['editions']['morning'].

    A late or skipped GitHub cron is caught by the next run: the edition is due from a few
    minutes before its time until `latest`, as long as it was not sent on that Israeli date.
    """
    il = now.astimezone(IL)
    if WEEKDAYS[il.weekday()] not in cfg.get("weekdays", WEEKDAYS):
        return False
    target = datetime.combine(il.date(), _hm(cfg.get("time", "07:00")), IL)
    earliest = target - timedelta(minutes=int(cfg.get("earliest_minutes_before", 5)))
    latest = datetime.combine(il.date(), _hm(cfg.get("latest", "12:00")), IL)
    if not (earliest <= il <= latest):
        return False
    return sent_on != il.date().isoformat()


def in_quiet_hours(now: datetime, start: str, end: str) -> bool:
    t = now.astimezone(IL).time()
    s, e = _hm(start), _hm(end)
    return (s <= t or t < e) if s > e else (s <= t < e)


def et_to_il(d: date, hhmm: str) -> datetime:
    return datetime.combine(d, _hm(hhmm), NY).astimezone(IL)


def heb_date(d: date) -> str:
    return f"יום {HEB_DAYS[d.weekday()]} {d.day}.{d.month}"
