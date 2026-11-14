"""The heartbeat. Every scheduled run calls `python -m newsroom tick`; the code decides what is due.

Tasks:
  tick     bot commands + due editions + alerts + dashboard (the normal scheduled run)
  morning | preopen | close | weekly   send that edition now, regardless of the clock (manual test)
  alerts   run only the alerts pass
  research run the technical research now (otherwise every evening after the close)
  bot      handle queued bot commands only (started instantly by the Worker in webhook mode)
  webhook_on | webhook_off   switch instant bot commands on or off
  site     rebuild the dashboard now
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


PART_HE = {"research": "מעבדת הסטאפים", "bot": "הבוט", "morning": "מהדורת הבוקר", "preopen": "מהדורת לפני הפתיחה", "close": "סיכום הסגירה",
           "weekly": "הסיכום השבועי", "alerts": "מנוע ההתראות", "dashboard": "הדשבורד", "startup": "ההפעלה"}


def watchdog(ctx: Context | None, exc: BaseException, where: str = "", more: int = 0) -> bool:
    """⚠️ Tell the owner a part failed. The same error is not repeated within 3 hours.
    Returns True when the owner knows (sent now, or already told recently)."""
    reason = scrub(f"{type(exc).__name__}: {exc}")[:300]
    if ctx is None:
        return False
    try:
        last = ctx.state.get("watchdog", {})
        if last.get("reason") == reason and time.time() - last.get("ts", 0) < 3 * 3600:
            return True
        part = PART_HE.get(where, where)
        extra = f"\n(ועוד {more} תקלות באותה הרצה)" if more else ""
        ctx.telegram.send(f"⚠️ <b>המערכת נתקלה בתקלה</b>" + (f" · {_esc(part)}" if part else "")
                          + f"\n<code>{_esc(reason)}</code>{extra}\nההרצה הבאה תנסה שוב אוטומטית.")
        ctx.state.set("watchdog", {"reason": reason, "ts": time.time()})
        return True
    except Exception:  # noqa: BLE001
        log.exception("watchdog could not report")
        return False


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


EDITIONS = ("morning", "preopen", "close", "weekly")


def due_editions(ctx: Context) -> list[str]:
    e, st = ctx.cfg.s("editions", default={}), ctx.state
    extra = ctx.cfg.market.get("extra_closures")
    due = []
    if sch.morning_due(ctx.now, e.get("morning", {}), st.sent_on("morning")):
        due.append("morning")
    if sch.preopen_due(ctx.now, e.get("preopen", {}), st.sent_on("preopen"), extra):
        due.append("preopen")
    if sch.close_due(ctx.now, e.get("close", {}), st.sent_on("close"), extra):
        due.append("close")
    if sch.weekly_due(ctx.now, e.get("weekly", {}), st.sent_on("weekly")):
        due.append("weekly")
    return due


def tick(ctx: Context, force: str | None = None) -> list[tuple[str, BaseException]]:
    """One heartbeat. Each part runs isolated: a failing part is reported, the others still run."""
    from .alerts import run as alerts
    from .editions import close, morning, preopen, weekly
    from .site import build as site
    from .telegram import bot

    errors: list[tuple[str, BaseException]] = []

    def part(name, fn):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            log.error("%s failed:\n%s", name, scrub(traceback.format_exc()))
            errors.append((name, exc))

    def commands():
        try:
            bot.process_updates(ctx.telegram, ctx.state, ctx.cfg, _validate_ticker(ctx))
        except SourceError as exc:
            ctx.fail("Telegram getUpdates", exc)

    part("bot", commands)
    if force == "bot":                     # instant mode: a command just arrived, nothing else to do
        return errors
    runners = {"morning": morning.run, "preopen": preopen.run, "close": close.run, "weekly": weekly.run}
    for name in ([force] if force in runners else due_editions(ctx)):
        log.info("edition due: %s", name)
        part(name, lambda n=name: runners[n](ctx))
    if force in (None, "alerts"):
        part("alerts", lambda: alerts.run(ctx))
    if force in (None, "research"):
        from .research import run as research
        part("research", lambda: research.run(ctx, force=force == "research"))
    part("dashboard", lambda: site.maybe_build(ctx, force=force == "site"))

    ctx.state.prune(ctx.now.astimezone(sch.IL).date(), int(ctx.cfg.s("archive_days", default=90)))
    ctx.state.set("last_run", int(time.time()))
    return errors


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    task = (argv or sys.argv[1:] or ["tick"])[0]

    if task == "whoami":
        from .tools.whoami import run as whoami
        return whoami()
    if task in ("webhook_on", "webhook_off"):
        from .tools.webhook import run as webhook
        return webhook(on=task == "webhook_on")
    if task == "probe":
        from .tools.probe import run as probe
        return probe()

    ctx: Context | None = None
    try:
        ctx = Context(Config.load(), State())
        errors = tick(ctx, force=None if task == "tick" else task)
        if errors:
            name, exc = errors[0]
            delivered = watchdog(ctx, exc, where=name, more=len(errors) - 1)
            healthcheck(ctx, ok=False)
            return 0 if delivered else 1
        healthcheck(ctx, ok=True)
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("run failed:\n%s", scrub(traceback.format_exc()))
        delivered = watchdog(ctx, exc, where="startup")
        if ctx:
            healthcheck(ctx, ok=False)
        return 0 if delivered else 1
    finally:
        if ctx:
            ctx.state.save()
