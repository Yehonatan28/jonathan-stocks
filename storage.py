"""Where accounts, portfolios, watchlists and alerts live.

* `TURSO_DATABASE_URL` + `TURSO_AUTH_TOKEN` set (production): a hosted libSQL database on Turso,
  reached over its HTTP API (Hrana v2 pipeline). No extra dependency: plain `requests`.
* Otherwise (local development, tests): a SQLite file, exactly as before.

`connect()` returns an object with the slice of the sqlite3 API the app uses: `execute()` returning a
cursor with `fetchone/fetchall/lastrowid/rowcount`, `executescript()`, `commit()`, `close()`, rows that
read by column name or index, and `sqlite3.IntegrityError` on a constraint violation, so the routes
work unchanged on either backend.
"""
from __future__ import annotations

import base64
import os
import sqlite3

import requests


def _http_url(url: str) -> str:
    url = url.strip().rstrip("/")
    for scheme in ("libsql://", "wss://", "ws://"):
        if url.startswith(scheme):
            return "https://" + url[len(scheme):]
    return url


def _arg(v):
    if v is None:
        return {"type": "null"}
    if isinstance(v, bool):
        return {"type": "integer", "value": str(int(v))}
    if isinstance(v, int):
        return {"type": "integer", "value": str(v)}
    if isinstance(v, float):
        return {"type": "float", "value": v}
    if isinstance(v, (bytes, bytearray)):
        return {"type": "blob", "base64": base64.b64encode(bytes(v)).decode()}
    return {"type": "text", "value": str(v)}


def _value(cell):
    t = cell.get("type")
    if t == "null":
        return None
    if t == "integer":
        return int(cell["value"])
    if t == "float":
        return float(cell["value"])
    if t == "blob":
        return base64.b64decode(cell.get("base64", ""))
    return cell.get("value")


class Row:
    """Reads like sqlite3.Row: by column name or position, and `dict(row)` works."""
    __slots__ = ("_cols", "_vals")

    def __init__(self, cols, vals):
        self._cols, self._vals = cols, vals

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._vals[key]
        return self._vals[self._cols.index(key)]

    def keys(self):
        return list(self._cols)

    def __iter__(self):
        return iter(self._vals)

    def __len__(self):
        return len(self._vals)


class Cursor:
    def __init__(self, cols=(), rows=(), lastrowid=None, rowcount=-1):
        self._rows = [Row(list(cols), list(r)) for r in rows]
        self.lastrowid, self.rowcount = lastrowid, rowcount

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def __iter__(self):
        return iter(self._rows)


class TursoConnection:
    """One statement per HTTP request, each committed on its own (the app commits after every write)."""

    def __init__(self, url: str, token: str, timeout: float = 10.0):
        self.endpoint = _http_url(url) + "/v2/pipeline"
        self.headers = {"Authorization": f"Bearer {token.strip()}", "Content-Type": "application/json"}
        self.timeout = timeout

    def execute(self, sql: str, params=()) -> Cursor:
        body = {"requests": [{"type": "execute", "stmt": {"sql": sql, "args": [_arg(p) for p in params]}},
                             {"type": "close"}]}
        r = requests.post(self.endpoint, json=body, headers=self.headers, timeout=self.timeout)
        if r.status_code == 401:
            raise sqlite3.OperationalError("Turso rejected the token (401)")
        r.raise_for_status()
        res = r.json()["results"][0]
        if res.get("type") == "error":
            msg = (res.get("error") or {}).get("message", "database error")
            if "UNIQUE" in msg or "constraint" in msg.lower():
                raise sqlite3.IntegrityError(msg)
            raise sqlite3.OperationalError(msg)
        out = res["response"]["result"]
        cols = [c.get("name") for c in out.get("cols", [])]
        rows = [[_value(c) for c in row] for row in out.get("rows", [])]
        last = out.get("last_insert_rowid")
        return Cursor(cols, rows, int(last) if last not in (None, "") else None, out.get("affected_row_count", -1))

    def executescript(self, script: str) -> None:
        for stmt in (s.strip() for s in script.split(";")):
            if stmt:
                self.execute(stmt)

    def commit(self) -> None:
        pass

    def close(self) -> None:
        pass


def backend() -> str:
    return "turso" if os.environ.get("TURSO_DATABASE_URL") and os.environ.get("TURSO_AUTH_TOKEN") else "sqlite"


def connect(sqlite_path: str):
    if backend() == "turso":
        return TursoConnection(os.environ["TURSO_DATABASE_URL"], os.environ["TURSO_AUTH_TOKEN"])
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    return conn
