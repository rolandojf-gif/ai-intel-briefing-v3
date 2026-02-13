import yaml
from pathlib import Path

from src.fetch import fetch_rss
from src.render import render_index
from src.score import score_item


def main():
    cfg = yaml.safe_load(
        Path("feeds/feeds.yaml").read_text(encoding="utf-8")
    )

    items_out = []

    # ---- Fetch + score ----
    for s in cfg["sources"]:
        if s.get("type") != "rss":
            continue

        for it in fetch_rss(s["url"], limit=12):
            if not it.get("title") or not it.get("link"):
                continue

            it["source"] = s["name"]
            it["feed_tags"] = s.get("tags", [])

            sc = score_item(
                it["title"],
                it.get("summary", ""),
                it["source"]
            )
            it.update(sc)

            items_out.append(it)

    # ---- Dedup por link ----
    seen = set()
    dedup = []
    for it in items_out:
        if it["link"] in seen:
            continue
        seen.add(it["link"])
        dedup.append(it)

    # ---- Orden por score ----
    dedup.sort(key=lambda x: x.get("score", 0), reverse=True)

    # ---- Umbral dinámico ----
    threshold = 45
    filtered = [x for x in dedup if x.get("score", 0) >= threshold]

    if len(filtered) < 20:
        threshold = 35
        filtered = [x for x in dedup if x.get("score", 0) >= threshold]

    dedup = filtered

    # ---- Caps por categoría ----
    caps = {
        "infra": 6,
        "invest": 6,
        "models": 4,
        "geopol": 4,
        "misc": 2
    }

    picked = []
    counts = {k: 0 for k in caps}

    for it in dedup:
        p = it.get("primary", "misc")
        if p not in caps:
            p = "misc"

        if counts[p] >= caps[p]:
            continue

        counts[p] += 1
        picked.append(it)

    # ---- Relleno hasta 20 si hace falta ----
    if len(picked) < 20:
        for it in dedup:
            if it in picked:
                continue
            picked.append(it)
            if len(picked) >= 20:
                break

    # ---- Render ----
    html = render_index(picked)

    Path("docs").mkdir(exist_ok=True)
    Path("docs/index.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
