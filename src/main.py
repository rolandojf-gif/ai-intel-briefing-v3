import yaml
from pathlib import Path

from src.fetch import fetch_rss
from src.render import render_index
from src.score import score_item              # heurístico (gratis)
from src.llm_rank import rank_batch           # Gemini batch (1-2 llamadas)


def chunk(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]


def main():
    cfg = yaml.safe_load(Path("feeds/feeds.yaml").read_text(encoding="utf-8"))

    items = []

    # caps por fuente (anti-spam arXiv)
    per_source_cap = {
        "arXiv cs.AI": 2,
        "arXiv cs.LG": 2,   # opcional, quítalo si quieres más LG
        "NVIDIA Blog": 2,
    }
    per_source_count = {}

    # 1) Ingesta RSS + heurístico rápido
    for s in cfg["sources"]:
        if s.get("type") != "rss":
            continue

        # reduce volumen desde el origen para arXiv
        limit = 12
        if s["name"].startswith("arXiv"):
            limit = 6

        for it in fetch_rss(s["url"], limit=limit):
            if not it.get("title") or not it.get("link"):
                continue

            it["source"] = s["name"]
            it["feed_tags"] = s.get("tags", [])

            # aplicar cap por fuente
            src = it["source"]
            cap = per_source_cap.get(src)
            if cap is not None:
                per_source_count[src] = per_source_count.get(src, 0)
                if per_source_count[src] >= cap:
                    continue
                per_source_count[src] += 1

            # score provisional (heurístico)
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

    # 3) Preselección por heurístico (para no gastar en basura)
    dedup.sort(key=lambda x: x.get("score", 0), reverse=True)

    # Ajustes “equilibrio inteligente” en free tier:
    # - candidates 30 máximo
    # - chunk 15 => 2 llamadas como mucho
    candidates = dedup[:30]

    # 4) Preparar input para batch
    batch_in = []
    for idx, it in enumerate(candidates, start=1):
        batch_in.append({
            "id": idx,
            "source": it.get("source", ""),
            "title": it.get("title", ""),
            "summary": it.get("summary", ""),
            "url": it.get("link", ""),
        })
        it["_rid"] = idx  # id interno para mapear respuesta

    # 5) Re-rank con Gemini en 1-2 chunks
    results_map = {}
    for part in chunk(batch_in, 15):
        try:
            part_map = rank_batch(part)
            results_map.update(part_map)
        except Exception:
            # si Gemini falla, no rompemos el pipeline (queda heurístico)
            pass

    # Aplicar resultados LLM a candidates
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

    # 6) Orden final por score (LLM si disponible)
    reranked.sort(key=lambda x: x.get("score", 0), reverse=True)

    final_items = reranked[:10]

    html = render_index(final_items)

    Path("docs").mkdir(exist_ok=True)
    Path("docs/index.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
