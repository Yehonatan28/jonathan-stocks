"""The spoken morning edition: script for the ear, and never breaks the written edition."""
from datetime import date

from newsroom import audio


def test_speakable_turns_symbols_into_words():
    t = audio.speakable('🔴 <b>NVDA</b> ▼ −5.80% (2.2σ) · S&P 500 ▲ +0.81% · $108,420 · 10Y +8 נ"ב')
    assert "אנבידיה" in t and "ירידה של 5.80 אחוז" in t and "2.2 סטיות תקן" in t
    assert "אס אנד פי עלייה של 0.81 אחוז" in t and "108,420 דולר" in t
    assert "נקודות בסיס" in t and "לעשר שנים" in t
    assert "<" not in t and "🔴" not in t and "▲" not in t


def test_say_pct():
    assert audio.say_pct(1.234) == "עלייה של 1.2 אחוז"
    assert audio.say_pct(-0.04) == "ללא שינוי"
    assert audio.say_pct(None) == "אין נתון"


FACTS = {
    "session_note": None,
    "indices_last_session": [{"name": "S&P 500", "change_pct": -1.23}, {"name": 'נאסד"ק 100', "change_pct": -1.9}],
    "sectors_last_session": [{"name": "אנרגיה", "change_pct": 1.1}, {"name": "טכנולוגיה", "change_pct": -2.4}],
    "my_stocks": [{"ticker": "NVDA", "change_pct": -6.2}],
    "overnight": {"ביטקוין": {"price_usd": 104250, "change_24h_pct": 3.07}},
    "today": {"open_israel_time": "16:30", "early_close": False,
              "macro": [{"label": "מדד המחירים לצרכן (CPI)", "time_israel": "15:30"}],
              "fomc_decision": False, "earnings": [{"symbol": "WMT", "when": "לפני הפתיחה"}]},
}


def test_script_with_and_without_model_text():
    plain = audio.script(FACTS, None, date(2026, 11, 10))
    assert plain.startswith("בוקר טוב") and plain.rstrip().endswith("יום טוב.")
    assert "אנבידיה: ירידה של 6.2 אחוז." in plain
    assert "16:30" in plain and "וולמארט" in plain
    full = audio.script(FACTS, {"headline": "הטכנולוגיה הובילה ירידה",
                                "my_stocks": {"NVDA": "התחזית החלשה מכבידה."},
                                "three_things": [{"text": "א"}, {"text": "ב"}, {"text": "ג"}]}, date(2026, 11, 10))
    assert "שלושה דברים" in full and "התחזית החלשה מכבידה." in full


class Ctx:
    def __init__(self, enabled=True):
        self.failed = []
        self.cfg = type("C", (), {"s": lambda self, *a, default=None: {"enabled": enabled}})()
        self.telegram = None

    def fail(self, name, exc):
        self.failed.append(name)


def test_audio_failure_is_recorded_not_raised(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("blocked")
    monkeypatch.setattr(audio, "synthesize", boom)
    ctx = Ctx()
    assert audio.send_morning_audio(ctx, FACTS, None, date(2026, 11, 10)) is False
    assert ctx.failed == ["קול (edge-tts)"]


def test_audio_disabled_does_nothing():
    ctx = Ctx(enabled=False)
    assert audio.send_morning_audio(ctx, FACTS, None, date(2026, 11, 10)) is False and ctx.failed == []
