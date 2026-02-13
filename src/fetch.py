import feedparser
from datetime import datetime, timezone

def fetch_rss(url: str, limit: int = 30):
    feed = feedparser.parse(url)
    items = []
    for e in feed.entries[:limit]:
        published = None
        if getattr(e, "published_parsed", None):
            published = datetime(*e.published_parsed[:6], tzinfo=timezone.utc).isoformat()
        items.append({
            "title": getattr(e, "title", "").strip(),
            "link": getattr(e, "link", "").strip(),
            "published": published,
            "summary": getattr(e, "summary", "").strip(),
        })
    return items
