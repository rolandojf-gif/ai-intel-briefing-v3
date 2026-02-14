from __future__ import annotations

import os
import re
import hashlib
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import requests

from src.fetch import fetch_rss

DEFAULT_X_RSS_MIRRORS = (
    "https://xcancel.com",
)

DEFAULT_TIMEOUT_SECONDS = 12
USER_AGENT = "ai-intel-briefing/1.0 (+https://github.com)"

_CACHE_LOADED = False
_CACHE_DIRTY = False
_CACHE_DATA: dict[str, list[dict]] = {}


def _rss_mirrors() -> list[str]:
    env_raw = (os.getenv("X_RSS_MIRRORS") or "").strip()
    mirrors: list[str] = []

    if env_raw:
        for part in env_raw.split(","):
            p = part.strip().rstrip("/")
            if p and p not in mirrors:
                mirrors.append(p)

    for mirror in DEFAULT_X_RSS_MIRRORS:
        if mirror not in mirrors:
            mirrors.append(mirror)
    return mirrors


def _env_flag(name: str, default: str = "0") -> bool:
    return (os.getenv(name, default) or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _cache_enabled() -> bool:
    return not _env_flag("X_CACHE_DISABLE", "0")


def _cache_file() -> Path:
    custom = (os.getenv("X_CACHE_FILE") or "").strip()
    if custom:
        return Path(custom)
    day = datetime.now().strftime("%Y-%m-%d")
    return Path("docs/data") / f"{day}.x_cache.json"


def _load_cache_once() -> None:
    global _CACHE_LOADED, _CACHE_DATA
    if _CACHE_LOADED:
        return

    _CACHE_LOADED = True
    if not _cache_enabled():
        return
    if _env_flag("X_CACHE_FORCE_REFRESH", "0"):
        return

    path = _cache_file()
    if not path.exists():
        return
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            parsed: dict[str, list[dict]] = {}
            for k, v in raw.items():
                if isinstance(k, str) and isinstance(v, list):
                    parsed[k] = [x for x in v if isinstance(x, dict)]
            _CACHE_DATA = parsed
    except Exception as exc:
        print("X cache read failed:", repr(exc))


def _cache_get(key: str) -> list[dict] | None:
    _load_cache_once()
    if not _cache_enabled():
        return None
    hit = _CACHE_DATA.get(key)
    if hit is None:
        return None
    return [dict(x) for x in hit]


def _cache_put(key: str, items: list[dict]) -> None:
    global _CACHE_DIRTY
    _load_cache_once()
    if not _cache_enabled():
        return
    _CACHE_DATA[key] = [dict(x) for x in items]
    _CACHE_DIRTY = True


def _save_cache() -> None:
    global _CACHE_DIRTY
    if not _CACHE_DIRTY or not _cache_enabled():
        return

    path = _cache_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_CACHE_DATA, ensure_ascii=False, indent=2), encoding="utf-8")
        _CACHE_DIRTY = False
    except Exception as exc:
        print("X cache write failed:", repr(exc))


def _timeout_seconds() -> int:
    raw = (os.getenv("X_RSS_TIMEOUT_SECONDS") or "").strip()
    if raw.isdigit():
        return max(5, min(int(raw), 60))
    return DEFAULT_TIMEOUT_SECONDS


def _safe_username(username: str) -> str:
    return (username or "").strip().lstrip("@")


def _looks_like_rss(text: str, content_type: str) -> bool:
    ct = (content_type or "").lower()
    if "xml" in ct or "rss" in ct:
        return True

    head = (text or "").lstrip().lower()[:160]
    return head.startswith("<?xml") or "<rss" in head


def _probe_rss(url: str) -> bool:
    try:
        resp = requests.get(
            url,
            timeout=_timeout_seconds(),
            headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8"},
        )
        if resp.status_code != 200:
            return False
        return _looks_like_rss(resp.text, resp.headers.get("content-type", ""))
    except requests.RequestException:
        return False


