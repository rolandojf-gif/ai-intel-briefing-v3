import yaml
from pathlib import Path

from src.fetch import fetch_rss
from src.render import render_index
from src.score import score_item  # heurístico (barato)
from src.llm_rank import rank_item  # Gemini (caro, pero poco)


def main():
    cfg = yaml.safe_load(Path("feeds/feeds.yaml").read_text(encoding="utf-8"))

    items = []

    # 1) Ingesta RSS + heurístico rápido
    for s in cfg["sources"]:
        if s.get("type") != "rss":
            continue

        for it in fetch_rss(s["url"], limit=12):
            if not it.get("title") or not it.get("link"):
                continue

            it["source"] = s["name"]
            it["feed_tags"] = s.get("tags", [])

            sc = score_item(it["title"], it.get("summary", ""), it["source"])
            it.update(sc)

            items.append(it)

    # 2) Dedup por link
    seen = set()
    dedup = []
    for it in items:
        link = it["link"]
        if link in seen:
            continue
        seen.add(link)
        dedup.append(it)

    # 3) Preselección: top N por heurístico (para no pagar por basura)
    dedup.sort(key=lambda x: x.get("score", 0), reverse=True)
    candidates = dedup[:40]  # aquí controlas el gasto

    # 4) Re-rank con Gemini (score “real”)
    reranked = []
    for it in candidates:
        try:
            llm = rank_item(
                title=it["title"],
                summary=it.get("summary", ""),
                source=it["source"],
                url=it["link"],
            )
            it["score"] = int(llm["score"])
            it["primary"] = llm["primary"]
            it["tags"] = llm.get("tags", [])
            it["why"] = llm.get("why", "")
            it["entities"] = llm.get("entities", [])
        except Exception:
            # si Gemini falla, al menos no rompas el pipeline
            it["why"] = it.get("summary", "")[:160]
        reranked.append(it)

    reranked.sort(key=lambda x: x.get("score", 0), reverse=True)

    # 5) Top 20 final
    final_items = reranked[:20]

    html = render_index(final_items)
    Path("docs").mkdir(exist_ok=True)
    Path("docs/index.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
