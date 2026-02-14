from __future__ import annotations

import re
from datetime import datetime, timezone

import feedparser
import requests

USER_AGENT = "ai-intel-briefing/1.0 (+https://x.com)"
RSS_TIMEOUT_SECONDS = 15
RSS_RETRIES = 2


def _clean_html(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    no_tags = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", no_tags).strip()


def _fetch_feed_with_retries(url: str):
    last_error = None
    for attempt in range(RSS_RETRIES + 1):
        try:
            resp = requests.get(
                url,
                timeout=RSS_TIMEOUT_SECONDS,
                headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8"},
            )
            resp.raise_for_status()
            payload = (resp.content or b"").lstrip()
            return feedparser.parse(payload)
        except requests.RequestException as exc:
            last_error = exc
            if attempt < RSS_RETRIES:
                continue

    raise RuntimeError(f"RSS fetch failed for {url}: {last_error!r}")


def fetch_rss(url: str, limit: int = 30, quiet: bool = False):
    try:
        feed = _fetch_feed_with_retries(url)
    except Exception as exc:
        if not quiet:
            print("RSS fetch failed:", repr(exc))
        return []

    entries = getattr(feed, "entries", []) or []
    if getattr(feed, "bozo", 0) and getattr(feed, "bozo_exception", None) and not entries and not quiet:
        print("RSS parse warning:", repr(feed.bozo_exception))

    items = []
    for e in entries[:limit]:
        published = None
        if getattr(e, "published_parsed", None):
            published = datetime(*e.published_parsed[:6], tzinfo=timezone.utc).isoformat()

        summary = _clean_html(getattr(e, "summary", "") or getattr(e, "description", ""))
        link = (getattr(e, "link", "") or "").strip()
        title = (getattr(e, "title", "") or "").strip()

        items.append(
            {
                "title": title,
                "link": link,
                "published": published,
                "summary": summary,
            }
        )
    return items