def _to_x_link(link: str) -> str:
    raw = (link or "").strip()
    if not raw:
        return raw

    try:
        parsed = urlsplit(raw)
    except ValueError:
        return raw

    if parsed.scheme not in {"http", "https"}:
        return raw

    netloc = (parsed.netloc or "").lower()
    if not netloc:
        return raw

    # Mirrors usually preserve /<user>/status/<id>.
    if any(netloc.endswith(mirror.split("://", 1)[-1].lower()) for mirror in _rss_mirrors()):
        return urlunsplit(("https", "x.com", parsed.path, "", ""))

    if netloc in {"twitter.com", "www.twitter.com", "x.com", "www.x.com", "mobile.twitter.com"}:
        return urlunsplit(("https", "x.com", parsed.path, "", ""))

    return raw


def _rewrite_links(items: list[dict]) -> list[dict]:
    for it in items:
        it["link"] = _to_x_link(it.get("link", ""))
    return items


def _is_placeholder_feed(items: list[dict]) -> bool:
    if not items:
        return False
    first_title = (items[0].get("title") or "").strip().lower()
    first_summary = (items[0].get("summary") or "").strip().lower()
    return ("rss reader not yet whitelist" in first_title) or ("rss reader not yet whitelist" in first_summary)


def _fetch_from_candidates(paths: list[str], limit: int, allow_empty_valid_feed: bool = True) -> list[dict]:
    for mirror in _rss_mirrors():
        for path in paths:
            url = f"{mirror}{path}"
            if not _probe_rss(url):
                continue

            items = fetch_rss(url, limit=limit, quiet=True)
            items = _rewrite_links(items)
            if _is_placeholder_feed(items):
                continue
            if items:
                return items
            # If RSS endpoint is healthy but temporarily empty, treat as valid.
            if allow_empty_valid_feed:
                return []
    return []


