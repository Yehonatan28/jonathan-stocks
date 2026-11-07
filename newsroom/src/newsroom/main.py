"""The heartbeat. Every scheduled run calls `python -m newsroom tick`; the code decides what is due.

Tasks:
  tick     bot commands + whatever edition is due now (the normal scheduled run)
  morning  send the morning edition now, regardless of the clock (manual test)
  probe    check every data source and key, report to Telegram
  whoami   print the chat ids that wrote to the bot (setup helper)
"""
from __future__ import annotations

import logging
import sys
import time
import traceback

from . import scheduler as sch
from .config import Config, scrub
from .context import Context
from .http import SourceError, request
from .storage.state import State

log = logging.getLogger("newsroom")


def _validate_ticker(ctx: Context):
    def check(t: str) -> bool:
        if not ctx.finnhub:
            return True                       # cannot verify; accept and let the next run show it
        try:
            return ctx.finnhub.quote(t) is not None
        except SourceError:
            return True
    return check


def watchdog(ctx: Context | None, exc: BaseException) -> None:
    """⚠️ Tell the owner a run failed. The same error is not repeated within 3 hours."""
    reason = scrub(f"{type(exc).__name__}: {exc}")[:300]
    try:
        if ctx is not None:
            last = ctx.state.get("watchdog", {})
            if last.get("reason") == reason and time.time() - last.get("ts", 0) < 3 * 3600:
                return
            ctx.state.set("watchdog", {"reason": reason, "ts": time.time()})
            ctx.state.save()
            ctx.telegram.send(f"⚠️ <b>המערכת נתקלה בתקלה</b>\n<code>{_esc(reason)}</code>\n"
                              "ההרצה הבאה תנסה שוב אוטומטית.")
    except Exception:  # noqa: BLE001
        log.exception("watchdog could not report")


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def healthcheck(ctx: Context, ok: bool) -> None:
    url = ctx.cfg.secrets.healthcheck_url
    if not url:
        return
    try:
        request("GET", url + ("" if ok else "/fail"), timeout=8, retries=1)
    except SourceError:
        pass


def tick(ctx: Context, force_morning: bool = False) -> None:
    from .editions import morning
    from .telegram import bot

    try:
        bot.process_updates(ctx.telegram, ctx.state, ctx.cfg, _validate_ticker(ctx))
    except SourceError as exc:
        ctx.fail("Telegram getUpdates", exc)

    mcfg = ctx.cfg.s("editions", "morning", default={})
    if force_morning or sch.morning_due(ctx.now, mcfg, ctx.state.sent_on("morning")):
        log.info("sending morning edition")
        morning.run(ctx, force=force_morning)

    ctx.state.prune(ctx.now.astimezone(sch.IL).date(), int(ctx.cfg.s("archive_days", default=90)))
    ctx.state.set("last_run", int(time.time()))


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    task = (argv or sys.argv[1:] or ["tick"])[0]

    if task == "whoami":
        from .tools.whoami import run as whoami
        return whoami()
    if task == "probe":
        from .tools.probe import run as probe
        return probe()

    ctx: Context | None = None
    try:
        ctx = Context(Config.load(), State())
        tick(ctx, force_morning=(task == "morning"))
        healthcheck(ctx, ok=True)
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("run failed:\n%s", scrub(traceback.format_exc()))
        watchdog(ctx, exc)
        if ctx:
            healthcheck(ctx, ok=False)
        return 1
    finally:
        if ctx:
            ctx.state.save()
