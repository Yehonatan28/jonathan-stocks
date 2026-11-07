"""Loading the YAML config and the secrets (which only ever come from the environment)."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]          # .../newsroom
CONFIG_DIR = ROOT / "config"
STATE_DIR = Path(os.environ.get("NEWSROOM_STATE_DIR", ROOT / "state"))

TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")

SECRET_NAMES = (
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "FINNHUB_API_KEY", "TIINGO_API_KEY",
    "FRED_API_KEY", "COINGECKO_API_KEY", "GEMINI_API_KEY", "SEC_CONTACT", "HEALTHCHECK_URL",
)


def _load(name: str) -> dict[str, Any]:
    with open(CONFIG_DIR / name, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@dataclass
class Secrets:
    telegram_token: str = ""
    telegram_chat_id: str = ""
    finnhub: str = ""
    tiingo: str = ""
    fred: str = ""
    coingecko: str = ""
    gemini: str = ""
    sec_contact: str = ""
    healthcheck_url: str = ""

    @classmethod
    def from_env(cls) -> "Secrets":
        g = lambda k: os.environ.get(k, "").strip()  # noqa: E731
        return cls(
            telegram_token=g("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=g("TELEGRAM_CHAT_ID"),
            finnhub=g("FINNHUB_API_KEY"),
            tiingo=g("TIINGO_API_KEY"),
            fred=g("FRED_API_KEY"),
            coingecko=g("COINGECKO_API_KEY"),
            gemini=g("GEMINI_API_KEY"),
            sec_contact=g("SEC_CONTACT"),
            healthcheck_url=g("HEALTHCHECK_URL"),
        )

    def values(self) -> list[str]:
        return [v for v in vars(self).values() if v and len(v) >= 6]


def scrub(text: str, secrets: Secrets | None = None) -> str:
    """Remove any secret value from a string before it is logged or sent."""
    secrets = secrets or Secrets.from_env()
    for v in secrets.values():
        text = text.replace(v, "***")
    # Telegram tokens / api keys that leak inside URLs
    text = re.sub(r"(token|key|api_key|apikey)=[^&\s]+", r"\1=***", text, flags=re.I)
    return text


@dataclass
class Config:
    settings: dict[str, Any]
    market: dict[str, Any]
    sources: dict[str, Any]
    watchlist: list[str]
    secrets: Secrets = field(default_factory=Secrets.from_env)

    @classmethod
    def load(cls) -> "Config":
        wl = _load("watchlist.yaml").get("tickers") or []
        return cls(
            settings=_load("settings.yaml"),
            market=_load("market.yaml"),
            sources=_load("sources.yaml"),
            watchlist=[str(t).upper() for t in wl],
        )

    # ---- convenience views -------------------------------------------------
    def s(self, *path: str, default: Any = None) -> Any:
        node: Any = self.settings
        for p in path:
            if not isinstance(node, dict) or p not in node:
                return default
            node = node[p]
        return node

    @property
    def index_symbols(self) -> list[str]:
        return [i["symbol"] for i in self.market.get("indices", [])]

    @property
    def sector_symbols(self) -> list[str]:
        return list(self.market.get("sectors", {}).keys())

    def all_quote_symbols(self) -> list[str]:
        m = self.market
        syms = (self.index_symbols + self.sector_symbols
                + [p["symbol"] for p in m.get("proxies", [])]
                + [p["symbol"] for p in m.get("israel", [])]
                + self.watchlist)
        seen: dict[str, None] = {}
        for s in syms:
            seen.setdefault(s, None)
        return list(seen)

    def display_name(self, symbol: str) -> str:
        for group in ("indices", "proxies", "israel"):
            for item in self.market.get(group, []):
                if item["symbol"] == symbol:
                    return item["name"]
        if symbol in self.market.get("yahoo_symbols", {}):
            return self.market["yahoo_symbols"][symbol]
        if symbol == "BTC":
            return "ביטקוין"
        sec = self.market.get("sectors", {}).get(symbol)
        return f"{sec} ({symbol})" if sec else symbol


def save_watchlist(tickers: list[str]) -> None:
    header = ("# רשימת המעקב. רק סימולים: בלי כמויות, סכומים או שווי.\n"
              "# אפשר לערוך ידנית, או מהבוט: /add TICKER, /remove TICKER\n")
    body = yaml.safe_dump({"tickers": tickers}, allow_unicode=True, sort_keys=False)
    (CONFIG_DIR / "watchlist.yaml").write_text(header + body, encoding="utf-8")
