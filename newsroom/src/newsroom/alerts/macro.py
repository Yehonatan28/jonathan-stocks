"""Macro releases: when CPI / jobs / PCE / GDP come out, what came out vs. the previous print.

FRED marks each value with realtime_start = the day it became public, so "released today"
is a fact from the data, not a guess from the clock.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from .. import scheduler as sch
from ..http import SourceError
from ..snapshot import Snapshot
from .detect import macro_alert
from .models import Alert

log = logging.getLogger(__name__)


def compute(kind: str, obs: list[dict]) -> tuple[float, float] | None:
    """obs newest first. Returns (value, previous) in the unit of `kind`."""
    v = [float(o["value"]) for o in obs[:3]]
    if kind == "mom":
        if len(v) < 3 or v[1] == 0 or v[2] == 0:
            return None
        return round((v[0] / v[1] - 1) * 100, 2), round((v[1] / v[2] - 1) * 100, 2)
    if kind == "diff":
        if len(v) < 3:
            return None
        return round(v[0] - v[1], 1), round(v[1] - v[2], 1)
    if len(v) < 2:
        return None
    return round(v[0], 2), round(v[1], 2)


UNITS = {"mom": "%", "level": "%", "diff": ""}


def values_today(ctx, snap: Snapshot, max_tier: int = 2, skip_seen: bool = False) -> list[tuple]:
    """[(MacroEvent, rows)] for releases already out today. Read-only unless skip_seen."""
    fred = ctx.fred
    if not fred or not snap.macro_today:
        return []
    series_map = ctx.cfg.market.get("macro_series", {})
    seen = ctx.state.data.setdefault("macro_seen", {})
    today = snap.today_ny.isoformat()
    out = []
    for ev in snap.macro_today:
        if ev.tier > max_tier:
            continue
        release_at = datetime.combine(snap.today_ny, sch._hm(ev.time_et or "08:30"), sch.NY)
        if ctx.now < release_at + timedelta(minutes=1):
            continue
        rule = next((r for r in ctx.cfg.market.get("macro_releases", []) if r["label"] == ev.label), None)
        rows = []
        for sdef in (series_map.get(rule["match"], []) if rule else []):
            if skip_seen and seen.get(sdef["id"]) == today:
                continue
            try:
                obs = fred.observations(sdef["id"])
            except SourceError as exc:
                ctx.fail("FRED", exc)
                continue
            if not obs or obs[0].get("realtime_start") != today:
                continue                          # not on FRED yet; the next run will look again
            val = compute(sdef["kind"], obs)
            if val is None:
                continue
            if skip_seen:
                seen[sdef["id"]] = today
            rows.append({"label": sdef["label"], "value": val[0], "prev": val[1],
                         "unit": UNITS.get(sdef["kind"], ""), "period": obs[0]["date"]})
        if rows:
            out.append((ev, rows))
    return out


def released_today(ctx, snap: Snapshot) -> list[Alert]:
    return [macro_alert(ev.label, rows, snap, ev.tier) for ev, rows in values_today(ctx, snap, skip_seen=True)]
