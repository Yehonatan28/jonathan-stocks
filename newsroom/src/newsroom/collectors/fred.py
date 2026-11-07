"""FRED (St. Louis Fed): daily macro series and the official release calendar."""
from __future__ import annotations

from datetime import date, timedelta

from ..http import SourceError, get_json
from ..models import MacroEvent

BASE = "https://api.stlouisfed.org/fred"


class Fred:
    def __init__(self, key: str):
        if not key:
            raise SourceError("FRED_API_KEY missing")
        self.key = key

    def _get(self, path: str, **params):
        params.update(api_key=self.key, file_type="json")
        return get_json(f"{BASE}{path}", params=params, timeout=15, retries=2)

    def latest(self, series_id: str) -> dict | None:
        """Last two valid observations -> {'date','value','prev','change'}."""
        d = self._get("/series/observations", series_id=series_id, sort_order="desc", limit=10)
        obs = [o for o in d.get("observations", []) if o.get("value") not in (".", "", None)]
        if not obs:
            return None
        cur = float(obs[0]["value"])
        prev = float(obs[1]["value"]) if len(obs) > 1 else None
        return {"date": obs[0]["date"], "value": cur, "prev": prev,
                "change": round(cur - prev, 4) if prev is not None else None}

    def observations(self, series_id: str, limit: int = 14) -> list[dict]:
        """Newest first. Each row has realtime_start = the day this value became public."""
        d = self._get("/series/observations", series_id=series_id, sort_order="desc", limit=limit)
        return [o for o in d.get("observations", []) if o.get("value") not in (".", "", None)]

    def release_dates(self, start: date, days: int = 7) -> list[dict]:
        d = self._get("/releases/dates", realtime_start=start.isoformat(),
                      realtime_end=(start + timedelta(days=days)).isoformat(),
                      include_release_dates_with_no_data="true", limit=1000,
                      order_by="release_date", sort_order="asc")
        return d.get("release_dates", [])


def match_macro(release_dates: list[dict], rules: list[dict], on: date | None = None) -> list[MacroEvent]:
    out: list[MacroEvent] = []
    seen = set()
    for r in release_dates:
        if on and r.get("date") != on.isoformat():
            continue
        name = r.get("release_name", "")
        for rule in rules:
            if rule["match"].lower() in name.lower():
                key = (rule["label"], r.get("date"))
                if key not in seen:
                    seen.add(key)
                    out.append(MacroEvent(label=rule["label"], date=r["date"],
                                          time_et=rule.get("time_et", ""), tier=int(rule.get("tier", 3))))
    return sorted(out, key=lambda e: (e.date, e.time_et, e.tier))
