from newsroom import main


def test_quiet_exit_before_setup(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert main.main(["tick"]) == 0
