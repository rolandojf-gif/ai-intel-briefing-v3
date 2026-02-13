import yaml
from pathlib import Path

from src.fetch import fetch_rss
from src.render import render_index
from src.score import score_item
from src.llm_rank import rank_batch


def chunk(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]


def merge_briefings(briefs: list[dict]) -> dict:
    """
    Si haces 2 chunks, tendrás 2 briefings.
    Aquí los fusionamos de forma simple:
    - concatenar y recortar a tamaño fijo.
    """
    out = {"signals": [], "risks": [], "watch": [], "entities_top": []}
    for b in briefs:
        for k in out.keys():
            out[k].extend(b.get(k, []))

    # dedup preservando orden
    def dedup(seq):
        seen = set()
        res = []
        for x in seq:
            if x in seen:
                continue
            seen.add(x)
            res.append(x)
        return res

    out["signals"] = dedup(out["signals"])[:5]
    out["risks"] = dedup(out["risks"])[:3]
    out["watch"] = dedup(out["watch"])[:3]
    out["entities_top"] = dedup(out["entities_top"])[:3]
    return out


def main():
    cfg = yaml.safe_load(Path("feeds/feeds.yaml").read_text(encoding="utf-8"))

    items = []

    # caps por fuente (ajusta nombres EXACTOS según feeds.yaml)
    per_source_cap = {
        "arXiv cs.AI": 2,
        "arXiv cs.LG": 2,
        "NVIDIA Blog (AI)": 2,  # si tu name es distinto, cámbialo
    }
    per_source_count = {}

    # 1) Ingesta RSS + heurístico
    for s in cfg["sources"]:
        if s.get("type") != "rss":
            continue

        limit = 12
        if s["name"].startswith("arXiv"):
            limit = 6

        for it in fetch_rss(s["url"], limit=limit):
            if not it.get("title") or not it.get("link"):
                continue

            it["source"] = s["name"]
            it["feed_tags"] = s.get("tags", [])

            # cap por fuente
            src = it["source"]
            cap = per_source_cap.get(src)
            if cap is not None:
                per_source_count[src] = per_source_count.get(src, 0)
                if per_source_count[src] >= cap:
                    continue
                per_source_count[src] += 1

            sc = score_item(it["title"], it.get("summary", ""), it["source"])
            it.update(sc)
            items.append(it)

    # 2) Dedup
    seen = set()
    dedup = []
    for it in items:
        link = it["link"]
        if link in seen:
            continue
        seen.add(link)
        dedup.append(it)

    # 3) Preselección
    dedup.sort(key=lambda x: x.get("score", 0), reverse=True)
    candidates = dedup[:30]

    # 4) Batch input
    batch_in = []
    for idx, it in enumerate(candidates, start=1):
        batch_in.append({
            "id": idx,
            "source": it.get("source", ""),
            "title": it.get("title", ""),
            "summary": it.get("summary", ""),
            "url": it.get("link", ""),
        })
        it["_rid"] = idx

    # 5) Gemini batch en 1-2 chunks
    results_map = {}
    briefings = []

    for part in chunk(batch_in, 15):
        try:
            out = rank_batch(part)
            results_map.update(out.get("map", {}))
            briefings.append(out.get("briefing", {}))
        except Exception:
            pass

    briefing = merge_briefings(briefings) if briefings else {
        "signals": [],
        "risks": [],
        "watch": [],
        "entities_top": []
    }

    # 6) Aplicar LLM + ordenar
    reranked = []
    for it in candidates:
        rid = it.get("_rid")
        llm = results_map.get(rid)

        if llm:
            it["score"] = int(llm.get("score", it.get("score", 0)))
            it["primary"] = llm.get("primary", it.get("primary", "misc"))
            it["tags"] = llm.get("tags", [])
            it["why"] = llm.get("why", "")
            it["entities"] = llm.get("entities", [])
        else:
            it["why"] = it.get("why") or (it.get("summary", "")[:160])

        reranked.append(it)

    reranked.sort(key=lambda x: x.get("score", 0), reverse=True)

    final_items = reranked[:10]
    from datetime import datetime
import json
import statistics

today = datetime.now().strftime("%Y-%m-%d")

# métricas simples
scores = [x.get("score", 0) for x in final_items]
score_avg = round(statistics.mean(scores), 1) if scores else 0

primary_dist = {}
for x in final_items:
    p = x.get("primary", "misc")
    primary_dist[p] = primary_dist.get(p, 0) + 1

entities_flat = []
for x in final_items:
    entities_flat.extend(x.get("entities", []))

entity_counts = {}
for e in entities_flat:
    entity_counts[e] = entity_counts.get(e, 0) + 1

top_entities = sorted(entity_counts.items(), key=lambda x: x[1], reverse=True)[:5]

daily_snapshot = {
    "date": today,
    "score_avg": score_avg,
    "primary_dist": primary_dist,
    "top_entities": top_entities,
    "briefing": briefing,
    "items": final_items,
}

Path("docs/data").mkdir(parents=True, exist_ok=True)
Path(f"docs/data/{today}.json").write_text(
    json.dumps(daily_snapshot, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

    html = render_index(final_items, briefing=briefing)

    Path("docs").mkdir(exist_ok=True)
    Path("docs/index.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
