# src/main.py
import os
import yaml
from pathlib import Path
from datetime import datetime
import json
import statistics
import re
import traceback
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.fetch import fetch_rss
from src.fetch_x import fetch_x_search, fetch_x_user
from src.render import render_index
from src.score import score_item
from src.llm_rank import rank_batch
from src.config import CATEGORY_LABELS, KNOWN_ENTITIES, ENTITY_ALIASES, STOP_ENTITIES, ALLOW_ACRONYMS


def env_flag(name: str, default: str = "") -> bool:
    val = (os.getenv(name) or default).strip().lower()
    return val in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


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


def normalize_entity(e: str) -> str:
    e = (e or "").strip()
    e = re.sub(r"\s+", " ", e)
    if e in ENTITY_ALIASES:
        return ENTITY_ALIASES[e]
    return e


TRACKING_QUERY_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
}


def canonical_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""

    try:
        parsed = urlsplit(raw)
    except ValueError:
        return raw

    if not parsed.scheme or not parsed.netloc:
        return raw

    pairs = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in TRACKING_QUERY_KEYS
    ]
    query = urlencode(pairs, doseq=True)
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, query, ""))


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


def should_use_gemini_today() -> bool:
    # Override explícito
    if env_flag("FORCE_GEMINI", "0"):
        return True
    
    event = (os.getenv("GITHUB_EVENT_NAME") or "").strip()
    # Solo Gemini en schedule (por defecto). En workflow_dispatch también si se quiere probar manual.
    if event == "schedule":
        return True
    if event == "workflow_dispatch":
        return True
        
    return False


def ingest_feeds(cfg: dict, per_source_cap: dict) -> list[dict]:
    items = []
    per_source_count = {}

    for s in cfg["sources"]:
        stype = (s.get("type") or "").strip().lower()
        if not stype:
            continue

        try:
            limit = int(s.get("limit", 12))
        except (TypeError, ValueError):
            print(f"Invalid limit for source {s.get('name', 'unnamed')}: {s.get('limit')!r}")
            continue
        if limit <= 0:
            continue
        if "limit" not in s and s["name"].startswith("arXiv"):
            limit = 6

        fetched = []
        if stype == "rss":
            if not s.get("url"):
                print(f"Invalid RSS source config (missing url): {s.get('name', 'unnamed')}")
                continue
            fetched = fetch_rss(s["url"], limit=limit)
        elif stype == "x":
            if s.get("username"):
                fetched = fetch_x_user(
                    username=s["username"],
                    limit=limit,
                    include_replies=bool(s.get("include_replies", False)),
                    include_retweets=bool(s.get("include_retweets", False)),
                )
            elif s.get("query"):
                fetched = fetch_x_search(
                    query=s["query"],
                    limit=limit,
                )
            else:
                print(f"Invalid X source config (missing username/query): {s.get('name', 'unnamed')}")
        else:
            print(f"Unknown source type '{stype}' for source: {s.get('name', 'unnamed')}")

        for it in fetched:
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
    return items


def dedup_items(items: list[dict]) -> list[dict]:
    seen = set()
    deduped = []
    for it in items:
        key = canonical_url(it.get("link", ""))
        if not key:
            title_key = re.sub(r"\s+", " ", (it.get("title") or "").strip().lower())
            key = f"title:{title_key}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)
    return deduped


def generate_llm_data(candidates: list[dict], llm_cache: Path, llm_done: Path) -> tuple[dict, list]:
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

    force_refresh = env_flag("FORCE_GEMINI_REFRESH", "0")
    
    # Cache HIT
    if llm_cache.exists() and not force_refresh:
        try:
            cached = json.loads(llm_cache.read_text(encoding="utf-8"))
            results_map = cached.get("results_map", {}) or {}
            briefings = cached.get("briefings", []) or []
            print("Gemini cache HIT:", llm_cache.name)
        except Exception as e:
            print("Gemini cache read FAILED:", repr(e))

    # Gemini attempt
    if not results_map and not briefings:
        use_gemini = should_use_gemini_today()
        if not use_gemini:
            print("Gemini disabled for this run (non-scheduled).")
        elif llm_done.exists() and not env_flag("FORCE_GEMINI", "0"):
            print("Skipping Gemini: llm_done present (already attempted today).")
        else:
            gemini_ok = False
            try:
                out = rank_batch(llm_payload)
                results_map.update(out.get("map", {}))
                b = out.get("briefing", {}) or {}
                briefings.append(b)

                gemini_ok = True
                try:
                    llm_cache.write_text(
                        json.dumps({"results_map": results_map, "briefings": briefings}, ensure_ascii=False, indent=2),
                        encoding="utf-8"
                    )
                    print("Gemini cache WRITTEN:", llm_cache.name)
                except Exception as cache_err:
                    print("Gemini cache write FAILED:", repr(cache_err))
            except Exception as e:
                print("GEMINI rank_batch FAILED:", repr(e))
            if gemini_ok:
                # marca intento exitoso de hoy para no repetir llamadas LLM
                llm_done.write_text(datetime.now().isoformat(), encoding="utf-8")
                
    return results_map, briefings


