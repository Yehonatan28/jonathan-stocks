"""Everything one run needs: config, state, the clock, source clients, and source health."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from functools import cached_property

from .config import Config
from .http import SourceError
from .scheduler import UTC
from .storage.state import State

log = logging.getLogger(__name__)


@dataclass
class Context:
    cfg: Config
    state: State
    now: datetime = field(default_factory=lambda: datetime.now(UTC))
    failed_sources: list[str] = field(default_factory=list)

    def fail(self, source: str, exc: Exception | str) -> None:
        log.warning("source %s failed: %s", source, exc)
        if source not in self.failed_sources:
            self.failed_sources.append(source)

    def _client(self, factory, label: str):
        try:
            return factory()
        except SourceError as exc:
            self.fail(label, exc)
            return None

    @cached_property
    def finnhub(self):
        from .collectors.finnhub import Finnhub
        return self._client(lambda: Finnhub(self.cfg.secrets.finnhub), "Finnhub")

    @cached_property
    def tiingo(self):
        from .collectors.tiingo import Tiingo
        return self._client(lambda: Tiingo(self.cfg.secrets.tiingo), "Tiingo")

    @cached_property
    def fred(self):
        from .collectors.fred import Fred
        return self._client(lambda: Fred(self.cfg.secrets.fred), "FRED")

    @cached_property
    def sec(self):
        from .collectors.sec import Sec
        return self._client(lambda: Sec(self.cfg.secrets.sec_contact, self.state), "SEC")

    @cached_property
    def telegram(self):
        from .telegram.send import Telegram
        return Telegram(self.cfg.secrets.telegram_token, self.cfg.secrets.telegram_chat_id)
