"""One HTTP helper for every source: timeouts, retry with exponential backoff, rate limits."""
from __future__ import annotations

import logging
import random
import threading
import time
from collections import deque
from typing import Any

import requests

log = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}
DEFAULT_UA = "Mozilla/5.0 (compatible; NewsroomBot/1.0; personal market digest)"


class SourceError(RuntimeError):
    """A source did not answer usefully. Callers degrade instead of crashing."""


class RateLimiter:
    """At most `calls` per `period` seconds, shared between threads."""

    def __init__(self, calls: int, period: float = 60.0):
        self.calls, self.period = calls, period
        self._stamps: deque[float] = deque()
        self._lock = threading.Lock()

    def wait(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                while self._stamps and now - self._stamps[0] >= self.period:
                    self._stamps.popleft()
                if len(self._stamps) < self.calls:
                    self._stamps.append(now)
                    return
                sleep_for = self.period - (now - self._stamps[0]) + 0.05
            time.sleep(sleep_for)


_session = requests.Session()


def request(method: str, url: str, *, params: dict | None = None, headers: dict | None = None,
            json: Any = None, timeout: float = 15, retries: int = 3,
            limiter: RateLimiter | None = None, backoff: float = 2.0) -> requests.Response:
    hdrs = {"User-Agent": DEFAULT_UA}
    hdrs.update(headers or {})
    last: Exception | None = None
    for attempt in range(retries + 1):
        if limiter:
            limiter.wait()
        try:
            resp = _session.request(method, url, params=params, headers=hdrs, json=json, timeout=timeout)
        except requests.RequestException as exc:
            last = exc
        else:
            if resp.status_code < 400:
                return resp
            if resp.status_code not in RETRY_STATUS:
                raise SourceError(f"HTTP {resp.status_code} from {url.split('?')[0]}")
            last = SourceError(f"HTTP {resp.status_code} from {url.split('?')[0]}")
            retry_after = resp.headers.get("Retry-After")
            if retry_after and retry_after.isdigit() and attempt < retries:
                time.sleep(min(int(retry_after), 30))
                continue
        if attempt < retries:
            time.sleep(backoff * (2 ** attempt) + random.uniform(0, 0.5))
    raise SourceError(str(last) if last else f"failed: {url.split('?')[0]}")


def get_json(url: str, **kw: Any) -> Any:
    resp = request("GET", url, **kw)
    try:
        return resp.json()
    except ValueError as exc:
        raise SourceError(f"not JSON from {url.split('?')[0]}") from exc


def get_bytes(url: str, **kw: Any) -> bytes:
    return request("GET", url, **kw).content
