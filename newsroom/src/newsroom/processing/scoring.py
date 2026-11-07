"""Importance score for a story cluster, 1 to 10.

Rule-based and explainable: every point has a reason, which is kept for the dashboard.
An optional model rating can be blended in (30%), but it can only nudge, never decide alone.

  base                                   1.0
  distinct sources (beyond the first)   +1.0 each, max +4
  source quality (avg vs. 2)            +0.5 per level
  about my watchlist                    +2.0
  about a megacap                       +0.5
  actual price reaction (|σ| of tickers) +0.7 per σ, max +2.1
  high-impact keywords                  +1.0 first, +0.5 second, max +1.5
  official source (Fed / SEC)           +1.5
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .cluster import Cluster

# Plural/3rd-person forms matter: headlines say "jumps", not "jump". "cut(s)" is left out on
# purpose: OPEC cuts lift oil and rate cuts lift stocks, so the word has no fixed direction.
POS_WORDS = ("beat", "beats", "surge", "surges", "soar", "soars", "jump", "jumps", "rally", "rallies", "record",
             "raise", "raises", "lifts", "upgrade", "upgrades", "gain", "gains", "rise", "rises", "climb", "climbs",
             "strong", "approval", "approved", "boost", "boosts", "tops", "accelerate", "accelerates", "rebound")
NEG_WORDS = ("miss", "misses", "plunge", "plunges", "slump", "slumps", "fall", "falls", "drop", "drops",
             "downgrade", "downgrades", "weak", "warn", "warns", "probe", "lawsuit", "recall", "tumble", "tumbles",
             "sink", "sinks", "slide", "slides", "loss", "losses", "layoff", "layoffs", "halt", "halts", "bankrupt",
             "fear", "fears", "sell-off", "selloff", "slower", "slowdown", "lower", "lowers")


@dataclass
class Scored:
    cluster: Cluster
    score: float
    reasons: list[str] = field(default_factory=list)
    sentiment: int = 0          # -1, 0, +1

    @property
    def key(self) -> str:
        return "story:" + self.cluster.lead.id


def _has(text: str, kw: str) -> bool:
    return re.search(rf"(?<![a-z]){re.escape(kw)}(?![a-z])", text) is not None


def sentiment(title: str) -> int:
    t = title.lower()
    pos = sum(_has(t, w) for w in POS_WORDS)
    neg = sum(_has(t, w) for w in NEG_WORDS)
    return (pos > neg) - (neg > pos)


def score_cluster(c: Cluster, *, watchlist: set[str], megacaps: set[str], sigmas: dict[str, float],
                  keywords: list[str], llm_rating: float | None = None) -> Scored:
    reasons: list[str] = []
    s = 1.0
    n = len(c.sources)
    if n > 1:
        add = min(n - 1, 4) * 1.0
        s += add
        reasons.append(f"{n} מקורות")
    q = sum(x.quality for x in c.stories) / len(c.stories)
    if q != 2:
        s += (q - 2) * 0.5
    mine = c.tickers & watchlist
    if mine:
        s += 2.0
        reasons.append("ברשימה שלי: " + ", ".join(sorted(mine)))
    if c.tickers & megacaps:
        s += 0.5
    react = max((abs(sigmas.get(t, 0.0)) for t in c.tickers), default=0.0)
    if react >= 0.5:
        s += min(react, 3.0) * 0.7
        reasons.append(f"תגובת מחיר {react:.1f}σ")
    text = " ".join(x.title.lower() for x in c.stories)
    hits = [k for k in keywords if _has(text, k.lower())]
    if hits:
        s += 1.0 + (0.5 if len(hits) > 1 else 0.0)
        reasons.append("מילות מפתח: " + ", ".join(hits[:3]))
    if any(x.kind in ("fed", "sec") for x in c.stories):
        s += 1.5
        reasons.append("מקור רשמי")
    s = max(1.0, min(10.0, s))
    if llm_rating is not None:
        s = 0.7 * s + 0.3 * max(1.0, min(10.0, float(llm_rating)))
        reasons.append(f"דירוג המודל {llm_rating:g}")
    lead_sent = sentiment(c.lead.title)
    return Scored(c, round(s, 1), reasons, lead_sent)


def score_all(clusters: list[Cluster], cfg, sigmas: dict[str, float],
              llm_ratings: dict[str, float] | None = None) -> list[Scored]:
    wl, mega = set(cfg.watchlist), set(cfg.market.get("megacaps", []))
    kws = cfg.market.get("keywords_high", [])
    out = [score_cluster(c, watchlist=wl, megacaps=mega, sigmas=sigmas, keywords=kws,
                         llm_rating=(llm_ratings or {}).get(c.lead.id)) for c in clusters]
    return sorted(out, key=lambda x: -x.score)
