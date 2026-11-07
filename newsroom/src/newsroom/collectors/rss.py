"""RSS/Atom feeds (news sites, the Fed). Only title, link, source and time are kept."""
from __future__ import annotations

import html
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

from ..http import SourceError, get_bytes
from ..models import Story

log = logging.getLogger(__name__)

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
FEED_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
}


def clean(text: str | None, limit: int = 280) -> str:
    if not text:
        return ""
    text = _WS.sub(" ", html.unescape(_TAG.sub(" ", text))).strip()
    return text[:limit].rstrip() + ("…" if len(text) > limit else "")


def _ns(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def parse_date(value: str | None) -> int | None:
    if not value:
        return None
    value = value.strip()
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _first(node, names) -> str | None:
    for child in node:
        if _ns(child.tag) in names and child.text and child.text.strip():
            return child.text.strip()
    return None


def _link(node) -> str | None:
    for child in node:
        if _ns(child.tag) != "link":
            continue
        if child.text and child.text.strip():
            return child.text.strip()
        if child.attrib.get("href") and child.attrib.get("rel", "alternate") == "alternate":
            return child.attrib["href"]
    return None


def parse_feed(data: bytes, source: str, quality: int = 2, kind: str = "news") -> list[Story]:
    """RSS 2.0 or Atom bytes -> stories. Never raises on bad XML."""
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError:
        return []
    out = []
    for n in root.iter():
        if _ns(n.tag) not in ("item", "entry"):
            continue
        title, link = clean(_first(n, ("title",)), 220), _link(n)
        if not title or not link:
            continue
        ts = parse_date(_first(n, ("pubDate", "published", "updated", "date")))
        out.append(Story(title=title, url=link, source=source, published=ts or 0, kind=kind,
                         summary=clean(_first(n, ("description", "summary"))), quality=quality))
    return out


def fetch_feeds(feeds: list[dict], kind: str = "news") -> tuple[list[Story], list[str]]:
    def one(f: dict):
        try:
            data = get_bytes(f["url"], headers=FEED_HEADERS, timeout=10, retries=1)
            return f, parse_feed(data, f["name"], int(f.get("quality", 2)), kind)
        except SourceError as exc:
            log.warning("feed %s: %s", f["key"], exc)
            return f, None

    stories: list[Story] = []
    failed: list[str] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for f, items in pool.map(one, feeds):
            if items is None:
                failed.append(f["key"])
            else:
                stories.extend(items)
    return stories, failed
