# src/main.py
import os
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


CATEGORY_LABELS = {
    "models": "Modelos",
    "infra": "Infraestructura/HW",
    "policy": "Política/Regulación",
    "security": "Seguridad",
    "research": "Research",
    "products": "Producto",
    "chips": "Chips",
    "robotics": "Robótica",
    "compute": "Compute",
    "misc": "Misc",
}

KNOWN_ENTITIES = [
    "OpenAI", "NVIDIA", "Anthropic", "Google", "DeepMind", "Microsoft", "Meta", "Apple",
    "Amazon", "AWS", "Azure", "TSMC", "AMD", "Intel", "Arm", "Tesla",
    "Cerebras", "Groq", "Mistral", "Hugging Face", "Stability AI",
    "ByteDance", "Alibaba", "Tencent", "Samsung", "Qualcomm",
]

ENTITY_ALIASES = {"UK": "Reino Unido", "US": "EEUU", "USA": "EEUU", "EU": "UE"}

STOP_ENTITIES = {"AI", "ML", "LLM", "RAG", "RL", "GPU", "CPU", "API", "SDK", "OSS", "PDF", "HTML"}
ALLOW_ACRONYMS = {"AWS", "TSMC", "AMD", "ARM", "NVIDIA", "GPT", "CUDA", "EEUU", "UE"}


def normalize_entity(e: str) -> str:
    e = (e or "").strip()
    e = re.sub(r"\s+", " ", e)
    if e in ENTITY_ALIASES:
        return ENTITY_ALIASES[e]
    return e


def is_bad_entity(e: str) -> bool:
    if not e:
        return True
    e2 = e.strip()
    if e2 in STOP_ENTITIES:
        return True
    if len(e2) <= 2 and e2.isupper() and e2 not in ALLOW_ACRONYMS and e2 not in ENTITY_ALIASES:
        return True
    if len(e2) < 3:
        return True
    return False


def extract_entities_from_title(title: str) -> list[str]:
    t = title or ""
    hits = []

    for e in KNOWN_ENTITIES:
        if re.search(r"\b" + re.escape(e) + r"\b", t, flags=re.IGNORECASE):
            hits.append(e)

    for m in re.findall(r"\b[A-Z][A-Z0-9]{1,6}\b", t):
        m2 = normalize_entity(m)
        if is_bad_entity(m2):
            continue
        if m2 not in hits:
            hits.append(m2)

    candidates = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b", t)
    stop_words = {"The", "A", "An", "And", "Of", "In", "On", "For", "With", "New"}
    for c in candidates:
        c2 = normalize_entity(c.strip())
        if c2 in stop_words:
            continue
        if is_bad_entity(c2):
            continue
        if c2 not in hits:
            hits.append(c2)

    out = []
    seen = set()
    for x in hits:
        key = x.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(x)
    return out[:8]


def forced_gemini() -> bool:
    return (os.getenv("FORCE_GEMINI", "").strip() == "1")


def should_use_gemini_today() -> bool:
    if forced_gemini():
        return True
    event = (os.getenv("GITHUB_EVENT_NAME") or "").strip()
    return event == "schedule"


