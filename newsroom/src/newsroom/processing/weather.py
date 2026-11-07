"""🌦️ Market weather: one composite mood score, 0 (storm) to 100 (sunshine).

Each input is mapped to 0-100 (higher = calmer / more risk appetite), then weighted. Inputs
that are missing are dropped and the weights re-normalised, so the score never invents data.

  VIX level        30%   12 -> 100, 20 -> 60, 32 -> 0
  S&P 500 today    20%   -2.5% -> 0, 0 -> 50, +2.5% -> 100
  breadth          20%   share of the 11 sector ETFs that are up
  10Y yield change 10%   +10bp -> 20 (rising yields weigh on equities)
  dollar (UUP)     10%   a stronger dollar is a mild headwind
  bitcoin 24h      10%   a risk-appetite gauge
"""
from __future__ import annotations


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


STATES = [
    (70, "sunny", "שמשי", "☀️"),
    (55, "partly", "בהיר חלקית", "🌤️"),
    (42, "cloudy", "מעונן", "☁️"),
    (28, "rain", "גשום", "🌧️"),
    (0, "storm", "סערה", "⛈️"),
]

WEIGHTS = {"vix": 0.30, "spx": 0.20, "breadth": 0.20, "yield": 0.10, "dollar": 0.10, "btc": 0.10}


def components(vix: float | None, spx_pct: float | None, sectors_up: int | None, sectors_total: int | None,
               yield_bp: float | None, dollar_pct: float | None, btc_pct: float | None) -> dict[str, float]:
    c: dict[str, float] = {}
    if vix is not None:
        c["vix"] = clamp(100 - (vix - 12) * 5)
    if spx_pct is not None:
        c["spx"] = clamp(50 + spx_pct * 20)
    if sectors_total:
        c["breadth"] = clamp(100 * (sectors_up or 0) / sectors_total)
    if yield_bp is not None:
        c["yield"] = clamp(50 - yield_bp * 3)
    if dollar_pct is not None:
        c["dollar"] = clamp(50 - dollar_pct * 25)
    if btc_pct is not None:
        c["btc"] = clamp(50 + btc_pct * 7)
    return c


def score(comp: dict[str, float]) -> float | None:
    if not comp:
        return None
    w = sum(WEIGHTS[k] for k in comp)
    return round(sum(comp[k] * WEIGHTS[k] for k in comp) / w, 1)


def state_of(s: float | None) -> dict:
    if s is None:
        return {"key": "unknown", "label": "אין מספיק נתונים", "icon": "❔"}
    for th, key, label, icon in STATES:
        if s >= th:
            return {"key": key, "label": label, "icon": icon}
    return {"key": "storm", "label": "סערה", "icon": "⛈️"}


def verdict(comp: dict[str, float], vix: float | None, up: int | None, total: int | None) -> str:
    """A deterministic one-liner: the two inputs that pull the score the most."""
    parts = []
    if vix is not None:
        parts.append("תנודתיות נמוכה" if vix < 16 else "תנודתיות גבוהה" if vix > 24 else "תנודתיות בינונית")
    if total:
        if up is not None and up >= total * 0.7:
            parts.append("רוב הסקטורים עולים")
        elif up is not None and up <= total * 0.3:
            parts.append("רוב הסקטורים יורדים")
        else:
            parts.append("שוק מעורב")
    if "yield" in comp and comp["yield"] <= 30:
        parts.append("תשואות האג\"ח עולות")
    if "btc" in comp and comp["btc"] <= 25:
        parts.append("ביטקוין בירידה חדה")
    return " · ".join(parts)
