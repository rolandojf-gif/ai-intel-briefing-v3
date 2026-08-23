# src/main.py
from __future__ import annotations
import os
import hashlib
import yaml
from pathlib import Path
from datetime import datetime, timezone
import json
import statistics
import re
import traceback
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.fetch import fetch_rss
from src.fetch_x import fetch_x_search, fetch_x_user
from src.render import render_index
from src.score import score_item
from src.llm_rank import rank_batch
from src.memory import (
    activity_level,
    detect_threads,
    entity_deltas,
    load_history,
    resolve_watchlist,
)
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
    # La tesis no se acumula entre briefings: se toma la del primero que la traiga.
    for b in briefs:
        if (b.get("thesis") or "").strip():
            out["thesis"] = b["thesis"].strip()
            break
    return out


def normalize_entity(e: str) -> str:
    e = (e or "").strip()
    e = re.sub(r"\s+", " ", e)
    if e in ENTITY_ALIASES:
        return ENTITY_ALIASES[e]
    for src, dst in ENTITY_ALIASES.items():
        if e.lower() == src.lower():
            return dst
    return e


def clean_signal_text(text: str, source: str = "") -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    raw = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", raw)
    raw = re.sub(r"!\s*Image\s*\d*:?", " ", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\bImage\s*\d*:?", " ", raw, flags=re.IGNORECASE)
    raw = re.sub(r"https?://\S+", " ", raw)
    raw = re.sub(r"#([A-Za-z0-9_]+)", r"\1", raw)
    raw = re.sub(r"&amp;", "&", raw)
    raw = re.sub(r"\s+", " ", raw).strip()

    if (source or "").startswith("X ") and " Quote " in raw:
        lead, quoted = raw.split(" Quote ", 1)
        if len(lead.strip()) >= 24:
            raw = lead.strip()
        else:
            raw = f"{lead.strip()} / {quoted.strip()}"

    raw = re.sub(r"\s+@\w+\s+[A-Z][a-z]{2}\s+\d{1,2}\s+", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


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
    if e2 in STOP_ENTITIES or e2.lower() in {x.lower() for x in STOP_ENTITIES}:
        return True
    if re.search(r"https?://|[#@]", e2):
        return True
    if len(e2) <= 2 and e2.isupper() and e2 not in ALLOW_ACRONYMS and e2 not in ENTITY_ALIASES:
        return True
    if len(e2) < 3:
        return True
    if len(e2.split()) > 3:
        return True
    return False


def extract_entities_from_title(title: str) -> list[str]:
    t = title or ""
    hits = []

    for e in KNOWN_ENTITIES:
        if re.search(r"\b" + re.escape(e) + r"\b", t, flags=re.IGNORECASE):
            norm = normalize_entity(e)
            if not is_bad_entity(norm) and norm not in hits:
                hits.append(norm)

    for m in re.findall(r"\b[A-Z][A-Z0-9]{1,6}\b", t):
        m2 = normalize_entity(m)
        if is_bad_entity(m2):
            continue
        if m2 not in hits:
            hits.append(m2)

    candidates = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b", t)
    stop_words = {"The", "A", "An", "And", "Of", "In", "On", "For", "With", "New", "Stop", "Making", "Best", "Top", "Great", "Good", "Run", "Running", "Build", "Building", "Using", "How", "Why", "What", "When", "Where", "Which", "Who", "Free", "Open", "All", "Every", "Some", "One", "Two", "Three", "Four", "Five", "Fast", "Faster", "Guide", "Ranking", "Ranked", "Review", "Summary", "Overview"} | STOP_ENTITIES
    for c in candidates:
        c_words = set(c.strip().split())
        if c_words & stop_words:
            continue
        c2 = normalize_entity(c.strip())
        if c2 in stop_words or is_bad_entity(c2):
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


def clean_entities(raw_entities: list, title: str = "") -> list[str]:
    out = []
    seen = set()
    source_entities = list(raw_entities or [])
    has_specific_gpt = any(isinstance(e, str) and re.search(r"\bGPT[- ]\d", e, re.IGNORECASE) for e in source_entities)
    for e in source_entities:
        if not isinstance(e, str):
            continue
        e2 = normalize_entity(e)
        e2 = re.sub(r"^[^A-Za-z0-9]+|[^A-Za-z0-9. -]+$", "", e2).strip()
        if has_specific_gpt and e2.upper() == "GPT":
            continue
        if is_bad_entity(e2):
            continue
        key = e2.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(e2)

    # El extractor por regex del titulo solo actua como FALLBACK. Cuando el LLM ya
    # ha dado entidades, anadirlo contamina: produce frases en Title Case como
    # "Contracted Power" o "Creating Scientific Figures", que no son entidades y
    # ensucian el momentum y los deltas de la capa de memoria.
    if not out:
        for e in extract_entities_from_title(title):
            e2 = normalize_entity(e)
            if has_specific_gpt and e2.upper() == "GPT":
                continue
            if is_bad_entity(e2):
                continue
            key = e2.lower()
            if key not in seen:
                seen.add(key)
                out.append(e2)
            if len(out) >= 6:
                break
    return out[:6]


def should_use_gemini_today() -> bool:
    # Si FORCE_GEMINI esta explicitamente desactivado
    if (os.getenv("FORCE_GEMINI") or "").strip() == "0":
        return False
    # Override explicito para activar
    if env_flag("FORCE_GEMINI", "0"):
        return True
    # Si la API key de Gemini esta presente en el entorno (GitHub Actions o local), usarla
    if (os.getenv("GEMINI_API_KEY") or "").strip():
        return True

    event = (os.getenv("GITHUB_EVENT_NAME") or "").strip()
    if event in ("schedule", "workflow_dispatch", "push"):
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

        fetched = []
        if stype == "rss":
            if not s.get("url"):
                print(f"Invalid RSS source config (missing url): {s.get('name', 'unnamed')}")
                continue
            try:
                fetched = fetch_rss(s["url"], limit=limit)
            except Exception as e:
                # Una fuente rota no debe tumbar el run entero; el health-check la marca.
                print(f"FETCH FAILED for {s.get('name', 'unnamed')}: {e!r}")
                fetched = []
        elif stype == "artificial_analysis":
            try:
                from src.fetch import fetch_artificial_analysis
                fetched = fetch_artificial_analysis(limit=limit)
            except Exception as e:
                print(f"FETCH FAILED for {s.get('name', 'unnamed')}: {e!r}")
                fetched = []
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
            it["raw_title"] = it.get("title", "")
            it["raw_summary"] = it.get("summary", "")
            it["title"] = clean_signal_text(it.get("title", ""), it["source"])
            it["summary"] = clean_signal_text(it.get("summary", ""), it["source"])

            src = it["source"]
            cap = per_source_cap.get(src)
            if cap is not None:
                per_source_count[src] = per_source_count.get(src, 0)
                if per_source_count[src] >= cap:
                    continue
                per_source_count[src] += 1

            sc = score_item(it["title"], it.get("summary", ""), it["source"])
            it.update(sc)
            it["heuristic_score"] = int(it.get("score", 0) or 0)
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


def title_fingerprint(title: str) -> str:
    base = re.sub(r"[^a-z0-9\s]", " ", (title or "").lower())
    tokens = [t for t in re.split(r"\s+", base) if t and len(t) > 2]
    return " ".join(tokens[:16])


def load_recent_history(data_dir: Path, today: str, days: int = 5) -> tuple[set[str], set[str]]:
    history_urls: set[str] = set()
    history_titles: set[str] = set()
    snapshots = sorted(data_dir.glob("*.json"), key=lambda p: p.name)
    recent = [p for p in snapshots if p.stem != today][-days:]

    for path in recent:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for it in data.get("items", []):
            if not isinstance(it, dict):
                continue
            curl = canonical_url(it.get("link") or it.get("url") or "")
            if curl:
                history_urls.add(curl)
            tfp = title_fingerprint(it.get("title", ""))
            if tfp:
                history_titles.add(tfp)

    return history_urls, history_titles


def apply_novelty_penalty(items: list[dict], history_urls: set[str], history_titles: set[str]) -> list[dict]:
    scored = []
    for it in items:
        base_score = int(it.get("heuristic_score", it.get("score", 0)) or 0)
        curl = canonical_url(it.get("link", ""))
        tfp = title_fingerprint(it.get("title", ""))

        repeated_url = bool(curl and curl in history_urls)
        repeated_title = bool(tfp and tfp in history_titles)
        is_repeat = repeated_url or repeated_title

        penalty = 0
        if repeated_url:
            penalty += 35
        if repeated_title:
            penalty += 20

        novelty_score = max(0, min(100, 100 - penalty))
        adjusted_score = max(0, base_score - penalty)

        it["is_repeat"] = is_repeat
        it["novelty_score"] = novelty_score
        it["adjusted_score"] = adjusted_score
        scored.append(it)
    return scored


def clamp_score(value: float | int) -> int:
    return max(0, min(100, int(round(float(value)))))


def parse_published_dt(raw_value) -> datetime | None:
    raw = (raw_value or "").strip()
    if not raw:
        return None

    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        pass

    try:
        dt2 = parsedate_to_datetime(raw)
        if dt2.tzinfo is None:
            dt2 = dt2.replace(tzinfo=timezone.utc)
        return dt2.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def item_age_days(it: dict) -> int | None:
    dt = parse_published_dt(it.get("published"))
    if not dt:
        return None
    now_utc = datetime.now(timezone.utc)
    days = (now_utc - dt).days
    return max(0, days)


def infer_strategic_theme(it: dict) -> str:
    text = f"{it.get('title', '')}\n{it.get('summary', '')}".lower()
    tags = [str(t).lower() for t in ((it.get("tags") or []) + (it.get("feed_tags") or [])) if isinstance(t, str)]
    source = (it.get("source") or "").lower()

    def has_any(words: list[str]) -> bool:
        return any(w in text for w in words) or any(w in tags for w in words) or any(w in source for w in words)

    if has_any(["agent", "agents", "mcp", "workflow", "autonomous", "automation", "coding", "tool use", "function calling", "browser use"]):
        return "agents_automation"
    if has_any(["chip", "gpu", "hbm", "datacenter", "data center", "tpu", "training cluster", "compute", "tsmc", "asml", "smic", "blackwell", "gb200", "b200"]):
        return "compute_chips_dc"
    if has_any(["price", "pricing", "api", "cost", "token", "margin", "capex", "opex", "revenue", "valuation"]):
        return "model_economics"
    if has_any(["china", "huawei", "deepseek", "alibaba", "tencent", "bytedance", "zhipu", "glm", "moonshot", "kimi", "qwen", "minimax", "01.ai", "yi", "baichuan"]):
        return "china_stack"
    if has_any(["export control", "sanction", "regulation", "policy", "eu ai act", "bis", "sovereign", "national security"]):
        return "geopolitics_power"
    if has_any(["agi", "reasoning", "frontier", "model", "multimodal", "benchmark", "alignment", "gemini", "claude", "gpt", "o1", "o3", "mistral", "llama"]):
        return "frontier_capability"
    primary = (it.get("primary") or "").strip()
    if primary == "models":
        return "frontier_capability"
    if primary == "infra":
        return "compute_chips_dc"
    if primary == "invest":
        return "model_economics"
    if primary == "geopol":
        return "geopolitics_power"
    return "other"


def compute_noise_penalty(it: dict) -> int:
    title = (it.get("title") or "").lower()
    summary = (it.get("summary") or "").lower()
    text = f"{title}\n{summary}"
    source = (it.get("source") or "").lower()

    penalty = 0
    fluff_tokens = [
        "webinar",
        "forum",
        "applications now open",
        "award",
        "event",
        "sponsored",
        "meet us",
        "join us",
        "booth",
        "register now",
    ]
    if any(tok in text for tok in fluff_tokens):
        penalty += 12

    entities = [e for e in (it.get("entities") or []) if isinstance(e, str) and e.strip()]
    if (it.get("primary") or "").strip() == "misc" and not entities:
        penalty += 8

    promotional_sources = ["google ai blog", "nvidia blog", "deepmind blog"]
    has_hard_signal = any(k in text for k in ["price", "pricing", "capex", "opex", "datacenter", "hbm", "gpu", "training", "inference", "weights", "benchmark", "reasoning"])
    if any(s in source for s in promotional_sources) and not has_hard_signal:
        penalty += 8

    if "nvidia" in source and not has_hard_signal:
        nvidia_pr_tokens = [
            "applications now open",
            "special presentation",
            "innovation to impact",
            "teaching",
            "bridge communication",
            "introducing",
        ]
        if any(tok in text for tok in nvidia_pr_tokens):
            penalty += 6

    age_days = item_age_days(it)
    if age_days is not None:
        if age_days >= 14:
            penalty += 45
        elif age_days >= 7:
            penalty += 25
        elif age_days >= 4:
            penalty += 12
        elif age_days >= 2:
            penalty += 4

    return min(45, max(0, penalty))


def _batch_fingerprint(payload: list[dict]) -> str:
    s = json.dumps(
        [{"id": p["id"], "t": (p.get("title") or "")[:50]} for p in payload],
        ensure_ascii=False, separators=(",", ":"),
    )
    return hashlib.md5(s.encode()).hexdigest()[:12]


def is_fresh_enough(it: dict) -> bool:
    source = (it.get("source") or "").lower()
    age = item_age_days(it)
    if age is None:
        return True
    if any(s in source for s in ("nvidia", "google ai", "deepmind", "semiwiki")):
        return age <= 7
    return age <= 5


def generate_llm_data(candidates: list[dict], llm_cache: Path, llm_done: Path) -> tuple[dict, list]:
    llm_payload = []
    for idx, it in enumerate(candidates[:20], start=1):
        llm_payload.append({
            "id": idx,
            "source": it.get("source", ""),
            "title": it.get("title", ""),
            "summary": it.get("summary", ""),
            "url": it.get("link", ""),
        })
        it["_rid"] = idx

    current_fp = _batch_fingerprint(llm_payload)
    results_map = {}
    briefings = []

    force_refresh = env_flag("FORCE_GEMINI_REFRESH", "0")

    # Cache HIT
    if llm_cache.exists() and not force_refresh:
        try:
            cached = json.loads(llm_cache.read_text(encoding="utf-8"))
            cached_fp = cached.get("batch_fingerprint")
            if cached_fp and cached_fp != current_fp:
                print("Gemini cache STALE: invalidating.")
            else:
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
            last_err = None
            # Un fallo transitorio de la API dejaba el dia entero sin gate de
            # relevancia (ver 2026-08-22). Reintentamos antes de degradar.
            for attempt in (1, 2, 3):
                try:
                    out = rank_batch(llm_payload)
                    results_map.update(out.get("map", {}))
                    b = out.get("briefing", {}) or {}
                    briefings.append(b)
                    gemini_ok = True
                    break
                except Exception as e:
                    last_err = e
                    print(f"GEMINI rank_batch FAILED (intento {attempt}/3):", repr(e))

            if gemini_ok:
                try:
                    llm_cache.write_text(
                        json.dumps(
                            {
                                "batch_fingerprint": current_fp,
                                "results_map": results_map,
                                "briefings": briefings,
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8"
                    )
                    print("Gemini cache WRITTEN:", llm_cache.name)
                except Exception as cache_err:
                    print("Gemini cache write FAILED:", repr(cache_err))
                # marca intento exitoso de hoy para no repetir llamadas LLM
                llm_done.write_text(datetime.now().isoformat(), encoding="utf-8")
            else:
                print(f"GEMINI agotó los reintentos; el dia sera degradado. Ultimo error: {last_err!r}")

    return results_map, briefings


MAX_SIGNALS = 8      # techo de senales primarias; el suelo lo marca la realidad del dia
MAX_CONTEXT = 5      # capa secundaria de contexto


def apply_llm_results(candidates: list[dict], results_map: dict) -> list[dict]:
    reranked = []
    for it in candidates:
        rid = it.get("_rid")
        llm = results_map.get(str(rid)) or results_map.get(rid) # handle string/int keys

        if llm:
            # Contrato v2: juicio de relevancia, no score de impacto generico.
            it["llm_score"] = llm.get("relevance", llm.get("score"))
            it["verdict"] = (llm.get("verdict") or "context").strip().lower()
            it["so_what"] = (llm.get("so_what") or "").strip()
            it["power_shift"] = (llm.get("power_shift") or "").strip()
            it["watch_next"] = (llm.get("watch_next") or "").strip()
            it["title_es"] = (llm.get("headline_es") or llm.get("title_es") or "").strip()
            it["llm_theme"] = (llm.get("theme") or "").strip()
            it["why"] = it["so_what"]          # alias legacy para render
            it["primary"] = llm.get("primary", it.get("primary", "misc"))
            it["tags"] = llm.get("tags", [])
            it["entities"] = llm.get("entities", [])
        else:
            # Sin LLM no hay gate posible: se marca degradado y no se afirma relevancia.
            it["llm_score"] = None
            it["verdict"] = "unrated"
            it["so_what"] = ""
            it["power_shift"] = ""
            it["watch_next"] = ""
            it["llm_theme"] = ""
            it["primary"] = it.get("primary", "misc")
            it["tags"] = it.get("tags", [])
            it["title_es"] = it.get("title_es", "")
            it["entities"] = it.get("entities", [])
            it["why"] = it.get("summary", "")[:160]

        heuristic_score = int(it.get("heuristic_score", it.get("score", 0)) or 0)
        adjusted_score = int(it.get("adjusted_score", heuristic_score) or 0)
        it["heuristic_score"] = clamp_score(heuristic_score)
        it["adjusted_score"] = clamp_score(adjusted_score)

        llm_score_raw = it.get("llm_score")
        llm_score_valid = False
        llm_score_num = None
        if llm_score_raw is not None:
            try:
                llm_score_num = clamp_score(float(llm_score_raw))
                llm_score_valid = True
            except (TypeError, ValueError):
                llm_score_valid = False

        noise_penalty = compute_noise_penalty(it)
        strategic_theme = infer_strategic_theme(it)

        # Freshness bonus: prioritize breaking/recent items (<24-48h)
        age_days = item_age_days(it)
        recency_boost = 0
        if age_days is not None:
            if age_days == 0:
                recency_boost = 12
            elif age_days == 1:
                recency_boost = 6

        if llm_score_valid and llm_score_num is not None:
            final_score = clamp_score((0.85 * llm_score_num) + (0.15 * it["adjusted_score"]) + recency_boost - noise_penalty)
            ranking_reason = f"llm(0.85)+adjusted(0.15)+recency({recency_boost})-noise({noise_penalty})"
            it["llm_score"] = llm_score_num
        else:
            final_score = clamp_score(it["adjusted_score"] + recency_boost - noise_penalty)
            ranking_reason = f"fallback_adjusted+recency({recency_boost})-noise({noise_penalty})"
            it["llm_score"] = None

        it["noise_penalty"] = noise_penalty
        it["final_score"] = final_score
        it["score"] = final_score  # legacy alias
        it["ranking_reason"] = ranking_reason
        # El tema del LLM manda sobre la heuristica de keywords cuando existe.
        it["strategic_theme"] = it.get("llm_theme") or strategic_theme
        it["entities"] = clean_entities(it.get("entities") or [], it.get("title", ""))

        reranked.append(it)

    reranked.sort(key=lambda x: x.get("final_score", x.get("score", 0)), reverse=True)

    # -- Gate de relevancia --------------------------------------------------
    # Lo marcado `noise` se ELIMINA. No se rankea mas abajo: desaparece.
    # Esto es lo que permite que un dia flojo muestre 3 items en vez de rellenar
    # hasta 15 con ruido.
    signals = [it for it in reranked if it.get("verdict") == "signal"][:MAX_SIGNALS]
    context = [it for it in reranked if it.get("verdict") == "context"][:MAX_CONTEXT]
    dropped = sum(1 for it in reranked if it.get("verdict") == "noise")

    # Distinguir "el LLM juzgo y descarto todo" de "el LLM no llego a correr":
    # en el primer caso el resultado correcto es CERO items, no un fallback con ruido.
    gate_ran = any(it.get("verdict") in ("signal", "context", "noise") for it in reranked)

    if gate_ran:
        for it in signals:
            it["layer"] = "signal"
        for it in context:
            it["layer"] = "context"
        final_items = signals + context
        print(f"Relevance gate: {len(signals)} signal / {len(context)} context / {dropped} noise descartados")
        if not final_items:
            print("Gate: dia sin senal - todo lo ingerido era ruido. Se muestra vacio a proposito.")
    else:
        # Sin veredictos (Gemini caido): modo degradado. No afirmamos relevancia
        # que no hemos podido juzgar; la UI avisa de que el filtro no se aplico.
        final_items = reranked[:10]
        for it in final_items:
            it["layer"] = "unrated"
        print(f"Relevance gate INACTIVO (sin veredictos LLM): {len(final_items)} items sin filtrar")

    for it in final_items:
        it["entities"] = clean_entities(it.get("entities") or [], it.get("title", ""))

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
    """Briefing minimo cuando el LLM no esta disponible.

    Deliberadamente escueto y honesto: sin el LLM no podemos emitir una tesis
    estrategica, asi que no fingimos una.
    """
    if not final_items:
        return {
            "thesis": "Sin datos suficientes para emitir una lectura del dia.",
            "signals": [],
            "risks": [],
            "watch": [],
            "entities_top": [],
        }

    top_items = sorted(final_items, key=lambda x: x.get("score", 0), reverse=True)[:3]
    lead_title = (top_items[0].get("title") or "").strip() if top_items else ""

    return {
        "thesis": "Analisis no disponible hoy: el filtro de relevancia no se ha aplicado.",
        "signals": [(it.get("title") or "").strip()[:130] for it in top_items if it.get("title")],
        "risks": [
            "Sin juicio del LLM no se puede distinguir senal de ruido: tratar todo como no verificado."
        ],
        "watch": ["Confirmar que el analisis vuelve a ejecutarse en el proximo run."],
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

    # Los caps salen SOLO de feeds.yaml. Los hardcodeados apuntaban a nombres
    # que ya no existian ("NVIDIA Blog" vs "NVIDIA Blog (AI)") y no se aplicaban.
    per_source_cap: dict[str, int] = {}
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

    # 1.5) Source health - una fuente muerta debe ser visible, no fallar en silencio.
    #      (X estuvo devolviendo 0 items durante 14+ dias sin que nadie lo notara.)
    configured = [s.get("name", "?") for s in cfg.get("sources", [])]
    got: dict[str, int] = {}
    for it in items:
        got[it.get("source", "?")] = got.get(it.get("source", "?"), 0) + 1
    dead_sources = [n for n in configured if got.get(n, 0) == 0]
    source_health = {
        "configured": len(configured),
        "alive": len(configured) - len(dead_sources),
        "dead": dead_sources,
        "counts": got,
    }
    print(f"Source health: {source_health['alive']}/{source_health['configured']} vivas")
    if dead_sources:
        print(f"  SIN ITEMS: {', '.join(dead_sources)}")

    # 2) Dedup
    deduped = dedup_items(items)

    # 2.5) Novelty (anti-repeticion respecto ultimos dias)
    history_urls, history_titles = load_recent_history(data_dir, today=today, days=5)
    deduped = apply_novelty_penalty(deduped, history_urls, history_titles)

    before_age = len(deduped)
    deduped = [it for it in deduped if is_fresh_enough(it)]
    dropped_age = before_age - len(deduped)
    if dropped_age:
        print(f"Age filter: removed {dropped_age} stale items exceeding freshness threshold.")

    # 3) Preselect
    deduped.sort(key=lambda x: x.get("adjusted_score", x.get("score", 0)), reverse=True)
    candidates = deduped[:30]

    # Enriquecer candidatos con imagenes OpenGraph en alta resolucion
    from src.fetch import enrich_items_with_images
    candidates = enrich_items_with_images(candidates)

    # 4) LLM Rank
    results_map, briefings = generate_llm_data(candidates, llm_cache, llm_done)

    briefing = merge_briefings(briefings) if briefings else {}

    # 5) Apply LLM Results (gate de relevancia)
    final_items = apply_llm_results(candidates, results_map)
    final_items = enrich_items_with_images(final_items)

    # 6) Stats & Fallback Briefing
    score_avg, primary_dist, top_entities = calculate_stats(final_items)
    top_entities_list = [e for e, _ in top_entities]

    if not briefing or not (briefing.get("thesis") or briefing.get("signals")):
        briefing = generate_fallback_briefing(final_items, primary_dist, top_entities_list)

    # 6.5) Memoria: continuidad entre dias. Determinista, sobrevive a fallos del LLM.
    degraded = not any(it.get("llm_score") is not None for it in final_items)
    try:
        history = load_history(data_dir, today=today, days=10)
        memory = {
            "watch_resolved": resolve_watchlist(history, final_items),
            "entity_deltas": entity_deltas(history, final_items),
            "threads": detect_threads(history, final_items),
        }
        level_label, level_class = activity_level(final_items, degraded=degraded)
    except Exception:
        print("MEMORY layer FAILED (traceback):")
        traceback.print_exc()
        memory = {"watch_resolved": [], "entity_deltas": {}, "threads": []}
        level_label, level_class = ("SIN FILTRAR", "quiet")

    if degraded:
        print("AVISO: dia degradado - sin veredictos del LLM, el gate de relevancia no se aplico.")

    # 7) Save Data
    daily_snapshot = {
        "date": today,
        "score_avg": score_avg,
        "primary_dist": primary_dist,
        "top_entities": [{"entity": e, "count": c} for e, c in top_entities],
        "briefing": briefing,
        "memory": memory,
        "activity": {"label": level_label, "class": level_class},
        "source_health": source_health,
        "degraded": degraded,
        # candidates fue mutado in-place por apply_llm_results, asi que lleva los veredictos
        "dropped_noise": sum(1 for it in candidates if it.get("verdict") == "noise"),
        "counts": {
            "signal": sum(1 for it in final_items if it.get("layer") == "signal"),
            "context": sum(1 for it in final_items if it.get("layer") == "context"),
        },
        "items": final_items,
    }

    Path(f"docs/data/{today}.json").write_text(
        json.dumps(daily_snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # 8) Render HTML
    from src.market import get_market_overview
    market_data = get_market_overview()
    html = render_index(final_items, briefing=briefing, snapshot=daily_snapshot, market=market_data)
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
