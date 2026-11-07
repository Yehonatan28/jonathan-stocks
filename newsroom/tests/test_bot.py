from newsroom.storage.state import State
from newsroom.telegram import bot
from newsroom.telegram.send import split_message


SETTINGS = {"quiet_hours": {"start": "23:30", "end": "06:30"},
            "volatility": {"alert_sigma": 2.0, "lookback_days": 60},
            "editions": {"morning": {"time": "07:00"}}}


def handle(cmd, args, wl, state, valid=True):
    return bot.handle(cmd, args, watchlist=wl, state=state, settings=SETTINGS,
                      validate=lambda t: valid, now=1_000_000)


def test_parse_command():
    assert bot.parse_command("/add nvda") == ("add", ["nvda"])
    assert bot.parse_command("/list@MyBot") == ("list", [])
    assert bot.parse_command("hello") is None


def test_add_remove(tmp_path):
    s, wl = State(tmp_path), ["AAPL"]
    reply, changed = handle("add", ["nvda"], wl, s)
    assert changed and wl == ["AAPL", "NVDA"] and "✅" in reply
    reply, changed = handle("add", ["NVDA"], wl, s)
    assert not changed and "כבר" in reply
    reply, changed = handle("remove", ["AAPL"], wl, s)
    assert changed and wl == ["NVDA"]


def test_add_rejects_bad_or_unknown(tmp_path):
    s, wl = State(tmp_path), []
    _, changed = handle("add", ["<script>"], wl, s)
    assert not changed and wl == []
    _, changed = handle("add", ["ZZZZ"], wl, s, valid=False)
    assert not changed and wl == []


def test_pause_resume(tmp_path):
    s = State(tmp_path)
    handle("pause", ["6h"], [], s)
    assert s.get("paused_until") == 1_000_000 + 6 * 3600
    handle("resume", [], [], s)
    assert s.get("paused_until") is None
    reply, _ = handle("pause", ["forever"], [], s)
    assert "פורמט" in reply


class FakeTG:
    chat_id = "42"

    def __init__(self, updates):
        self._u, self.sent = updates, []

    def updates(self, offset):
        return self._u

    def send(self, text):
        self.sent.append(text)


class FakeCfg:
    def __init__(self):
        self.watchlist, self.settings = ["AAPL"], SETTINGS


def test_only_owner_is_answered(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "save_watchlist", lambda wl: None)
    s = State(tmp_path)
    tg = FakeTG([
        {"update_id": 10, "message": {"chat": {"id": 999}, "text": "/add TSLA"}},   # stranger
        {"update_id": 11, "message": {"chat": {"id": 42}, "text": "/add NVDA"}},    # owner
    ])
    cfg = FakeCfg()
    changed = bot.process_updates(tg, s, cfg, lambda t: True)
    assert changed and cfg.watchlist == ["AAPL", "NVDA"]
    assert len(tg.sent) == 1
    assert s.get("telegram_offset") == 12


def test_split_message_respects_limit():
    text = "\n\n".join(["א" * 1000] * 10)
    parts = split_message(text, 3900)
    assert all(len(p) <= 3900 for p in parts)
    assert "".join(parts).replace("\n", "") == text.replace("\n", "")
