"""Bot commands. There is no server, so commands are collected with getUpdates on each run.

Only messages from the owner's chat_id are handled; anyone else is ignored silently.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Callable

from ..config import TICKER_RE, save_watchlist
from ..scheduler import IL
from .send import Telegram, esc

log = logging.getLogger(__name__)
MAX_TICKERS = 40

HELP = (
    "🤖 <b>פקודות</b>\n"
    "/add TICKER · הוספה לרשימה\n"
    "/remove TICKER · הסרה מהרשימה\n"
    "/list · הרשימה שלי\n"
    "/settings · ספים ושעות שקט\n"
    "/pause · עצירת התראות (אפשר גם /pause 6h או /pause 2d)\n"
    "/resume · חידוש התראות\n\n"
    "פקודות נקלטות בהרצה הבאה: תוך כדקה במצב מיידי, או עד כשעה בלי. המהדורות ממשיכות גם בזמן השהיה."
)


def parse_command(text: str) -> tuple[str, list[str]] | None:
    text = (text or "").strip()
    if not text.startswith("/"):
        return None
    head, *args = text.split()
    cmd = head[1:].split("@", 1)[0].lower()
    return cmd, args


def parse_duration(arg: str) -> int | None:
    m = re.fullmatch(r"(\d{1,3})([hd])", arg.lower())
    if not m:
        return None
    n = int(m.group(1))
    return n * (3600 if m.group(2) == "h" else 86400)


def handle(cmd: str, args: list[str], *, watchlist: list[str], state, settings: dict,
           validate: Callable[[str], bool], now: float | None = None) -> tuple[str, bool]:
    """Apply one command. Returns (reply_html, watchlist_changed). Pure apart from `state`."""
    now = now or time.time()
    if cmd in ("start", "help"):
        return HELP, False

    if cmd == "list":
        body = " · ".join(watchlist) if watchlist else "(ריקה)"
        paused = state.get("paused_until")
        extra = "\n⏸ ההתראות מושהות." if paused and paused > now else ""
        return f"📋 <b>הרשימה שלי</b> ({len(watchlist)})\n{esc(body)}{extra}", False

    if cmd in ("add", "remove"):
        if not args:
            return f"צריך סימול. למשל: /{cmd} NVDA", False
        changed, replies = False, []
        for raw in args[:10]:
            t = raw.upper().lstrip("$")
            if not TICKER_RE.match(t):
                replies.append(f"❌ {esc(raw)} הוא לא סימול תקין")
            elif cmd == "add":
                if t in watchlist:
                    replies.append(f"ℹ️ {t} כבר ברשימה")
                elif len(watchlist) >= MAX_TICKERS:
                    replies.append(f"❌ הרשימה מלאה ({MAX_TICKERS} סימולים)")
                elif not validate(t):
                    replies.append(f"❌ לא מצאתי מחיר ל-{t}. הסימול נכון?")
                else:
                    watchlist.append(t)
                    changed = True
                    replies.append(f"✅ {t} נוספה לרשימה")
            else:
                if t in watchlist:
                    watchlist.remove(t)
                    changed = True
                    replies.append(f"✅ {t} הוסרה מהרשימה")
                else:
                    replies.append(f"ℹ️ {t} לא ברשימה")
        return "\n".join(replies), changed

    if cmd == "settings":
        q = settings.get("quiet_hours", {})
        v = settings.get("volatility", {})
        m = settings.get("editions", {}).get("morning", {})
        return (
            "⚙️ <b>הגדרות</b>\n"
            f"שעות שקט: {q.get('start')}–{q.get('end')} (רק דחופות, בלי צליל)\n"
            f"תנועה חריגה: {v.get('alert_sigma')} סטיות תקן מהתנודתיות של כל נייר "
            f"(חלון של {v.get('lookback_days')} ימי מסחר)\n"
            f"מהדורת בוקר: {m.get('time')} שעון ישראל\n"
            "לשינוי: הקובץ config/settings.yaml"
        ), False

    if cmd == "pause":
        secs = parse_duration(args[0]) if args else None
        if args and secs is None:
            return "פורמט: /pause או /pause 6h או /pause 2d", False
        until = now + secs if secs else 10 ** 10
        state.set("paused_until", until)
        when = ("עד שתשלח /resume" if not secs
                else datetime.fromtimestamp(until, IL).strftime("עד %d.%m %H:%M"))
        return f"⏸ ההתראות הושהו {when}. המהדורות ממשיכות כרגיל.", False

    if cmd == "resume":
        state.set("paused_until", None)
        return "▶️ ההתראות חזרו לפעול.", False

    return "לא מכיר את הפקודה הזו. /help לרשימת הפקודות.", False


def fetch_updates(tg: Telegram, state) -> list[dict]:
    """Polling (getUpdates) by default. Once a webhook is set (instant mode), Telegram refuses
    getUpdates with 409, and the commands are waiting in Cloudflare KV, queued by the Worker."""
    from ..cloudflare import KV, take_bot_updates
    from ..http import SourceError
    try:
        return tg.updates(state.get("telegram_offset"))
    except SourceError as exc:
        msg = str(exc).lower()
        if "409" not in msg and "conflict" not in msg and "webhook" not in msg:
            raise
        kv = KV.from_env()
        if kv is None:
            raise SourceError("webhook is set but Cloudflare KV is not configured") from exc
        return take_bot_updates(kv)


def process_updates(tg: Telegram, state, cfg, validate: Callable[[str], bool],
                    updates: list[dict] | None = None) -> bool:
    """Read pending messages, answer the owner, persist the offset. Returns watchlist_changed."""
    if updates is None:
        updates = fetch_updates(tg, state)
    changed_any = False
    watchlist = list(cfg.watchlist)
    for u in updates:
        state.set("telegram_offset", u["update_id"] + 1)
        msg = u.get("message") or {}
        if str((msg.get("chat") or {}).get("id")) != tg.chat_id:
            continue                                     # not the owner: ignore
        parsed = parse_command(msg.get("text", ""))
        if not parsed:
            continue
        reply, changed = handle(*parsed, watchlist=watchlist, state=state, settings=cfg.settings,
                                validate=validate)
        changed_any |= changed
        try:
            tg.send(reply)
        except Exception as exc:  # noqa: BLE001 - a failed reply must not lose the command
            log.warning("reply failed: %s", exc)
    if changed_any:
        cfg.watchlist = watchlist
        save_watchlist(watchlist)
    return changed_any
