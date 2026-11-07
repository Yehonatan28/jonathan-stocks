"""Volatility-adjusted moves: a 5% day is ordinary for MSTR and an event for WMT.

The threshold for each symbol is a multiple (default 2) of the standard deviation of its own
daily returns over the lookback window. A symbol with too little history (a recent IPO such as
SPCX in its first weeks) falls back to a conservative default stdev.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class VolProfile:
    stdev_pct: float
    days: int
    is_default: bool


def daily_returns(closes: list[float]) -> list[float]:
    return [(b / a - 1) * 100 for a, b in zip(closes, closes[1:]) if a > 0]


def stdev(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))


def profile(rows: list[list], before: str | None, lookback: int, min_days: int, default_pct: float) -> VolProfile:
    """`rows` = [[iso_date, close], ...]. Only closes strictly before `before` are used, so the
    move being judged never inflates its own yardstick."""
    closes = [c for d, c in rows if before is None or d < before]
    rets = daily_returns(closes[-(lookback + 1):])
    if len(rets) < min_days:
        return VolProfile(default_pct, len(rets), True)
    sd = stdev(rets)
    if sd <= 0:
        return VolProfile(default_pct, len(rets), True)
    return VolProfile(round(sd, 3), len(rets), False)


def sigma(change_pct: float, prof: VolProfile) -> float:
    return round(change_pct / prof.stdev_pct, 2) if prof.stdev_pct else 0.0


def threshold_pct(prof: VolProfile, k: float) -> float:
    return round(prof.stdev_pct * k, 2)
