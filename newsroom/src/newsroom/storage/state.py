"""Persistent state, kept as small JSON files on the separate `data` branch.

Layout under STATE_DIR:
  state.json              offsets, what was sent when, paused flag, watchdog memory
  history/<SYM>.json      daily closes, for volatility thresholds
  cache/<name>.json       ticker->CIK map, company names, LLM results
  archive/YYYY-MM-DD.jsonl headlines seen that day (title, link, source, time - never text)
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from ..config import STATE_DIR


class State:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or STATE_DIR)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "state.json"
        self.data: dict[str, Any] = self._read(self.path, {})

    # ---- generic ----------------------------------------------------------
    @staticmethod
    def _read(path: Path, default: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return default

    @staticmethod
    def _write(path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(path)

    def save(self) -> None:
        self._write(self.path, self.data)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    # ---- editions -------------------------------------------------------
    def sent_on(self, edition: str) -> str | None:
        return self.data.get("editions_sent", {}).get(edition)

    def mark_sent(self, edition: str, on: str) -> None:
        self.data.setdefault("editions_sent", {})[edition] = on

    # ---- history / cache ----------------------------------------------------
    def history(self, symbol: str) -> list[list]:
        return self._read(self.root / "history" / f"{_safe(symbol)}.json", [])

    def set_history(self, symbol: str, rows: list[list]) -> None:
        self._write(self.root / "history" / f"{_safe(symbol)}.json", rows)

    def ohlc(self, symbol: str) -> list[list]:
        """[[date, open, high, low, close, volume], ...] oldest first, split-adjusted."""
        return self._read(self.root / "ohlc" / f"{_safe(symbol)}.json", [])

    def set_ohlc(self, symbol: str, rows: list[list]) -> None:
        self._write(self.root / "ohlc" / f"{_safe(symbol)}.json", rows)

    def cache(self, name: str, default: Any = None) -> Any:
        return self._read(self.root / "cache" / f"{name}.json", default if default is not None else {})

    def set_cache(self, name: str, value: Any) -> None:
        self._write(self.root / "cache" / f"{name}.json", value)

    # ---- archive ----------------------------------------------------------
    def archive(self, day: date, rows: list[dict]) -> None:
        if not rows:
            return
        path = self.root / "archive" / f"{day.isoformat()}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        known = set()
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    known.add(json.loads(line)["id"])
                except (ValueError, KeyError):
                    pass
        with path.open("a", encoding="utf-8") as fh:
            for r in rows:
                if r["id"] not in known:
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                    known.add(r["id"])

    def read_archive(self, start: date, end: date) -> list[dict]:
        rows = []
        d = start
        while d <= end:
            path = self.root / "archive" / f"{d.isoformat()}.jsonl"
            if path.exists():
                for line in path.read_text(encoding="utf-8").splitlines():
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        continue
            d += timedelta(days=1)
        return rows

    def prune(self, today: date, keep_days: int) -> int:
        cutoff = today - timedelta(days=keep_days)
        removed = 0
        for f in (self.root / "archive").glob("*.jsonl"):
            try:
                if date.fromisoformat(f.stem) < cutoff:
                    f.unlink()
                    removed += 1
            except ValueError:
                continue
        return removed


def _safe(symbol: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in symbol)
