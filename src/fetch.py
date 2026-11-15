from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
import html
import json
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import feedparser
import requests

USER_AGENT = "ai-intel-briefing/1.0 (+https://x.com)"
RSS_TIMEOUT_SECONDS = 15
RSS_RETRIES = 2
RSS_BACKOFF_SECONDS = 1.5
SUMMARY_MAX_CHARS = 800
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

IMAGE_CACHE_FILE = Path("docs/data/image_cache.json")
_MEM_IMAGE_CACHE: dict[str, str] = {}
_GN_RESOLVE_CACHE: dict[str, str] = {}
_GN_LOCK = threading.Lock()
_IMG_CACHE_LOCK = threading.Lock()


def clip_text(text: str, limit: int = SUMMARY_MAX_CHARS) -> str:
    """Recorta texto de ingest. Un summary de 60k chars hinchaba el JSON diario."""
    raw = re.sub(r"\s+", " ", (text or "").strip())
    if len(raw) <= limit:
        return raw
    if limit <= 1:
        return raw[:limit]
    return raw[: limit - 1].rstrip() + "…"


def _clean_html(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    no_tags = re.sub(r"<[^>]+>", " ", raw)
    # Hay feeds que codifican las entidades dos veces: tras el parser queda
    # "&quot;there&#039;s" como texto. Se decodifica, y se vuelven a quitar las
    # etiquetas por si lo que venia doblemente codificado era HTML.
    text = re.sub(r"<[^>]+>", " ", html.unescape(no_tags))
    return re.sub(r"\s+", " ", text).strip()


def is_google_news_url(url: str) -> bool:
    raw = (url or "").strip()
    if not raw:
        return False
    try:
        host = urlparse(raw).netloc.lower()
    except ValueError:
        return False
    return host == "news.google.com" or host.endswith(".news.google.com")


def google_news_article_id(url: str) -> str:
    """Token de `/articles/TOKEN` o `/read/TOKEN`."""
    try:
        parts = urlparse(url).path.strip("/").split("/")
    except ValueError:
        return ""
    if len(parts) >= 2 and parts[-2] in {"articles", "read"}:
        return parts[-1]
    return ""


def _decode_google_news_locally(article_id: str) -> str:
    """Formato legado: el protobuf del token lleva la URL del publisher.

    Los tokens post-2024 decodifican a un blob `AU_...` y necesitan batchexecute.
    """
    if not article_id:
        return ""
    padded = article_id + "=" * ((4 - len(article_id) % 4) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded).decode("latin1")
    except Exception:
        return ""

    prefix = b"\x08\x13\x22".decode("latin1")
    if decoded.startswith(prefix):
        decoded = decoded[len(prefix) :]
    suffix = b"\xd2\x01\x00".decode("latin1")
    if decoded.endswith(suffix):
        decoded = decoded[: -len(suffix)]
    if not decoded:
        return ""

    length = ord(decoded[0])
    if length >= 0x80:
        decoded = decoded[2 : length + 1]
    else:
        decoded = decoded[1 : length + 1]

    dest = decoded.strip()
    if dest.startswith("AU_"):
        return ""
    if dest.startswith(("http://", "https://")) and "news.google.com" not in dest:
        return dest
    return ""


def _parse_garturlres(body: str) -> str:
    m = re.search(r'\\"garturlres\\",\\"(https?://[^\\"]+)', body or "")
    if not m:
        m = re.search(r'"garturlres","(https?://[^"]+)"', body or "")
    if not m:
        return ""
    dest = m.group(1).replace("\\/", "/")
    if dest.startswith(("http://", "https://")) and "news.google.com" not in dest:
        return dest
    return ""


def _decode_google_news_via_google(article_id: str) -> str:
    """Lee firma+timestamp de la ficha y pide la URL real a batchexecute."""
    headers = {
        "User-Agent": BROWSER_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        page = requests.get(
            f"https://news.google.com/articles/{article_id}",
            headers=headers,
            timeout=8,
        )
        page.raise_for_status()
    except Exception:
        return ""

    sg_m = re.search(r'data-n-a-sg="([^"]+)"', page.text)
    ts_m = re.search(r'data-n-a-ts="([^"]+)"', page.text)
    if not sg_m or not ts_m:
        return ""

    inner = (
        '["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,'
        'null,null,null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],'
        f'"{article_id}",{ts_m.group(1)},"{sg_m.group(1)}"]'
    )
    envelope = json.dumps(["Fbv4je", inner, None, "generic"], separators=(",", ":"))
    try:
        resp = requests.post(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute?rpcids=Fbv4je",
            headers={
                "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
                "Referer": "https://news.google.com/",
                "User-Agent": BROWSER_UA,
            },
            data={"f.req": f"[[{envelope}]]"},
            timeout=8,
        )
        resp.raise_for_status()
    except Exception:
        return ""
    return _parse_garturlres(resp.text)


def resolve_google_news_url(url: str) -> str:
    """Convierte el wrapper de Google News en la URL del medio.

    Fallo suave: si Google no responde, se deja el wrapper para no tumbar el ingest.
    """
    raw = (url or "").strip()
    if not is_google_news_url(raw):
        return raw
    with _GN_LOCK:
        cached = _GN_RESOLVE_CACHE.get(raw)
    if cached:
        return cached
    article_id = google_news_article_id(raw)
    dest = ""
    if article_id:
        dest = _decode_google_news_locally(article_id) or _decode_google_news_via_google(article_id)
    resolved = dest or raw
    with _GN_LOCK:
        _GN_RESOLVE_CACHE[raw] = resolved
    return resolved


def resolve_items_google_news(items: list[dict], max_workers: int = 6) -> list[dict]:
    """Resuelve en paralelo las URLs de Google News solo para los items elegidos."""
    targets = [
        it for it in items
        if is_google_news_url((it.get("link") or it.get("url") or "").strip())
    ]
    if not targets:
        return items

    def _resolve_one(it: dict) -> None:
        raw = (it.get("link") or it.get("url") or "").strip()
        resolved = resolve_google_news_url(raw)
        if resolved and resolved != raw:
            it["link"] = resolved
            if "url" in it:
                it["url"] = resolved

    if len(targets) == 1:
        _resolve_one(targets[0])
    else:
        with ThreadPoolExecutor(max_workers=min(max_workers, len(targets))) as pool:
            list(pool.map(_resolve_one, targets))
    return items


def _load_image_cache() -> dict[str, str]:
    global _MEM_IMAGE_CACHE
    with _IMG_CACHE_LOCK:
        if _MEM_IMAGE_CACHE:
            return _MEM_IMAGE_CACHE
        if IMAGE_CACHE_FILE.exists():
            try:
                _MEM_IMAGE_CACHE = json.loads(IMAGE_CACHE_FILE.read_text(encoding="utf-8"))
            except Exception:
                _MEM_IMAGE_CACHE = {}
        return _MEM_IMAGE_CACHE


def _save_image_cache():
    with _IMG_CACHE_LOCK:
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
    if is_google_news_url(url):
        # El wrapper no tiene og:image util; resolver antes de scrapear.
        url = resolve_google_news_url(url)
        if not url or is_google_news_url(url):
            return ""

    # Un post de X no da og:image sin sesion: seria una peticion perdida.
    if urlparse(url).netloc.lower().removeprefix("www.") in {"x.com", "twitter.com"}:
        return ""

    cache = _load_image_cache()
    with _IMG_CACHE_LOCK:
        if url in cache:
            return cache[url]

    # No intentar en ciertos dominios que no tienen HTML tradicional o bloquean
    if any(d in url for d in ["github.com/deepseek-ai", "hnrss.org", "arxiv.org/abs"]):
        with _IMG_CACHE_LOCK:
            cache[url] = ""
        return ""

    headers = {
        "User-Agent": BROWSER_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=6)
        if resp.status_code == 200:
            text = resp.text[:120000]  # Primeros 120KB contienen todo el <head>
            og_match = re.search(
                r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image|twitter:image:src)["\'][^>]+content=["\']([^"\']+)["\']',
                text,
                flags=re.IGNORECASE,
            )
            if not og_match:
                og_match = re.search(
                    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\']',
                    text,
                    flags=re.IGNORECASE,
                )

            if og_match:
                img_url = html.unescape(og_match.group(1).strip())
                if img_url.startswith("//"):
                    img_url = "https:" + img_url
                elif img_url.startswith("/"):
                    img_url = urljoin(url, img_url)

                if img_url.startswith(("http://", "https://")):
                    with _IMG_CACHE_LOCK:
                        cache[url] = img_url
                    _save_image_cache()
                    return img_url
    except Exception:
        pass

    with _IMG_CACHE_LOCK:
        cache[url] = ""
    _save_image_cache()
    return ""


def enrich_items_with_images(items: list[dict]) -> list[dict]:
    """Rellena image_url en cada item usando OpenGraph si el feed RSS no incluyo imagen."""
    pending: list[tuple[dict, str]] = []
    for it in items:
        if not (it.get("image_url") or "").strip():
            target_url = (it.get("url") or it.get("link") or "").strip()
            if target_url:
                pending.append((it, target_url))
    if not pending:
        return items
    if len(pending) == 1:
        it, target_url = pending[0]
        it["image_url"] = fetch_og_image(target_url)
        return items
    with ThreadPoolExecutor(max_workers=min(6, len(pending))) as pool:
        results = list(pool.map(lambda pair: fetch_og_image(pair[1]), pending))
    for (it, _), img_url in zip(pending, results):
        it["image_url"] = img_url
    return items


def _extract_aa_date(fragment: str) -> str | None:
    """Extrae una fecha real del fragmento HTML de Artificial Analysis, o None."""
    if not fragment:
        return None
    iso_m = re.search(r"\b(202[4-9]-\d{2}-\d{2})(?:T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?\b", fragment)
    if iso_m:
        raw_iso = iso_m.group(0)
        if len(raw_iso) == 10:
            return f"{raw_iso}T00:00:00+00:00"
        return raw_iso.replace("Z", "+00:00")
    text_m = re.search(
        r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+202[4-9])\b",
        fragment,
        flags=re.IGNORECASE,
    )
    if text_m:
        cleaned = text_m.group(1).replace(",", "")
        for fmt in ("%b %d %Y", "%B %d %Y"):
            try:
                dt = datetime.strptime(cleaned, fmt).replace(tzinfo=timezone.utc)
                return dt.isoformat()
            except ValueError:
                continue
    return None


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

    article_matches = re.finditer(r'<a[^>]+href=["\'](/articles/[^"\']+)["\'][^>]*>(.*?)</a>', html_text, re.DOTALL)
    items = []
    seen = set()
    for match in article_matches:
        rel_link, content = match.group(1), match.group(2)
        full_link = f"https://artificialanalysis.ai{rel_link}"
        if full_link in seen:
            continue
        seen.add(full_link)

        raw_text = re.sub(r"<[^>]+>", " ", content)
        clean = re.sub(r"\s+", " ", raw_text).strip()
        if not clean or len(clean) < 10:
            continue

        title = clean
        summary = ""
        if " - " in clean:
            parts = clean.split(" - ", 1)
            title = parts[0].strip()
            summary = parts[1].strip()

        # Nunca falsificar la fecha con datetime.now(): solo usar fecha real si viene en el HTML.
        window = html_text[max(0, match.start() - 160) : min(len(html_text), match.end() + 260)]
        published = _extract_aa_date(content) or _extract_aa_date(window)

        items.append({
            "title": title,
            "link": full_link,
            "published": published,
            "summary": clip_text(summary or title),
            # La imagen se resuelve despues, solo para lo que se publica.
            "image_url": "",
        })
        if len(items) >= limit:
            break

    return items


def _extract_image_url(e) -> str:
    """Extrae URL de imagen de un item RSS (media:content, media:thumbnail, enclosures, img tags)."""
    media_content = getattr(e, "media_content", []) or []
    for m in media_content:
        if isinstance(m, dict) and m.get("url"):
            url = html.unescape(m["url"].strip())
            medium = str(m.get("medium", "") or m.get("type", "")).lower()
            if "image" in medium or url.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif")) or not medium:
                if url.startswith(("http://", "https://")):
                    return url

    media_thumbnail = getattr(e, "media_thumbnail", []) or []
    for m in media_thumbnail:
        if isinstance(m, dict) and m.get("url"):
            url = html.unescape(m["url"].strip())
            if url.startswith(("http://", "https://")):
                return url

    enclosures = getattr(e, "enclosures", []) or []
    for enc in enclosures:
        if isinstance(enc, dict) and enc.get("href"):
            mtype = str(enc.get("type", "")).lower()
            href = html.unescape(enc["href"].strip())
            if "image" in mtype or href.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif")):
                if href.startswith(("http://", "https://")):
                    return href

    links = getattr(e, "links", []) or []
    for lk in links:
        if isinstance(lk, dict) and lk.get("type", "").startswith("image/") and lk.get("href"):
            url = html.unescape(lk["href"].strip())
            if url.startswith(("http://", "https://")):
                return url

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
                # Reintentar al instante contra un 429 solo empeora el bloqueo.
                time.sleep(RSS_BACKOFF_SECONDS * (attempt + 1))
                continue

    raise RuntimeError(f"RSS fetch failed for {url}: {last_error!r}")


def fetch_rss(url: str, limit: int = 30, quiet: bool = False, resolve_gn: bool = True):
    """Lee un feed. La imagen solo sale del propio feed (media, enclosure, <img>).

    El og:image de cada articulo NO se pide aqui: se pedia para las ~250 entradas
    de cada run y solo se publican unas 13. Lo resuelve enrich_items_with_images()
    sobre los items que sobreviven al filtro.
    Cuando resolve_gn=False, las URLs de Google News se dejan sin decodificar
    para resolverlas en bloque solo tras aplicar freshness/cap por fuente.
    """
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
        # Atom puede traer solo <updated> (los releases de GitHub, por ejemplo).
        # Sin este fallback el item quedaba sin fecha: nunca caducaba en el radar
        # y NEXUS lo descartaba siempre por no poder afirmar que fuera nuevo.
        published = None
        parsed = getattr(e, "published_parsed", None) or getattr(e, "updated_parsed", None)
        if parsed:
            published = datetime(*parsed[:6], tzinfo=timezone.utc).isoformat()

        raw_summary = getattr(e, "summary", "") or getattr(e, "description", "")
        summary = clip_text(_clean_html(raw_summary))
        raw_link = (getattr(e, "link", "") or "").strip()
        link = resolve_google_news_url(raw_link) if resolve_gn else raw_link
        title = html.unescape((getattr(e, "title", "") or "").strip())
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
