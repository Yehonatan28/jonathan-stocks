"""Sending to Telegram with parse_mode=HTML (far fewer escaping problems with Hebrew than MarkdownV2)."""
from __future__ import annotations

import html
import logging
import re
import time

from ..http import SourceError, request

log = logging.getLogger(__name__)
API = "https://api.telegram.org/bot{token}/{method}"
LIMIT = 3900          # Telegram allows 4096 characters; keep a margin


def esc(text: str | None) -> str:
    return html.escape(text or "", quote=False)


def link(url: str, label: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{esc(label)}</a>'


def split_message(text: str, limit: int = LIMIT) -> list[str]:
    """Split on blank lines (section boundaries), then on lines, never inside a tag."""
    if len(text) <= limit:
        return [text]
    parts, cur = [], ""
    for block in text.split("\n\n"):
        candidate = f"{cur}\n\n{block}" if cur else block
        if len(candidate) <= limit:
            cur = candidate
            continue
        if cur:
            parts.append(cur)
        if len(block) <= limit:
            cur = block
        else:
            cur = ""
            for line in block.split("\n"):
                cand = f"{cur}\n{line}" if cur else line
                if len(cand) > limit and cur:
                    parts.append(cur)
                    cur = line
                else:
                    cur = cand
    if cur:
        parts.append(cur)
    return parts


class Telegram:
    def __init__(self, token: str, chat_id: str):
        if not token or not chat_id:
            raise SourceError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing")
        self.token, self.chat_id = token, str(chat_id)

    def call(self, method: str, **payload):
        r = request("POST", API.format(token=self.token, method=method), json=payload, timeout=20, retries=2)
        d = r.json()
        if not d.get("ok"):
            raise SourceError(f"telegram {method}: {d.get('description')}")
        return d.get("result")

    def send(self, text: str, silent: bool = False, preview: bool = False) -> None:
        for part in split_message(text):
            payload = dict(chat_id=self.chat_id, text=part, parse_mode="HTML",
                           disable_notification=silent,
                           link_preview_options={"is_disabled": not preview})
            try:
                self.call("sendMessage", **payload)
            except SourceError as exc:
                if "parse" not in str(exc).lower() and "entities" not in str(exc).lower():
                    raise
                log.warning("HTML rejected, sending as plain text: %s", exc)
                payload.pop("parse_mode")
                payload["text"] = html.unescape(re.sub(r"<[^>]+>", "", part))
                self.call("sendMessage", **payload)

    def send_audio(self, path, title: str, performer: str = "", silent: bool = True) -> None:
        """Upload an MP3 (multipart). Telegram shows it as a playable track with a title."""
        import requests
        url = API.format(token=self.token, method="sendAudio")
        last = None
        for attempt in range(3):
            try:
                with open(path, "rb") as fh:
                    r = requests.post(url, data={"chat_id": self.chat_id, "title": title, "performer": performer,
                                                 "disable_notification": str(silent).lower()},
                                      files={"audio": ("morning.mp3", fh, "audio/mpeg")}, timeout=60)
                d = r.json()
                if d.get("ok"):
                    return
                last = d.get("description")
                if r.status_code < 500 and r.status_code != 429:
                    break
            except (requests.RequestException, ValueError) as exc:
                last = type(exc).__name__
            time.sleep(2 * 2 ** attempt)
        raise SourceError(f"telegram sendAudio: {last}")

    def updates(self, offset: int | None) -> list[dict]:
        params = {"timeout": 0, "allowed_updates": ["message"]}
        if offset is not None:
            params["offset"] = offset
        return self.call("getUpdates", **params) or []