def _fetch_jina_profile_markdown(username: str) -> str:
    user = _safe_username(username)
    if not user:
        return ""
    url = f"https://r.jina.ai/http://x.com/{user}"
    try:
        resp = requests.get(url, timeout=max(15, _timeout_seconds()), headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        return resp.text or ""
    except requests.RequestException:
        return ""


def _extract_status_link(block: str, username: str, text_fallback: str) -> str:
    user = re.escape(_safe_username(username))
    m = re.search(rf"https://x\.com/{user}/status/\d+", block)
    if m:
        return m.group(0)
    m2 = re.search(rf"https://twitter\.com/{user}/status/\d+", block)
    if m2:
        return "https://x.com" + urlsplit(m2.group(0)).path
    digest = hashlib.sha1((text_fallback or "").encode("utf-8")).hexdigest()[:12]
    return f"https://x.com/{_safe_username(username)}?post={digest}"


def _clean_jina_text(lines: list[str]) -> str:
    keep: list[str] = []
    for raw in lines:
        line = (raw or "").strip()
        if not line:
            continue
        if line == "Pinned":
            continue
        if re.fullmatch(r"\d+:\d{2}(?::\d{2})?", line):
            continue
        if line.startswith("![Image"):
            continue
        if line.startswith("[![Image") and "](https://x.com/" in line:
            continue
        if line.startswith("Title:") or line.startswith("URL Source:") or line.startswith("Published Time:"):
            continue
        if line.startswith("Markdown Content:"):
            continue
        if line.endswith("posts") or line == "--------------":
            continue
        if re.fullmatch(r"[,;:.\-–—]+", line):
            continue
        keep.append(line)
    return " ".join(keep).strip()


def _extract_jina_posts(markdown: str, username: str, limit: int) -> list[dict]:
    user = _safe_username(username)
    if not markdown or not user:
        return []

    published = None
    for line in markdown.splitlines():
        if line.startswith("Published Time:"):
            published = line.split(":", 1)[1].strip()
            break

    lines = markdown.splitlines()
    start_re = re.compile(rf"^\[\!\[Image .*?\]\(https://x\.com/{re.escape(user)}\)\s*$")
    blocks: list[list[str]] = []
    current: list[str] | None = None

    for line in lines:
        if start_re.match((line or "").strip()):
            if current:
                blocks.append(current)
            current = []
            continue
        if current is not None:
            current.append(line)
    if current:
        blocks.append(current)

    out: list[dict] = []
    seen_texts: set[str] = set()
    for block_lines in blocks:
        text = _clean_jina_text(block_lines)
        if not text:
            continue
        key = text.lower()
        if key in seen_texts:
            continue
        seen_texts.add(key)

        block_text = "\n".join(block_lines)
        link = _extract_status_link(block_text, user, text)
        title = text if len(text) <= 160 else (text[:157] + "...")

        out.append(
            {
                "title": title,
                "summary": text,
                "link": link,
                "published": published,
            }
        )
        if len(out) >= limit:
            break
    return out


def _filter_by_keywords(items: list[dict], keywords: list[str]) -> list[dict]:
    if not keywords:
        return items
    kws = [k.lower() for k in keywords if k]
    out = []
    for it in items:
        hay = f"{it.get('title','')} {it.get('summary','')}".lower()
        if any(k in hay for k in kws):
            out.append(it)
    return out


def _dedup_items(items: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for it in items:
        key = (it.get("link") or it.get("title") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def _user_cache_key(username: str, limit: int, include_replies: bool, include_retweets: bool) -> str:
    user = _safe_username(username).lower()
    return f"user|{user}|{int(limit)}|r={int(include_replies)}|rt={int(include_retweets)}"


def _search_cache_key(query: str, limit: int) -> str:
    norm_q = " ".join((query or "").split()).lower()
    digest = hashlib.sha1(norm_q.encode("utf-8")).hexdigest()
    return f"search|{digest}|{int(limit)}"


def _parse_query_users_and_keywords(query: str) -> tuple[list[str], list[str]]:
    q = query or ""
    users = list(dict.fromkeys(re.findall(r"from:([A-Za-z0-9_]{1,30})", q, flags=re.IGNORECASE)))

    token_candidates = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", q)
    stop = {
        "from",
        "or",
        "and",
        "is",
        "retweet",
        "reply",
        "filter",
        "lang",
        "min",
        "since",
        "until",
    }
    keywords = []
    for tok in token_candidates:
        t = tok.lower()
        if t in stop:
            continue
        if any(t == u.lower() for u in users):
            continue
        keywords.append(t)
    keywords = list(dict.fromkeys(keywords))
    return users, keywords


def fetch_x_user(username: str, limit: int = 8, include_replies: bool = False, include_retweets: bool = False) -> list[dict]:
    user = _safe_username(username)
    if not user:
        return []

    n = max(1, min(int(limit), 100))
    key = _user_cache_key(user, n, include_replies, include_retweets)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    # Query path gives explicit control over replies/retweets.
    query_parts = [f"from:{user}"]
    if not include_replies:
        query_parts.append("-is:reply")
    if not include_retweets:
        query_parts.append("-is:retweet")
    q = " ".join(query_parts)
    q_encoded = quote(q, safe="")

    paths = [
        f"/search/rss?f=tweets&q={q_encoded}",
        f"/{user}/rss",
    ]
    rss_items = _fetch_from_candidates(paths, limit=n)
    if rss_items:
        _cache_put(key, rss_items)
        _save_cache()
        return rss_items

    # Fallback API-free scraping through r.jina.ai public renderer.
    md = _fetch_jina_profile_markdown(user)
    fallback_items = _extract_jina_posts(md, user, limit=n)
    _cache_put(key, fallback_items)
    _save_cache()
    return fallback_items


def fetch_x_search(query: str, limit: int = 10) -> list[dict]:
    q = (query or "").strip()
    if not q:
        return []

    n = max(1, min(int(limit), 100))
    key = _search_cache_key(q, n)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    q_encoded = quote(q, safe="")
    paths = [f"/search/rss?f=tweets&q={q_encoded}"]
    rss_items = _fetch_from_candidates(paths, limit=n)
    if rss_items:
        _cache_put(key, rss_items)
        _save_cache()
        return rss_items

    # Fallback: emulate search by pulling from explicit from: accounts in query.
    users, keywords = _parse_query_users_and_keywords(q)
    if not users:
        return []

    per_user = max(1, min(8, (n + len(users) - 1) // len(users)))
    pool: list[dict] = []
    for user in users:
        pool.extend(fetch_x_user(user, limit=per_user, include_replies=False, include_retweets=False))

    filtered = _filter_by_keywords(pool, keywords)
    if filtered:
        out = _dedup_items(filtered)[:n]
        _cache_put(key, out)
        _save_cache()
        return out
    out = _dedup_items(pool)[:n]
    _cache_put(key, out)
    _save_cache()
    return out
