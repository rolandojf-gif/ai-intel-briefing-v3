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


import html
import json
from pathlib import Path

IMAGE_CACHE_FILE = Path("docs/data/image_cache.json")
_MEM_IMAGE_CACHE: dict[str, str] = {}


def _load_image_cache() -> dict[str, str]:
    global _MEM_IMAGE_CACHE
    if _MEM_IMAGE_CACHE:
        return _MEM_IMAGE_CACHE
    if IMAGE_CACHE_FILE.exists():
        try:
            _MEM_IMAGE_CACHE = json.loads(IMAGE_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            _MEM_IMAGE_CACHE = {}
    return _MEM_IMAGE_CACHE


def _save_image_cache():
    if not _MEM_IMAGE_CACHE:
        return
    IMAGE_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        IMAGE_CACHE_FILE.write_text(json.dumps(_MEM_IMAGE_CACHE, indent=2), encoding="utf-8")
    except Exception:
        pass


def fetch_og_image(url: str) -> str:
    """Extrae la imagen OpenGraph (og:image / twitter:image) del HTML de una noticia con cache."""
    if not url or not url.startswith(("http://", "https://")):
        return ""
    
    cache = _load_image_cache()
    if url in cache:
        return cache[url]

    # No intentar en ciertos dominios que no tienen HTML tradicional o bloquean
    if any(d in url for d in ["github.com/deepseek-ai", "hnrss.org", "arxiv.org/abs"]):
        cache[url] = ""
        return ""

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=6)
        if resp.status_code == 200:
            text = resp.text[:120000] # Primeros 120KB contienen todo el <head>
            og_match = re.search(r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image|twitter:image:src)["\'][^>]+content=["\']([^"\']+)["\']', text, flags=re.IGNORECASE)
            if not og_match:
                og_match = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\']', text, flags=re.IGNORECASE)
            
            if og_match:
                img_url = html.unescape(og_match.group(1).strip())
                if img_url.startswith("//"):
                    img_url = "https:" + img_url
                elif img_url.startswith("/"):
                    from urllib.parse import urljoin
                    img_url = urljoin(url, img_url)

                if img_url.startswith(("http://", "https://")):
                    cache[url] = img_url
                    _save_image_cache()
                    return img_url
    except Exception:
        pass

    cache[url] = ""
    _save_image_cache()
    return ""


def enrich_items_with_images(items: list[dict]) -> list[dict]:
    """Rellena image_url en cada item usando OpenGraph si el feed RSS no incluyo imagen."""
    for it in items:
        if not (it.get("image_url") or "").strip():
            target_url = (it.get("url") or it.get("link") or "").strip()
            if target_url:
                it["image_url"] = fetch_og_image(target_url)
    return items


def fetch_artificial_analysis(limit: int = 10, quiet: bool = False) -> list[dict]:
    """Scraper para articulos y benchmarks de Artificial Analysis."""
    url = "https://artificialanalysis.ai/articles"
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    try:
        resp = requests.get(url, headers=headers, timeout=RSS_TIMEOUT_SECONDS)
        resp.raise_for_status()
        html_text = resp.text
    except Exception as exc:
        if not quiet:
            print("Artificial Analysis fetch failed:", repr(exc))
        return []

    # Extraer enlaces a artículos
    article_blocks = re.findall(r'<a[^>]+href=["\'](/articles/[^"\']+)["\'][^>]*>(.*?)</a>', html_text, re.DOTALL)
    items = []
    seen = set()
    for rel_link, content in article_blocks:
        full_link = f"https://artificialanalysis.ai{rel_link}"
        if full_link in seen:
            continue
        seen.add(full_link)

        # Extraer texto de titulo
        raw_text = re.sub(r'<[^>]+>', ' ', content)
        clean = re.sub(r'\s+', ' ', raw_text).strip()
        if not clean or len(clean) < 10:
            continue

        title = clean
        summary = ""
        # Si tiene fecha u otros datos en el texto, dividir
        if " - " in clean:
            parts = clean.split(" - ", 1)
            title = parts[0].strip()
            summary = parts[1].strip()

        img_url = fetch_og_image(full_link)

        items.append({
            "title": title,
            "link": full_link,
            "published": datetime.now(timezone.utc).isoformat(),
            "summary": summary or title,
            "image_url": img_url,
        })
        if len(items) >= limit:
            break

    return items


def _extract_image_url(e) -> str:
    """Extrae URL de imagen de un item RSS (media:content, media:thumbnail, enclosures, img tags)."""
    # 1. Media content
    media_content = getattr(e, "media_content", []) or []
    for m in media_content:
        if isinstance(m, dict) and m.get("url"):
            url = html.unescape(m["url"].strip())
            medium = str(m.get("medium", "") or m.get("type", "")).lower()
            if "image" in medium or url.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif")) or not medium:
                if url.startswith(("http://", "https://")):
                    return url

    # 2. Media thumbnail
    media_thumbnail = getattr(e, "media_thumbnail", []) or []
    for m in media_thumbnail:
        if isinstance(m, dict) and m.get("url"):
            url = html.unescape(m["url"].strip())
            if url.startswith(("http://", "https://")):
                return url

    # 3. Enclosures
    enclosures = getattr(e, "enclosures", []) or []
    for enc in enclosures:
        if isinstance(enc, dict) and enc.get("href"):
            mtype = str(enc.get("type", "")).lower()
            href = html.unescape(enc["href"].strip())
            if "image" in mtype or href.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif")):
                if href.startswith(("http://", "https://")):
                    return href

    # 4. Links con rel=enclosure
    links = getattr(e, "links", []) or []
    for lk in links:
        if isinstance(lk, dict) and lk.get("type", "").startswith("image/") and lk.get("href"):
            url = html.unescape(lk["href"].strip())
            if url.startswith(("http://", "https://")):
                return url

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
            img_clean = html.unescape(img_url.strip())
            img_l = img_clean.lower()
            # Descartar píxeles de tracking, avatares o iconos miniatura
            if any(bad in img_l for bad in ["1x1", "pixel", "feedburner", "tracker", "avatar", "emoji", "icon", "spacer", "stat?"]):
                continue
            return img_clean

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
        if not image_url and link:
            # Intentar resolver OpenGraph si es un link valido
            image_url = fetch_og_image(link)

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
