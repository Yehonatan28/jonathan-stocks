"""Switch instant bot commands on (Telegram -> Worker webhook) or off (back to polling).

Run from GitHub: Actions -> newsroom -> Run workflow -> task: webhook_on / webhook_off.
Needs: TELEGRAM_BOT_TOKEN, TG_WEBHOOK_SECRET, and dashboard_url (the Worker address) in settings.
"""
from __future__ import annotations

import os

from ..config import Config, scrub
from ..http import get_json, request


def run(on: bool = True) -> int:
    cfg = Config.load()
    token = cfg.secrets.telegram_token
    api = f"https://api.telegram.org/bot{token}"
    if not token:
        print("TELEGRAM_BOT_TOKEN missing")
        return 1
    try:
        if on:
            base = (cfg.s("dashboard_url") or "").rstrip("/")
            secret = os.environ.get("TG_WEBHOOK_SECRET", "").strip()
            if not base.startswith("https://") or not secret:
                print("Need dashboard_url (https://...workers.dev) in settings.yaml and the TG_WEBHOOK_SECRET secret.")
                return 1
            request("POST", f"{api}/setWebhook", json={"url": f"{base}/tg", "secret_token": secret,
                                                       "allowed_updates": ["message"], "max_connections": 5},
                    timeout=20, retries=1)
        else:
            request("POST", f"{api}/deleteWebhook", json={"drop_pending_updates": False}, timeout=20, retries=1)
        info = get_json(f"{api}/getWebhookInfo", retries=1).get("result", {})
    except Exception as exc:  # noqa: BLE001
        print("failed:", scrub(str(exc)))
        return 1
    state = "מיידי (webhook)" if info.get("url") else "רגיל (בדיקה בכל הרצה)"
    print(f"mode: {state} · pending: {info.get('pending_update_count', 0)}"
          + (f" · last error: {info['last_error_message']}" if info.get("last_error_message") else ""))
    try:
        from ..telegram.send import Telegram
        Telegram(token, cfg.secrets.telegram_chat_id).send(f"🤖 מצב הפקודות בבוט: <b>{state}</b>")
    except Exception as exc:  # noqa: BLE001
        print("could not notify:", scrub(str(exc)))
    return 0
