"""Six headlines about one event are one story.

Stage 1 groups headlines by word overlap (no API calls, deterministic, testable). Stage 2
extends this with the full importance score.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..models import Story

STOP = set("""a an the of to in on for and or but with at by from as is are was were be been it its
this that these those after before over under into amid says said say new will would could may might
than then up down out more most about vs via report reports why how what when who stock stocks shares
market markets today week live update updates""".split())

_WORD = re.compile(r"[a-z0-9$%&.\-]+")


def tokens(title: str) -> set[str]:
    words = _WORD.findall(title.lower())
    out = set()
    for w in words:
        w = w.strip(".-")
        if len(w) < 2 or w in STOP:
            continue
        if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.add(w)
    return out


def similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / min(len(a), len(b)) * 0.5 + inter / len(a | b) * 0.5


@dataclass
class Cluster:
    stories: list[Story] = field(default_factory=list)
    words: set[str] = field(default_factory=set)

    @property
    def lead(self) -> Story:
        return max(self.stories, key=lambda s: (s.quality, s.published))

    @property
    def sources(self) -> set[str]:
        return {s.source for s in self.stories}

    @property
    def tickers(self) -> set[str]:
        return {t for s in self.stories for t in s.tickers}

    @property
    def latest(self) -> int:
        return max(s.published for s in self.stories)


def cluster(stories: list[Story], threshold: float = 0.45) -> list[Cluster]:
    """Greedy single pass, newest first. Duplicate URLs are dropped."""
    seen_urls: set[str] = set()
    clusters: list[Cluster] = []
    for s in sorted(stories, key=lambda x: -x.published):
        if s.url in seen_urls:
            continue
        seen_urls.add(s.url)
        tk = tokens(s.title)
        best, best_sim = None, 0.0
        for c in clusters:
            sim = similarity(tk, c.words)
            if sim > best_sim:
                best, best_sim = c, sim
        if best is not None and best_sim >= threshold:
            best.stories.append(s)
            best.words |= tk
        else:
            clusters.append(Cluster([s], set(tk)))
    return clusters


def hot(clusters: list[Cluster], n: int) -> list[Cluster]:
    """Stories covered by the most distinct sources, then by source quality."""
    return sorted(clusters, key=lambda c: (len(c.sources), sum(s.quality for s in c.stories), c.latest),
                  reverse=True)[:n]


def tag_tickers(stories: list[Story], names: dict[str, list[str]]) -> None:
    """Attach watchlist tickers a headline is about: "(NVDA)", "$NVDA" or the company name."""
    for s in stories:
        title = s.title
        found = set(s.tickers)
        for t, aliases in names.items():
            if re.search(rf"(\(|\$|\b)(NASDAQ:|NYSE:)?{re.escape(t)}(\)|\b)", title):
                found.add(t)
                continue
            for a in aliases:
                if a and re.search(rf"\b{re.escape(a)}\b", title, re.I):
                    found.add(t)
                    break
        s.tickers = sorted(found)
