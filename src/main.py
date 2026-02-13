import yaml
from pathlib import Path
from datetime import datetime
import json
import statistics

from src.fetch import fetch_rss
from src.render import render_index
from src.score import score_item
from src.llm_rank import rank_batch


def chunk(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def merge_briefings(briefs: list[dict]) -> dict:
    out = {"signals": [], "risks": [], "watch": [], "entities_top": []}

    for b in briefs:
        for k in out.keys():
            out[k].extend(b.get(k, []))

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

    per_source_cap = {
        "arXiv cs.AI": 2,
        "arXiv cs.LG": 2,
        "NVIDIA Blog": 2,
    }

    per_source_count = {}

    # 1️⃣ Ingesta RSS
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

    # 2️⃣ Dedup
    seen = set()
    dedup = []
    for it in items:
        if it["link"] in seen:
            continue
        seen.add(it["link"])
        dedup.append(it)

    # 3️⃣ Preselección heurística
    dedup.sort(key=lambda x: x.get("score", 0), reverse=True)
    candidates = dedup[:30]

    # 4️⃣ Preparar batch Gemini
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

    results_map = {}
    briefings = []

    for part in chunk(batch_in, 15):
        try:
            out = rank_batch(part)
            results_map.update(out.get("map", {}))
            briefings.append(out.get("briefing", {}))
        except Exception:
            # si Gemini falla en un chunk, no tires el pipeline entero
            pass

    briefing = merge_briefings(briefings) if briefings else {
        "signals": [],
        "risks": [],
        "watch": [],
        "entities_top": []
    }

    # 5️⃣ Aplicar resultados LLM
    reranked = []
    for it in candidates:
        rid = it.get("_rid")
        llm = results_map.get(rid)

        # estandariza url (para weekly/clusters)
        it["url"] = it.get("link", "")

        if llm:
            it["score"] = int(llm.get("score", it.get("score", 0)))
            it["primary"] = llm.get("primary", it.get("primary", "misc"))
            it["tags"] = llm.get("tags", [])
            it["why"] = llm.get("why", "")
            it["entities"] = llm.get("entities", [])
        else:
            it["primary"] = it.get("primary", "misc")
            it["tags"] = it.get("tags", [])
            it["entities"] = it.get("entities", [])
            it["why"] = it.get("summary", "")[:160]

        reranked.append(it)

    reranked.sort(key=lambda x: x.get("score", 0), reverse=True)
    final_items = reranked[:15]

    # 5.5️⃣ Métricas daily
    today = datetime.now().strftime("%Y-%m-%d")

    scores = [
        it.get("score", 0)
        for it in final_items
        if isinstance(it.get("score", 0), (int, float))
    ]
    score_avg = round(statistics.mean(scores), 2) if scores else 0

    primary_dist = {}
    for it in final_items:
        p = it.get("primary", "misc")
        primary_dist[p] = primary_dist.get(p, 0) + 1

    entity_counts = {}
    for it in final_items:
        for e in (it.get("entities") or []):
            if not isinstance(e, str):
                continue
            e2 = e.strip()
            if not e2:
                continue
            entity_counts[e2] = entity_counts.get(e2, 0) + 1

    # 6️⃣ Snapshot JSON
    top_entities = sorted(entity_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    top_entities = [{"entity": e, "count": c} for e, c in top_entities]

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

    # 7️⃣ Render HTML
    html = render_index(final_items, briefing=briefing)

    Path("docs").mkdir(exist_ok=True)
    Path("docs/index.html").write_text(html, encoding="utf-8")

    # 8️⃣ Weekly radar (direct call)
from src.weekly import main as weekly_main
weekly_main()



if __name__ == "__main__":
    main()
