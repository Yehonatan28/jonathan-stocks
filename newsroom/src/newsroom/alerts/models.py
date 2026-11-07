from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Alert:
    key: str                    # dedupe key: the same key is never sent twice
    kind: str                   # move | market | earnings | filing | story | megacap | macro | fed
    score: float                # importance 1-10
    headline: str               # first line, already HTML-escaped
    what: str                   # template sentence (used when the model is unavailable)
    why: str
    symbol: str | None = None
    tickers: list[str] = field(default_factory=list)
    url: str | None = None
    source: str | None = None
    level: int = 0              # escalation level: a higher level breaks the cooldown
    facts: dict = field(default_factory=dict)       # what the model may use
    tokens: list[str] = field(default_factory=list)  # for story similarity
    urgent: bool = False
    silent: bool = False

    def to_queue(self, ts: float) -> dict:
        d = asdict(self)
        d["ts"] = ts
        for k in ("facts", "tokens"):
            d.pop(k)
        return d
