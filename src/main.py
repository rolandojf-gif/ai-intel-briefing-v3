import yaml
from pathlib import Path

from src.fetch import fetch_rss
from src.render import render_index

def main():
    cfg = yaml.safe_load(Path("feeds/feeds.yaml").read_text(encoding="utf-8"))

    items_out = []
    for s in cfg["sources"]:
        if s.get("type") != "rss":
            continue
        for it in fetch_rss(s["url"], limit=20):
            if not it.get("title") or not it.get("link"):
                continue
            it["source"] = s["name"]
            it["tags"] = s.get("tags", [])
            items_out.append(it)

    seen = set()
    dedup = []
    for it in items_out:
        if it["link"] in seen:
            continue
        seen.add(it["link"])
        dedup.append(it)

    html = render_index(dedup[:120])

    Path("docs").mkdir(exist_ok=True)
    Path("docs/index.html").write_text(html, encoding="utf-8")

if __name__ == "__main__":
    main()
