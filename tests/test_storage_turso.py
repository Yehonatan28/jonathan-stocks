"""The Turso backend, end to end, without the network.

A fake Turso answers the exact Hrana v2 pipeline protocol (request and response shapes as Turso
documents them) from an in-memory SQLite database. With it in place, the full security suite runs
through `storage.TursoConnection`: registration, sign-in, account isolation, settings, watchlists.
"""
import os
import runpy
import sqlite3
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class FakeTurso:
    def __init__(self):
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.calls = 0

    @staticmethod
    def _decode(a):
        t = a["type"]
        return None if t == "null" else int(a["value"]) if t == "integer" else float(a["value"]) if t == "float" else a.get("value")

    @staticmethod
    def _encode(v):
        if v is None:
            return {"type": "null"}
        if isinstance(v, int):
            return {"type": "integer", "value": str(v)}
        if isinstance(v, float):
            return {"type": "float", "value": v}
        return {"type": "text", "value": str(v)}

    def post(self, url, json=None, headers=None, timeout=None):
        assert url.startswith("https://") and url.endswith("/v2/pipeline")
        assert headers["Authorization"] == "Bearer test-token"
        self.calls += 1
        stmt = json["requests"][0]["stmt"]
        try:
            cur = self.db.execute(stmt["sql"], [self._decode(a) for a in stmt["args"]])
            self.db.commit()
            cols = [{"name": d[0], "decltype": None} for d in (cur.description or [])]
            rows = [[self._encode(v) for v in r] for r in cur.fetchall()]
            result = {"type": "ok", "response": {"type": "execute", "result": {
                "cols": cols, "rows": rows, "affected_row_count": max(cur.rowcount, 0),
                "last_insert_rowid": str(cur.lastrowid) if cur.lastrowid is not None else None}}}
        except sqlite3.Error as exc:
            result = {"type": "error", "error": {"message": f"SQLite error: {exc}", "code": "SQLITE_CONSTRAINT"}}
        return Resp({"baton": None, "base_url": None, "results": [result, {"type": "ok", "response": {"type": "close"}}]})


class Resp:
    status_code = 200

    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body

    def raise_for_status(self):
        pass


def test_security_suite_passes_on_the_turso_backend(monkeypatch, capsys):
    monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://jonathan-stocks-test.turso.io")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "test-token")
    fake = FakeTurso()
    import storage
    monkeypatch.setattr(storage.requests, "post", fake.post)
    assert storage.backend() == "turso"
    for mod in ("app", "engine"):
        sys.modules.pop(mod, None)
    with pytest.raises(SystemExit) as done:
        runpy.run_path(os.path.join(ROOT, "test_security.py"), run_name="__main__")
    out = capsys.readouterr().out
    assert "FAIL" not in out, out
    assert done.value.code in (0, None)
    assert fake.calls > 10                       # really went through the Turso adapter


def test_values_round_trip_and_constraint_errors(monkeypatch):
    import storage
    fake = FakeTurso()
    monkeypatch.setattr(storage.requests, "post", fake.post)
    c = storage.TursoConnection("libsql://x.turso.io", "test-token")
    c.executescript("CREATE TABLE t(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, qty REAL, note TEXT);")
    cur = c.execute("INSERT INTO t(name, qty, note) VALUES(?,?,?)", ("NVDA", 12.5, None))
    assert cur.lastrowid == 1
    row = c.execute("SELECT * FROM t WHERE id=?", (1,)).fetchone()
    assert row["name"] == "NVDA" and row["qty"] == 12.5 and row["note"] is None and row[0] == 1
    assert dict(zip(row.keys(), row)) == {"id": 1, "name": "NVDA", "qty": 12.5, "note": None}
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("INSERT INTO t(name) VALUES(?)", ("NVDA",))
    names = [r["name"] for r in c.execute("PRAGMA table_info(t)")]
    assert names == ["id", "name", "qty", "note"]
