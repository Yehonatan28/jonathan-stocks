"""Instant bot commands: Worker behaviour (in Node) and the Python side reading the KV queue."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from newsroom import cloudflare
from newsroom.http import SourceError
from newsroom.storage.state import State
from newsroom.telegram import bot


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_worker_webhook_and_lock():
    root = Path(__file__).resolve().parents[1]
    r = subprocess.run(["node", str(root / "tests" / "worker_test.mjs")], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "worker ok" in r.stdout


class FakeKV:
    def __init__(self, items):
        self.items = dict(items)
        self.deleted = []

    def keys(self, prefix):
        return [k for k in self.items if k.startswith(prefix)]

    def get(self, k):
        return self.items.get(k)

    def delete(self, k):
        self.deleted.append(k)
        self.items.pop(k, None)


def test_take_bot_updates_in_order_and_once():
    kv = FakeKV({"tg:12": json.dumps({"update_id": 12}), "tg:9": json.dumps({"update_id": 9}), "data.json": "{}"})
    ups = cloudflare.take_bot_updates(kv)
    assert [u["update_id"] for u in ups] == [9, 12]
    assert kv.deleted == ["tg:9", "tg:12"] and "data.json" in kv.items
    assert cloudflare.take_bot_updates(kv) == []


class WebhookTG:
    chat_id = "42"

    def updates(self, offset):
        raise SourceError("HTTP 409 from https://api.telegram.org/bot***/getUpdates")


def test_falls_back_to_kv_when_webhook_is_set(tmp_path, monkeypatch):
    kv = FakeKV({"tg:5": json.dumps({"update_id": 5, "message": {"chat": {"id": 42}, "text": "/list"}})})
    monkeypatch.setattr(cloudflare.KV, "from_env", classmethod(lambda cls: kv))
    ups = bot.fetch_updates(WebhookTG(), State(tmp_path))
    assert [u["update_id"] for u in ups] == [5]


def test_other_telegram_errors_still_raise(tmp_path):
    class Broken:
        def updates(self, offset):
            raise SourceError("HTTP 401 from telegram")
    with pytest.raises(SourceError):
        bot.fetch_updates(Broken(), State(tmp_path))
