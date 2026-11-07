"""Plain data shapes passed between the modules."""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field


@dataclass
class Quote:
    symbol: str
    price: float
    change_pct: float          # vs previous close, in percent
    prev_close: float
    time: int                  # unix seconds of the last trade
    source: str


@dataclass
class Story:
    title: str
    url: str
    source: str
    published: int             # unix seconds
    kind: str = "news"         # news | sec | fed
    tickers: list[str] = field(default_factory=list)
    summary: str = ""          # short teaser for the model only; never stored or shown
    quality: int = 2

    @property
    def id(self) -> str:
        return hashlib.sha1(self.url.encode()).hexdigest()[:12]

    def archive_row(self) -> dict:
        """What may be stored: never the article text."""
        d = asdict(self)
        d.pop("summary")
        d["id"] = self.id
        return d


@dataclass
class Filing:
    ticker: str
    form: str
    filed: str                 # ISO date-time
    url: str
    items: str = ""            # 8-K item numbers, e.g. "2.02,9.01"


@dataclass
class EarningsEvent:
    symbol: str
    date: str
    hour: str                  # bmo | amc | dmh | ""
    eps_estimate: float | None
    eps_actual: float | None
    revenue_estimate: float | None
    revenue_actual: float | None


@dataclass
class MacroEvent:
    label: str
    date: str
    time_et: str
    tier: int
