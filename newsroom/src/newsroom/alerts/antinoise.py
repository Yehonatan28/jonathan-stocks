"""Against noise: every alert must be worth the buzz in the pocket.

Order of checks for each candidate (highest score first):
  1. below threshold            -> dropped (it may still appear in an edition)
  2. same key already sent      -> dropped
  3. same story, new headline   -> dropped (word overlap with a story sent in the last 48h)
  4. ticker in cooldown         -> queued, unless it is a material development
                                   (higher σ level, now urgent, or a new event type)
  5. alerts paused (/pause)     -> queued
  6. quiet hours                -> urgent: sent silently; others: queued
  7. daily cap reached          -> queued (urgent alerts are never capped)
Queued alerts are shown in the next edition, once.
"""
from __future__ import annotations

from datetime import datetime

from .. import scheduler as sch
from ..processing.cluster import similarity
from .models import Alert

MATERIAL_KINDS = {"earnings", "filing", "macro", "fed"}
KEEP_SECONDS = 3 * 86400
QUEUE_MAX = 30


class AntiNoise:
    def __init__(self, state, settings: dict, now: float):
        self.state, self.now = state, now
        a = settings.get("alerts", {})
        self.threshold = float(a.get("threshold", 7))
        self.urgent_at = float(a.get("urgent", 9))
        self.cooldown = float(a.get("cooldown_minutes", 120)) * 60
        self.cap = int(a.get("daily_cap", 8))
        q = settings.get("quiet_hours", {})
        self.quiet = sch.in_quiet_hours(datetime.fromtimestamp(now, sch.UTC), q.get("start", "23:30"),
                                        q.get("end", "06:30"))
        self._batch: dict[str, dict] = {}
        self.mem = state.data.setdefault("alerts", {})
        for k, default in (("sent", {}), ("tickers", {}), ("stories", []), ("queued_keys", {})):
            self.mem.setdefault(k, default)
        self.today = datetime.fromtimestamp(now, sch.IL).date().isoformat()
        if self.mem.get("day") != self.today:
            self.mem["day"], self.mem["count"] = self.today, 0

    @property
    def paused(self) -> bool:
        p = self.state.get("paused_until")
        return bool(p and p > self.now)

    def _seen_story(self, a: Alert) -> bool:
        if a.kind != "story" or not a.tokens:
            return False
        tk = set(a.tokens)
        return any(similarity(tk, set(words)) >= 0.5 for ts, words in self.mem["stories"]
                   if self.now - ts < 2 * 86400)

    def _in_cooldown(self, a: Alert) -> bool:
        if a.kind in MATERIAL_KINDS:
            return False
        for t in a.tickers or ([a.symbol] if a.symbol else []):
            last = self._batch.get(t) or self.mem["tickers"].get(t)
            if not last or self.now - last["ts"] >= self.cooldown:
                continue
            escalated = a.level > last.get("level", 0) or (a.urgent and not last.get("urgent"))
            if not escalated:
                return True
        return False

    def decide(self, alerts: list[Alert]) -> tuple[list[Alert], list[Alert]]:
        send, queue = [], []
        sent_now = 0
        self._batch: dict[str, dict] = {}
        for a in sorted(alerts, key=lambda x: -x.score):
            a.urgent = a.score >= self.urgent_at
            if a.score < self.threshold or a.key in self.mem["sent"] or self._seen_story(a):
                continue
            if self._in_cooldown(a) or self.paused:
                queue.append(a)
                continue
            if self.quiet:
                if a.urgent:
                    a.silent = True
                    send.append(a)
                else:
                    queue.append(a)
                continue
            if not a.urgent and self.mem["count"] + sent_now >= self.cap:
                queue.append(a)
                continue
            send.append(a)
            if not a.urgent:
                sent_now += 1
            # a ticker already alerted in this batch does not get a second, weaker alert now
            for t in a.tickers:
                self._batch[t] = {"ts": self.now, "level": a.level, "urgent": a.urgent, "kind": a.kind}
        return send, self._dedupe_queue(queue)

    def _dedupe_queue(self, queue: list[Alert]) -> list[Alert]:
        out = []
        for a in queue:
            if a.key not in self.mem["queued_keys"]:
                out.append(a)
        return out

    def commit(self, sent: list[Alert], queued: list[Alert]) -> None:
        for a in sent:
            self.mem["sent"][a.key] = self.now
            if not a.urgent:
                self.mem["count"] += 1
            if a.tokens:
                self.mem["stories"].append([self.now, a.tokens])
            for t in a.tickers:
                self.mem["tickers"][t] = {"ts": self.now, "level": a.level, "urgent": a.urgent, "kind": a.kind}
        q = self.state.data.setdefault("alert_queue", [])
        for a in queued:
            self.mem["queued_keys"][a.key] = self.now
            q.append(a.to_queue(self.now))
        del q[:-QUEUE_MAX]
        self._prune()

    def _prune(self) -> None:
        cut = self.now - KEEP_SECONDS
        self.mem["sent"] = {k: v for k, v in self.mem["sent"].items() if v >= cut}
        self.mem["queued_keys"] = {k: v for k, v in self.mem["queued_keys"].items() if v >= cut}
        self.mem["stories"] = [s for s in self.mem["stories"] if s[0] >= cut][-200:]
        self.mem["tickers"] = {k: v for k, v in self.mem["tickers"].items() if v["ts"] >= cut}


def take_queue(state, max_items: int = 8) -> list[dict]:
    """Editions call this: returns the queued alerts (best first) and clears the queue."""
    q = state.data.get("alert_queue", [])
    state.data["alert_queue"] = []
    return sorted(q, key=lambda a: -a.get("score", 0))[:max_items]
