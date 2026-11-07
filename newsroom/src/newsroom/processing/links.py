"""Relationships between holdings: MAGS overlap, bitcoin exposure, energy."""
from __future__ import annotations

from ..models import Quote

COMPANY_SUFFIXES = (" inc", " corp", " corporation", " co", " ltd", " plc", " holdings", " group",
                    " company", " incorporated", " class a", " class c", " technologies", ",")

# A few names are better known by another word than their registered name.
KNOWN_ALIASES = {
    "GOOG": ["Google", "Alphabet"], "GOOGL": ["Google", "Alphabet"], "META": ["Meta", "Facebook"],
    "MSTR": ["MicroStrategy", "Strategy Inc"], "TTWO": ["Take-Two", "Rockstar", "GTA"],
    "IBIT": ["iShares Bitcoin"], "SPCX": ["SpaceX", "Starlink"], "WMT": ["Walmart"],
    "TSLA": ["Tesla"], "NVDA": ["Nvidia"], "AAPL": ["Apple"], "AMZN": ["Amazon"], "MSFT": ["Microsoft"],
    "MAGS": ["Magnificent Seven", "Magnificent 7"], "XLE": ["Energy Select"],
}


def short_name(name: str) -> str:
    n = name.strip()
    low = n.lower()
    changed = True
    while changed:
        changed = False
        for suf in COMPANY_SUFFIXES:
            if low.endswith(suf):
                n, low = n[: -len(suf)].strip(), low[: -len(suf)].strip()
                changed = True
    return n


def aliases(ticker: str, registered_name: str | None) -> list[str]:
    out = list(KNOWN_ALIASES.get(ticker, []))
    if registered_name:
        s = short_name(registered_name)
        if len(s) >= 4 and s not in out:
            out.append(s)
    return out


def mags_overlap(watchlist: list[str], group: dict, quotes: dict[str, Quote], sigmas: dict[str, float],
                 min_sigma: float = 1.0) -> dict | None:
    """How much of the watchlist is the MAGS basket twice, and did those names move together?"""
    if group.get("etf") not in watchlist:
        return None
    members = [m for m in group.get("members", []) if m in watchlist]
    if not members:
        return None
    up = [m for m in members if m in quotes and sigmas.get(m, 0) >= min_sigma]
    down = [m for m in members if m in quotes and sigmas.get(m, 0) <= -min_sigma]
    total = len(group.get("members", []))
    together = up if len(up) >= len(down) else down
    return {
        "members_held": members,
        "held_count": len(members),
        "basket_size": total,
        "moved_together": together if len(together) >= 3 else [],
        "direction": ("up" if together is up else "down") if len(together) >= 3 else None,
    }
