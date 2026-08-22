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


def _extract_image_url(e) -> str:
    """Extrae URL de imagen de un item RSS (media:content, media:thumbnail, enclosures, img tags)."""
    # 1. Media content
    media_content = getattr(e, "media_content", []) or []
    for m in media_content:
        if isinstance(m, dict) and m.get("url"):
            url = m["url"].strip()
            medium = str(m.get("medium", "") or m.get("type", "")).lower()
            if "image" in medium or url.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif")) or not medium:
                return url

    # 2. Media thumbnail
    media_thumbnail = getattr(e, "media_thumbnail", []) or []
    for m in media_thumbnail:
        if isinstance(m, dict) and m.get("url"):
            return m["url"].strip()

    # 3. Enclosures
    enclosures = getattr(e, "enclosures", []) or []
    for enc in enclosures:
        if isinstance(enc, dict) and enc.get("href"):
            mtype = str(enc.get("type", "")).lower()
            href = enc["href"].strip()
            if "image" in mtype or href.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif")):
                return href

    # 4. Links con rel=enclosure
    links = getattr(e, "links", []) or []
    for lk in links:
        if isinstance(lk, dict) and lk.get("type", "").startswith("image/") and lk.get("href"):
            return lk["href"].strip()

    # 5. Raw HTML en content o summary/description
    html_sources = []
    if hasattr(e, "content") and isinstance(e.content, list):
        for c in e.content:
            if isinstance(c, dict) and c.get("value"):
                html_sources.append(c["value"])
    html_sources.append(getattr(e, "summary", "") or "")
    html_sources.append(getattr(e, "description", "") or "")

    for raw_html in html_sources:
        if not raw_html or not isinstance(raw_html, str):
            continue
        img_matches = re.findall(r'<img[^>]+src=["\'](https?://[^"\'>\s]+)["\']', raw_html, flags=re.IGNORECASE)
        for img_url in img_matches:
            img_l = img_url.lower()
            # Descartar píxeles de tracking, avatares o iconos miniatura
            if any(bad in img_l for bad in ["1x1", "pixel", "feedburner", "tracker", "avatar", "emoji", "icon", "spacer"]):
                continue
            return img_url.strip()

    return ""


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

        raw_summary = getattr(e, "summary", "") or getattr(e, "description", "")
        summary = _clean_html(raw_summary)
        link = (getattr(e, "link", "") or "").strip()
        title = (getattr(e, "title", "") or "").strip()
        image_url = _extract_image_url(e)

        items.append(
            {
                "title": title,
                "link": link,
                "published": published,
                "summary": summary,
                "image_url": image_url,
            }
        )
    return items
