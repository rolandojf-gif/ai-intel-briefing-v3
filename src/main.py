# src/main.py
import yaml
from pathlib import Path
from datetime import datetime
import json
import statistics
import re

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
    out["entities_top"] = dedup(out["entities_top"])[:5]

    return out


KNOWN_ENTITIES = [
    "OpenAI", "NVIDIA", "Anthropic", "Google", "DeepMind", "Microsoft", "Meta", "Apple",
    "Amazon", "AWS", "Azure", "TSMC", "AMD", "Intel", "Arm", "Tesla",
    "Cerebras", "Groq", "Mistral", "Hugging Face", "Stability AI",
    "ByteDance", "Alibaba", "Tencent", "Samsung", "Qualcomm",
]


def extract_entities_from_title(title: str) -> list[str]:
    t = title or ""
    hits = []

    # 1) conocidos
    for e in KNOWN_ENTITIES:
        if re.search(r"\b" + re.escape(e) + r"\b", t, flags=re.IGNORECASE):
            hits.append(e)

    # 2) acrónimos (2-6 mayúsculas/números)
    for m in re.findall(r"\b[A-Z][A-Z0-9]{1,5}\b", t):
        if m not in hits and m not in {"AI", "ML", "LLM"}:
            hits.append(m)

    # 3) secuencias Capitalizadas tipo "San Francisco", "United States"
    # ojo: heurístico, no NER real
    candidates = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b", t)
    stop = {"The", "A", "An", "And", "Of", "In", "On", "For", "With", "New"}
    for c in candidates:
        if c in stop:
            continue
        if len(c) < 3:
            continue
        if c not in hits:
            hits.append(c)

    # limpia y limita
    out = []
    seen = set()
    for x in hits:
        x2 = x.strip()
        if not x2 or x2.lower() in seen:
            continue
        seen.add(x2.lower())
        out.append(x2)
    return out[:8]


def main():
    cfg = yaml.safe_load(Path("feeds/feeds.yaml").read_text(encoding="utf-8"))

    items = []

    per_source_cap = {
        "arXiv cs.AI": 2,
        "arXiv cs.LG": 2,
        "NVIDIA Blog": 2,
    }
    per_source_count = {}

    # Fecha del run (para cache + snapshot)
    today = datetime.now().strftime("%Y-%m-%d")
    data_dir = Path("docs/data")
    data_dir.mkdir(parents=True, exist_ok=True)

    llm_done = data_dir / f"{today}.llm_done"
    llm_cache = data_dir / f"{today}.llm_cache.json"

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

            # estándar
            it["url"] = it.get("link", "")

            items.append(it)

    # 2️⃣ Dedup
    seen = set()
    deduped = []
    for it in items:
        if it["link"] in seen:
            continue
        seen.add(it["link"])
        deduped.append(it)

    # 3️⃣ Preselección heurística
    deduped.sort(key=lambda x: x.get("score", 0), reverse=True)
    candidates = deduped[:30]

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

    # 4.5️⃣ LLM cache: si hay cache, úsalo. Si no, intenta Gemini 1 vez/día.
    if llm_cache.exists():
        try:
            cached = json.loads(llm_cache.read_text(encoding="utf-8"))
            results_map = cached.get("results_map", {}) or {}
            briefings = cached.get("briefings", []) or []
            print("Gemini cache HIT:", llm_cache.name)
        except Exception as e:
            print("Gemini cache read FAILED:", repr(e))

    if not results_map and not briefings:
        if llm_done.exists():
            print("Skipping Gemini: llm_done present (already attempted today).")
        else:
            for part in chunk(batch_in, 15):
                try:
                    out = rank_batch(part)
                    results_map.update(out.get("map", {}))
                    b = out.get("briefing", {}) or {}
                    briefings.append(b)
                except Exception as e:
                    print("GEMINI rank_batch FAILED:", repr(e))
                    if "429" in repr(e) or "RESOURCE_EXHAUSTED" in repr(e):
                        break

            # marca “intentado hoy” (para no quemar cuota en reruns)
            llm_done.write_text(datetime.now().isoformat(), encoding="utf-8")

            # guarda cache si hay algo útil
            if results_map or any((b.get("signals") or b.get("risks") or b.get("watch") or b.get("entities_top")) for b in briefings):
                llm_cache.write_text(
                    json.dumps({"results_map": results_map, "briefings": briefings}, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                print("Gemini cache WRITTEN:", llm_cache.name)

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

    # 5.1️⃣ Si no hay entidades (sin LLM), extrae heurísticamente desde títulos
    for it in final_items:
        ents = it.get("entities") or []
        if not ents:
            it["entities"] = extract_entities_from_title(it.get("title", ""))

    # 5.5️⃣ Métricas daily (para snapshot)
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
            if isinstance(e, str) and e.strip():
                e2 = e.strip()
                entity_counts[e2] = entity_counts.get(e2, 0) + 1

    top_entities = sorted(entity_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    top_entities_list = [e for e, _ in top_entities]

    # 5.6️⃣ Briefing fallback DECENTE si no hay LLM briefing
    if not (briefing.get("signals") or briefing.get("risks") or briefing.get("watch") or briefing.get("entities_top")):
        top_cats = sorted(primary_dist.items(), key=lambda x: x[1], reverse=True)[:3]
        cat_txt = ", ".join([f"{c} ({n}/{len(final_items)})" for c, n in top_cats]) if top_cats else "misc"

        # riesgo simple: concentración
        max_cat = top_cats[0][1] if top_cats else 0
        concentration = max_cat / max(1, len(final_items))
        risk = "Concentración alta en una categoría (posible mono-tema)." if concentration >= 0.55 else "Diversidad razonable de categorías."

        # watch: top 2 entidades + categoría dominante
        watch = []
        if top_entities_list:
            watch.append(f"Seguir: {', '.join(top_entities_list[:3])}.")
        if top_cats:
            watch.append(f"Vigilar si '{top_cats[0][0]}' sigue dominando mañana.")
        if not watch:
            watch = ["Sube más histórico para ver tendencias reales."]

        briefing = {
            "signals": [
                f"Top categorías (hoy): {cat_txt}.",
                f"Top entidades (hoy): {', '.join(top_entities_list) if top_entities_list else 'n/a'}.",
            ],
            "risks": [risk, "LLM no disponible (cuota/429): briefing en modo heurístico."],
            "watch": watch[:3],
            "entities_top": top_entities_list[:5],
        }

    # 6️⃣ Snapshot JSON
    top_entities_json = [{"entity": e, "count": c} for e, c in top_entities]

    daily_snapshot = {
        "date": today,
        "score_avg": score_avg,
        "primary_dist": primary_dist,
        "top_entities": top_entities_json,
        "briefing": briefing,
        "items": final_items,
    }

    Path(f"docs/data/{today}.json").write_text(
        json.dumps(daily_snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # 7️⃣ Render HTML
    html = render_index(final_items, briefing=briefing)
    Path("docs").mkdir(exist_ok=True)
    Path("docs/index.html").write_text(html, encoding="utf-8")

    # 8️⃣ Weekly radar
    try:
        from src.weekly import main as weekly_main
        weekly_main()
        print("WEEKLY OK -> docs/weekly.html")
    except Exception:
        import traceback
        print("WEEKLY FAILED (traceback):")
        traceback.print_exc()


if __name__ == "__main__":
    main()