def main():
    cfg = yaml.safe_load(Path("feeds/feeds.yaml").read_text(encoding="utf-8"))

    per_source_cap = {"arXiv cs.AI": 2, "arXiv cs.LG": 2, "NVIDIA Blog": 2}
    per_source_count = {}

    today = datetime.now().strftime("%Y-%m-%d")
    data_dir = Path("docs/data")
    data_dir.mkdir(parents=True, exist_ok=True)

    llm_done = data_dir / f"{today}.llm_done"
    llm_cache = data_dir / f"{today}.llm_cache.json"

    items = []

    # 1) RSS ingest
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
            it["url"] = it.get("link", "")

            items.append(it)

    # 2) Dedup
    seen = set()
    deduped = []
    for it in items:
        if it["link"] in seen:
            continue
        seen.add(it["link"])
        deduped.append(it)

    # 3) Preselect
    deduped.sort(key=lambda x: x.get("score", 0), reverse=True)
    candidates = deduped[:30]

    # 4) LLM payload: top 15 (1 llamada)
    llm_payload = []
    for idx, it in enumerate(candidates[:15], start=1):
        llm_payload.append({
            "id": idx,
            "source": it.get("source", ""),
            "title": it.get("title", ""),
            "summary": it.get("summary", ""),
            "url": it.get("link", ""),
        })
        it["_rid"] = idx

    results_map = {}
    briefings = []

    # 4.5) Cache hit
    if llm_cache.exists():
        try:
            cached = json.loads(llm_cache.read_text(encoding="utf-8"))
            results_map = cached.get("results_map", {}) or {}
            briefings = cached.get("briefings", []) or []
            print("Gemini cache HIT:", llm_cache.name)
        except Exception as e:
            print("Gemini cache read FAILED:", repr(e))

    # 4.6) Gemini attempt
    if not results_map and not briefings:
        if not should_use_gemini_today():
            print("Gemini disabled for this run (non-scheduled).")
        else:
            # si FORCE_GEMINI=1, ignoramos llm_done para poder probar
            if llm_done.exists() and not forced_gemini():
                print("Skipping Gemini: llm_done present (already attempted today).")
            else:
                try:
                    out = rank_batch(llm_payload)
                    results_map.update(out.get("map", {}))
                    briefings.append(out.get("briefing", {}) or {})

                    llm_cache.write_text(
                        json.dumps({"results_map": results_map, "briefings": briefings}, ensure_ascii=False, indent=2),
                        encoding="utf-8"
                    )
                    print("Gemini cache WRITTEN:", llm_cache.name)
                except Exception as e:
                    print("GEMINI rank_batch FAILED:", repr(e))
                finally:
                    llm_done.write_text(datetime.now().isoformat(), encoding="utf-8")

    briefing = merge_briefings(briefings) if briefings else {"signals": [], "risks": [], "watch": [], "entities_top": []}

    # 5) Apply LLM results
    reranked = []
    for it in candidates:
        rid = it.get("_rid")
        llm = results_map.get(rid) if rid else None

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

    # entities fallback
    for it in final_items:
        if not (it.get("entities") or []):
            it["entities"] = extract_entities_from_title(it.get("title", ""))

    # metrics
    scores = [it.get("score", 0) for it in final_items if isinstance(it.get("score", 0), (int, float))]
    score_avg = round(statistics.mean(scores), 2) if scores else 0

    primary_dist = {}
    for it in final_items:
        p = (it.get("primary", "misc") or "misc").strip()
        primary_dist[p] = primary_dist.get(p, 0) + 1

    entity_counts = {}
    for it in final_items:
        for e in (it.get("entities") or []):
            if not isinstance(e, str):
                continue
            e2 = normalize_entity(e)
            if is_bad_entity(e2):
                continue
            entity_counts[e2] = entity_counts.get(e2, 0) + 1

    top_entities = sorted(entity_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    top_entities_list = [e for e, _ in top_entities]

    # briefing fallback humano
    if not (briefing.get("signals") or briefing.get("risks") or briefing.get("watch") or briefing.get("entities_top")):
        top_cats = sorted(primary_dist.items(), key=lambda x: x[1], reverse=True)[:3]
        parts = []
        for c, ncat in top_cats:
            lbl = CATEGORY_LABELS.get(c, c)
            parts.append(f"{lbl} ({ncat}/{len(final_items)})")
        cat_txt = ", ".join(parts) if parts else "Misc"

        max_cat = top_cats[0][1] if top_cats else 0
        concentration = max_cat / max(1, len(final_items))
        if concentration >= 0.60:
            risk = "Concentración alta en una categoría: posible mono-tema o sesgo del scoring."
        elif concentration >= 0.50:
            risk = "Concentración media: vigilar si se consolida como narrativa dominante."
        else:
            risk = "Diversidad razonable de categorías (sin dominancia extrema)."

        watch = []
        if top_entities_list:
            watch.append(f"Seguir: {', '.join(top_entities_list[:3])}.")
        if top_cats:
            lbl0 = CATEGORY_LABELS.get(top_cats[0][0], top_cats[0][0])
            watch.append(f"Vigilar si '{lbl0}' mantiene dominancia mañana.")
        if not watch:
            watch = ["Aumentar histórico para detectar momentum real."]

        briefing = {
            "signals": [
                f"Mix de hoy (top): {cat_txt}.",
                f"Actores dominantes (hoy): {', '.join(top_entities_list) if top_entities_list else 'n/a'}.",
            ],
            "risks": [risk],
            "watch": watch[:3],
            "entities_top": top_entities_list[:5],
        }

    # snapshot
    daily_snapshot = {
        "date": today,
        "score_avg": score_avg,
        "primary_dist": primary_dist,
        "top_entities": [{"entity": e, "count": c} for e, c in top_entities],
        "briefing": briefing,
        "items": final_items,
    }

    Path(f"docs/data/{today}.json").write_text(
        json.dumps(daily_snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    html = render_index(final_items, briefing=briefing)
    Path("docs").mkdir(exist_ok=True)
    Path("docs/index.html").write_text(html, encoding="utf-8")

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