def apply_llm_results(candidates: list[dict], results_map: dict) -> list[dict]:
    reranked = []
    for it in candidates:
        rid = it.get("_rid")
        llm = results_map.get(str(rid)) or results_map.get(rid) # handle string/int keys

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

    min_x_items = max(0, env_int("MIN_X_ITEMS", 2))
    if min_x_items > 0:
        x_in_final = sum(1 for it in final_items if str(it.get("source", "")).startswith("X "))
        need = max(0, min_x_items - x_in_final)
        if need > 0:
            remaining_x = [it for it in reranked if str(it.get("source", "")).startswith("X ") and it not in final_items]
            for xit in remaining_x:
                replace_idx = None
                for i in range(len(final_items) - 1, -1, -1):
                    if not str(final_items[i].get("source", "")).startswith("X "):
                        replace_idx = i
                        break
                if replace_idx is None:
                    break
                final_items[replace_idx] = xit
                need -= 1
                if need <= 0:
                    break
            final_items.sort(key=lambda x: x.get("score", 0), reverse=True)
    
    for it in final_items:
        if not (it.get("entities") or []):
            it["entities"] = extract_entities_from_title(it.get("title", ""))
            
    return final_items


def calculate_stats(final_items: list[dict]) -> tuple[float, dict, list]:
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
    return score_avg, primary_dist, top_entities


def generate_fallback_briefing(final_items: list[dict], primary_dist: dict, top_entities_list: list) -> dict:
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

    return {
        "signals": [
            f"Mix de hoy (top): {cat_txt}.",
            f"Actores dominantes (hoy): {', '.join(top_entities_list) if top_entities_list else 'n/a'}.",
        ],
        "risks": [risk],
        "watch": watch[:3],
        "entities_top": top_entities_list[:5],
    }


def main():
    event = (os.getenv("GITHUB_EVENT_NAME") or "").strip()
    fg = (os.getenv("FORCE_GEMINI") or "").strip()
    print(f"Context: GITHUB_EVENT_NAME={event} FORCE_GEMINI={fg}")

    cfg_path = Path("feeds/feeds.yaml")
    if not cfg_path.exists():
        print("feeds/feeds.yaml not found!")
        return
        
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    per_source_cap = {
        "arXiv cs.AI": 2,
        "arXiv cs.LG": 2,
        "NVIDIA Blog": 2,
    }
    for source in cfg.get("sources", []):
        cap = source.get("cap")
        if cap is None:
            continue
        try:
            per_source_cap[source["name"]] = int(cap)
        except (TypeError, ValueError):
            print(f"Invalid cap for source {source.get('name', 'unnamed')}: {cap!r}")

    today = datetime.now().strftime("%Y-%m-%d")
    data_dir = Path("docs/data")
    data_dir.mkdir(parents=True, exist_ok=True)

    llm_done = data_dir / f"{today}.llm_done"
    llm_cache = data_dir / f"{today}.llm_cache.json"

    # 1) Ingest
    items = ingest_feeds(cfg, per_source_cap)

    # 2) Dedup
    deduped = dedup_items(items)

    # 3) Preselect
    deduped.sort(key=lambda x: x.get("score", 0), reverse=True)
    candidates = deduped[:30]

    # 4) LLM Rank
    results_map, briefings = generate_llm_data(candidates, llm_cache, llm_done)

    briefing = merge_briefings(briefings) if briefings else {}

    # 5) Apply LLM Results
    final_items = apply_llm_results(candidates, results_map)

    # 6) Stats & Fallback Briefing
    score_avg, primary_dist, top_entities = calculate_stats(final_items)
    top_entities_list = [e for e, _ in top_entities]

    if not briefing or not (briefing.get("signals") or briefing.get("risks") or briefing.get("watch") or briefing.get("entities_top")):
        briefing = generate_fallback_briefing(final_items, primary_dist, top_entities_list)

    # 7) Save Data
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

    # 8) Render HTML
    html = render_index(final_items, briefing=briefing)
    Path("docs").mkdir(exist_ok=True)
    Path("docs/index.html").write_text(html, encoding="utf-8")

    # 9) Weekly
    try:
        from src.weekly import main as weekly_main
        weekly_main()
        print("WEEKLY OK -> docs/weekly.html")
    except Exception:
        print("WEEKLY FAILED (traceback):")
        traceback.print_exc()


if __name__ == "__main__":
    main()
