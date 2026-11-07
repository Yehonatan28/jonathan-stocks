"""Setup helper: which chat ids wrote to the bot? (Send the bot any message first.)"""
from __future__ import annotations

from ..config import Secrets, scrub
from ..http import get_json


def run() -> int:
    s = Secrets.from_env()
    if not s.telegram_token:
        print("TELEGRAM_BOT_TOKEN missing")
        return 1
    try:
        d = get_json(f"https://api.telegram.org/bot{s.telegram_token}/getUpdates", retries=0)
    except Exception as exc:  # noqa: BLE001
        print("getUpdates failed:", scrub(str(exc)))
        return 1
    chats = {}
    for u in d.get("result", []):
        chat = (u.get("message") or {}).get("chat") or {}
        if chat.get("id"):
            chats[chat["id"]] = chat.get("first_name") or chat.get("title") or ""
    if not chats:
        print("No messages yet. Open the bot in Telegram, press Start, send 'hi', and run again.")
        return 1
    for cid, name in chats.items():
        print(f"chat_id = {cid}   ({name})")
    print("Put this number in the TELEGRAM_CHAT_ID secret.")
    return 0
