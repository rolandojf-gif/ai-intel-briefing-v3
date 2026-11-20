# src/main.py
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
import os
import hashlib
import html
import yaml
from pathlib import Path
from datetime import datetime, timezone
import json
import statistics
import re
import traceback
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.evidence import LABELS, PENDING, UNCERTAIN, percentages_supported, qualify_item
from src.fetch import clip_text, fetch_rss, resolve_items_google_news
from src.fetch_x import fetch_x_search, fetch_x_user
from src.render import render_index
from src.score import score_item
from src.followups import excerpt, followups, previous_state, with_open_stories
from src.llm_rank import rank_batch
from src.memory import (
    known_before,
    _is_snapshot,
    activity_level,
    detect_threads,
    entity_deltas,
    load_history,
    resolve_watchlist,
)
from src.config import (
    CATEGORY_LABELS,
    KNOWN_ENTITIES,
    ENTITY_ALIASES,
    STOP_ENTITIES,
    ALLOW_ACRONYMS,
    LEAD_SLOT_COUNT,
    demote_repeats_from_lead,
    radar_today_str,
)


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


def merge_briefings(briefs: list[dict], published: list[dict]) -> dict:
    """Construye el JSON público solo con referencias a señales que han pasado el gate."""
    by_id = {it["_rid"]: it for it in published if it.get("evidence") and "_rid" in it}
    out = {"signals": [], "risks": [], "watch": [], "entities_top": [],
           "signals_en": [], "risks_en": [], "watch_en": [], "evidence": {}}
    for brief in briefs:
        out["entities_top"] = list(dict.fromkeys(out["entities_top"] + brief.get("entities_top", [])))[:5]
        for ref in brief.get("references", []):
            field, idx, ids = ref["field"], ref["index"], ref["ids"]
            if not ids or any(i not in by_id for i in ids):
                continue
            if field == "thesis":
                if idx != 0 or "thesis" in out:
                    continue
                es, en = brief.get(field), brief.get("thesis_en")
                key = field
            else:
                if len(out[field]) >= {"signals": 5, "risks": 3, "watch": 3}[field]:
                    continue
                es_list, en_list = brief.get(field, []), brief.get(field + "_en", [])
                if not 0 <= idx < min(len(es_list), len(en_list)):
                    continue
                es, en = es_list[idx], en_list[idx]
                key = f"{field}.{len(out[field])}"
            if not es or not en:
                continue
            sources = [by_id[i] for i in dict.fromkeys(ids)]
            if field != "watch":
                if not percentages_supported(es + " " + en, [it["evidence"]["quote"] for it in sources]):
                    continue
                # Una síntesis es una lectura incluso si se apoya en hechos confirmados.
                kind = "inference"
                if any(it["evidence_kind"] == "speculation" for it in sources):
                    kind = "speculation"
                es, en = f"{LABELS[kind][0]} · {es}", f"{LABELS[kind][1]} · {en}"
            if field == "thesis":
                out[field], out["thesis_en"] = es, en
            else:
                if es in out[field]:
                    continue
                out[field].append(es)
                out[field + "_en"].append(en)
            out["evidence"][key] = [it["evidence"] for it in sources]
    if "thesis" not in out:
        out["thesis"] = "Evidencia insuficiente para una tesis del día."
        out["thesis_en"] = "Insufficient evidence for a daily thesis."
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
    # Antes de quitar hashtags: si no, "&#039;" pierde la almohadilla y se
    # queda como "&039;", que ya no se puede decodificar.
    raw = html.unescape(raw)
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
    if event in ("schedule", "workflow_dispatch"):
        return True

    return False


def _source_selection_key(it: dict) -> tuple[int, int, int, int]:
    fresh_flag = 1 if is_fresh_enough(it) else 0
    dt = parse_published_dt(it.get("published"))
    has_dt = 1 if dt is not None else 0
    day_bucket = int(dt.timestamp() // 86400) if dt is not None else 0
    hscore = int(it.get("heuristic_score", 0) or 0)
    return (fresh_flag, has_dt, day_bucket, hscore)


def _fetch_non_x_source(s: dict, stype: str, limit: int) -> list[dict]:
    if stype == "rss":
        if not s.get("url"):
            print(f"Invalid RSS source config (missing url): {s.get('name', 'unnamed')}")
            return []
        try:
            return fetch_rss(s["url"], limit=limit, resolve_gn=False)
        except Exception as e:
            # Una fuente rota no debe tumbar el run entero; el health-check la marca.
            print(f"FETCH FAILED for {s.get('name', 'unnamed')}: {e!r}")
            return []
    if stype == "artificial_analysis":
        try:
            from src.fetch import fetch_artificial_analysis
            return fetch_artificial_analysis(limit=limit)
        except Exception as e:
            print(f"FETCH FAILED for {s.get('name', 'unnamed')}: {e!r}")
            return []
    print(f"Unknown source type '{stype}' for source: {s.get('name', 'unnamed')}")
    return []


def ingest_feeds(cfg: dict, per_source_cap: dict) -> tuple[list[dict], dict]:
    items = []
    x_names: list[str] = []
    x_disabled = env_flag("X_DISABLED", "0")

    prepared: list[tuple[dict, str, int]] = []
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

        if stype == "x":
            x_names.append(s.get("name") or s.get("username") or "X")
            if x_disabled:
                continue

        prepared.append((s, stype, limit))

    fetched_by_idx: dict[int, list[dict]] = {}
    parallel_jobs: list[tuple[int, dict, str, int]] = []
    for idx, (s, stype, limit) in enumerate(prepared):
        if stype != "x":
            parallel_jobs.append((idx, s, stype, limit))

    if parallel_jobs:
        workers = min(8, len(parallel_jobs))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {
                idx: pool.submit(_fetch_non_x_source, s, stype, limit)
                for idx, s, stype, limit in parallel_jobs
            }
            for idx, fut in futs.items():
                try:
                    fetched_by_idx[idx] = fut.result() or []
                except Exception as e:
                    src_name = prepared[idx][0].get("name", "unnamed")
                    print(f"FETCH FAILED for {src_name}: {e!r}")
                    fetched_by_idx[idx] = []

    for idx, (s, stype, limit) in enumerate(prepared):
        if stype == "x":
            fetched = []
            try:
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
                    fetched = []
            except Exception as e:
                print(f"FETCH FAILED for {s.get('name', 'unnamed')}: {e!r}")
                fetched = []
        else:
            fetched = fetched_by_idx.get(idx, [])

        src_items: list[dict] = []
        src_name = s["name"]
        for it in fetched:
            if not it.get("title") or not it.get("link"):
                continue

            it["source"] = src_name
            it["feed_tags"] = s.get("tags", [])
            it["title"] = clean_signal_text(it.get("title", ""), it["source"])
            it["summary"] = clip_text(clean_signal_text(it.get("summary", ""), it["source"]))

            sc = score_item(it["title"], it.get("summary", ""), it["source"])
            it.update(sc)
            it["heuristic_score"] = int(it.get("score", 0) or 0)
            it["url"] = it.get("link", "")
            src_items.append(it)

        # Seleccionar los mejores/mas frescos por fuente antes de aplicar el cap
        # para no desperdiciar un cap:1 con una noticia vieja o irrelevante de Google News.
        cap = per_source_cap.get(src_name)
        if cap is not None:
            if cap <= 0:
                continue
            if len(src_items) > cap:
                src_items.sort(key=_source_selection_key, reverse=True)
                src_items = src_items[:cap]

        items.extend(src_items)

    # Decodificar URLs de Google News solo en los items que sobrevivieron al cap.
    resolve_items_google_news(items)
    for it in items:
        it["url"] = it.get("link", "") or it.get("url", "")

    counts = {}
    for it in items:
        src = it.get("source", "?")
        counts[src] = counts.get(src, 0) + 1
    x_layer = evaluate_x_layer(x_names, counts, disabled=x_disabled)
    if x_layer["status"] == "killed":
        print(
            f"X KILL SWITCH: 0 posts de {x_layer['configured']} cuentas. "
            "El briefing sigue sin capa X."
        )
    elif x_layer["status"] == "disabled":
        print("X DISABLED: capa X omitida (X_DISABLED=1).")
    elif x_layer["configured"]:
        print(
            f"X layer: {x_layer['posts']} posts "
            f"({len(x_layer['alive'])}/{x_layer['configured']} cuentas)"
        )
    return items, x_layer


def evaluate_x_layer(accounts: list[str], counts: dict[str, int], disabled: bool = False) -> dict:
    """Decide si la capa X se publica o se apaga entera.

    Cero posts en todas las cuentas no es '6 fuentes muertas': es el espejo
    caído. El kill switch evita que eso ensucie el health y el radar.
    """
    names = [n for n in accounts if n]
    if disabled:
        return {
            "status": "disabled",
            "reason": "X_DISABLED",
            "configured": len(names),
            "posts": 0,
            "alive": [],
            "silent": names,
            "accounts": names,
        }
    posts = sum(int(counts.get(n, 0) or 0) for n in names)
    alive = [n for n in names if (counts.get(n, 0) or 0) > 0]
    silent = [n for n in names if n not in alive]
    if names and posts == 0:
        return {
            "status": "killed",
            "reason": "zero_posts",
            "configured": len(names),
            "posts": 0,
            "alive": [],
            "silent": silent,
            "accounts": names,
        }
    return {
        "status": "ok",
        "reason": "",
        "configured": len(names),
        "posts": posts,
        "alive": alive,
        "silent": silent,
        "accounts": names,
    }


def build_source_health(configured: list[str], items: list[dict], x_layer: dict | None = None) -> dict:
    got: dict[str, int] = {}
    for it in items:
        src = it.get("source", "?")
        got[src] = got.get(src, 0) + 1
    skip = set()
    x_layer = x_layer or {}
    if x_layer.get("status") in {"killed", "disabled"}:
        skip = set(x_layer.get("accounts") or [])
    visible = [n for n in configured if n not in skip]
    dead = [n for n in visible if got.get(n, 0) == 0]
    return {
        "configured": len(visible),
        "alive": len(visible) - len(dead),
        "dead": dead,
        "counts": got,
        "x": x_layer,
    }


def dedup_items(items: list[dict]) -> list[dict]:
    # El juicio semántico se hace tras el ranking. Con 3 palabras compartidas
    # se perdían cambios de precio y otras novedades antes de llegar al modelo.
    seen = {}
    deduped = []
    for it in items:
        key = _source_text(it)
        lead = seen.get(key)
        if lead is not None and key[0]:
            source = it.get("source")
            if source and source != lead.get("source"):
                sources = lead.setdefault("other_sources", [])
                if source not in sources:
                    sources.append(source)
                url = it.get("url") or it.get("link")
                if url:
                    related = lead.setdefault("related", [])
                    if all(r["url"] != url for r in related):
                        related.append({"source": source, "url": url})
            continue
        seen[key] = it
        deduped.append(it)
    return deduped


def _source_text(it: dict) -> tuple[str, str]:
    return tuple(" ".join((it.get(k) or "").split()).casefold() for k in ("title", "summary"))


def exclude_reprints(items: list[dict], history: list[dict]) -> list[dict]:
    past = [_source_text(it) for day in history for it in day.get("items", []) if isinstance(it, dict)]
    exact = set(past)
    fresh = []
    for it in items:
        title, summary = _source_text(it)
        if title and (title, summary) in exact:
            continue
        # Un anuncio sin más contenido puede llegar después de la cobertura de
        # su lanzamiento. Exigir nombre/version completos y un lanzamiento previo afirmativo.
        bare = re.fullmatch(r"(?:introducing|presentamos) ([\w.-]+(?: [\w.-]+){1,5})", title)
        if bare and not summary and any(c.isdigit() for c in bare[1]):
            product = re.escape(bare[1])
            launch = re.compile(r"\b(?:launches|released|lanza|introducing) " + product + r"(?=$|[,:;!]| (?:with|at|in|for|to|as|con|para)\b)")
            if any(launch.search(t) and not UNCERTAIN.search(t) and not PENDING.search(t) for t, _ in past):
                continue
        fresh.append(it)
    return fresh


def title_fingerprint(title: str) -> str:
    base = re.sub(r"[^a-z0-9\s]", " ", (title or "").lower())
    tokens = [t for t in re.split(r"\s+", base) if t and len(t) > 2]
    return " ".join(tokens[:16])


def load_recent_history(data_dir: Path, today: str, days: int = 5) -> tuple[set[str], set[str]]:
    history_urls: set[str] = set()
    history_titles: set[str] = set()
    # Solo snapshots YYYY-MM-DD.json. Con el glob a pelo, image_cache.json (que
    # ordena despues de cualquier fecha) y los *.llm_cache.json ocupaban huecos
    # de la ventana y el historial real se quedaba en 4 ediciones o menos.
    snapshots = sorted((p for p in data_dir.glob("*.json") if _is_snapshot(p)), key=lambda p: p.name)
    recent = [p for p in snapshots if p.stem < today][-days:]

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
            for field in ("title", "title_es", "title_en"):
                tfp = title_fingerprint(it.get(field, ""))
                if tfp:
                    history_titles.add(tfp)

    return history_urls, history_titles


def load_recent_context(data_dir: Path, today: str, days: int = 2) -> tuple[list[set[str]], list[str]]:
    """Extrae tokens y titulares recientes (ultimos 2 dias) para dedup cruzado y prompt del LLM."""
    token_sets: list[set[str]] = []
    headlines: list[str] = []
    seen_hl: set[str] = set()
    snapshots = sorted((p for p in data_dir.glob("*.json") if _is_snapshot(p)), key=lambda p: p.name)
    recent = [p for p in snapshots if p.stem < today][-days:]

    for path in reversed(recent):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for it in data.get("items", []):
            if not isinstance(it, dict):
                continue
            for field in ("title", "title_es", "title_en"):
                toks = _story_words(it.get(field, ""))
                if len(toks) >= 4:
                    token_sets.append(toks)
            text = excerpt(it)
            if text and text not in seen_hl:
                seen_hl.add(text)
                headlines.append(text)

    return token_sets, headlines[:20]


def apply_novelty_penalty(
    items: list[dict],
    history_urls: set[str],
    history_titles: set[str],
    recent_token_sets: list[set[str]] | None = None,
) -> list[dict]:
    scored = []
    for it in items:
        base_score = int(it.get("heuristic_score", it.get("score", 0)) or 0)
        curl = canonical_url(it.get("link", ""))
        tfp = title_fingerprint(it.get("title", ""))

        repeated_url = bool(curl and curl in history_urls)
        repeated_title = bool(tfp and tfp in history_titles)
        repeated_story = False
        if not repeated_url and not repeated_title and recent_token_sets:
            toks = _story_words(it.get("title", ""))
            if len(toks) >= 4:
                for past_toks in recent_token_sets:
                    if len(past_toks) < 4:
                        continue
                    shared = len(toks & past_toks)
                    if shared >= 4 and (shared / min(len(toks), len(past_toks))) >= 0.72:
                        repeated_story = True
                        break

        is_repeat = repeated_url or repeated_title or repeated_story

        penalty = 0
        if repeated_url:
            penalty += 35
        if repeated_title:
            penalty += 20
        if repeated_story:
            penalty += 25

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
    has_hard_signal = any(
        k in text
        for k in [
            "price",
            "pricing",
            "capex",
            "opex",
            "datacenter",
            "hbm",
            "gpu",
            "training",
            "inference",
            "weights",
            "benchmark",
            "reasoning",
            "model",
            "gemini",
            "claude",
            "gpt",
            "llama",
            "grok",
            "release",
            "launch",
            "api",
            "agent",
            "agents",
            "multimodal",
            "checkpoint",
            "rubin",
        ]
    )
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


def _batch_fingerprint(payload: list[dict], recent_headlines: list[str] | None = None) -> str:
    inputs = ["evidence-v1-followups", payload, recent_headlines or []]
    return hashlib.sha256(json.dumps(inputs, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def is_fresh_enough(it: dict) -> bool:
    source = (it.get("source") or "").lower()
    age = item_age_days(it)
    if age is None:
        return True
    if any(s in source for s in ("nvidia", "google ai", "deepmind", "semiwiki")):
        return age <= 7
    return age <= 5


# Ultimo error del LLM en este run. Va al snapshot para que el aviso de dia
# degradado diga POR QUE ha fallado: el 2026-11-07 el motivo solo estaba en el
# log del run y el radar paso una semana degradado sin que nadie lo viera.
LLM_LAST_ERROR = ""


def generate_llm_data(
    candidates: list[dict],
    llm_cache: Path,
    llm_done: Path,
    recent_headlines: list[str] | None = None,
) -> tuple[dict, list]:
    global LLM_LAST_ERROR
    if not candidates:
        return {}, []
    llm_payload = []
    for idx, it in enumerate(candidates[:LLM_BATCH_SIZE], start=1):
        llm_payload.append({
            "id": idx,
            "source": it.get("source", ""),
            "title": it.get("title", ""),
            "summary": it.get("summary", ""),
            "url": it.get("link", ""),
        })
        it["_rid"] = idx

    current_fp = _batch_fingerprint(llm_payload, recent_headlines)
    results_map = {}
    briefings = []

    force_refresh = env_flag("FORCE_GEMINI_REFRESH", "0")

    stale_cache = False
    # Cache HIT
    if llm_cache.exists() and not force_refresh:
        try:
            cached = json.loads(llm_cache.read_text(encoding="utf-8"))
            cached_fp = cached.get("batch_fingerprint")
            if cached_fp != current_fp:
                stale_cache = True
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
        elif llm_done.exists() and not stale_cache and not env_flag("FORCE_GEMINI", "0"):
            print("Skipping Gemini: llm_done present (already attempted today).")
        else:
            gemini_ok = False
            last_err = None
            # Un fallo transitorio de la API dejaba el dia entero sin gate de
            # relevancia (ver 2026-08-22). Reintentamos antes de degradar.
            for attempt in (1, 2, 3):
                try:
                    out = (
                        rank_batch(llm_payload, recent_headlines=recent_headlines)
                        if recent_headlines
                        else rank_batch(llm_payload)
                    )
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
                llm_done.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
            else:
                LLM_LAST_ERROR = repr(last_err)[:500]
                print(f"GEMINI agotó los reintentos; el dia sera degradado. Ultimo error: {last_err!r}")

    return results_map, briefings


MAX_SIGNALS = 12     # techo de senales primarias
MAX_CONTEXT = 3      # capa secundaria de contexto reducida
MAX_REPEAT_SIGNALS = 3  # techo blando de repeats dentro de signals si hay senal fresca
# LEAD_SLOT_COUNT vive en src/config.py junto a demote_repeats_from_lead.

# Debe cubrir TODO el pool de candidatos. Si es menor, la cola queda sin juicio
# del LLM y no se puede publicar (ver el gate en apply_llm_results).
# El test test_llm_batch_covers_configured_caps ancla esto a la suma de caps
# de feeds.yaml: si subes un cap, sube este número.
LLM_BATCH_SIZE = 64

# Score minimo para que power_shift rescate un item que el LLM no marco signal.
# Sin umbral no filtra: el campo viene relleno en ~75% de los items.
POWER_SHIFT_FLOOR = 55


def _story_words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9áéíóúüñ]{4,}", (text or "").lower()))


def _norm_text(text: str) -> str:
    return re.sub(r"[^a-z0-9áéíóúüñ]+", " ", (text or "").lower()).strip()


def _syndicated_text(item: dict) -> tuple[str, str]:
    title, summary = _source_text(item)
    source = (item.get("source") or "").strip().casefold()
    if source:
        title = title.removesuffix(" - " + source)
        summary = summary.removesuffix(" - " + source)
    return title, "" if summary == title else summary


def same_story(a: dict, b: dict) -> bool:
    """¿Cuentan `a` y `b` el mismo suceso segun el juicio del LLM?

    El dedup de ingest compara titulares ORIGINALES, y un gran suceso llega con
    titulares que no se parecen ("The End of Jensen", "Jensen Out, MATCH Act
    In?"). Tras el LLM si hay señal fiable: o lo dice el propio modelo
    (same_story_as) o les ha escrito el mismo titular o el mismo so_what.
    """
    ra, rb = a.get("_rid"), b.get("_rid")
    sa, sb = a.get("_same_as") or 0, b.get("_same_as") or 0
    if ra is not None and rb is not None and (sa == rb or sb == ra or (sa and sa == sb)):
        return True

    if "evidence_kind" in a or "evidence_kind" in b:
        # Una republicación puede cambiar la firma o repetir el título como resumen.
        # Cualquier dato adicional de la fuente conserva su propia ficha.
        original = _syndicated_text(a)
        return bool(original[0]) and original == _syndicated_text(b)

    ta, tb = _norm_text(a.get("title_es")), _norm_text(b.get("title_es"))
    if ta and ta == tb:
        return True
    wa, wb = _norm_text(a.get("so_what")), _norm_text(b.get("so_what"))
    if len(wa) >= 40 and wa == wb:
        return True

    # Red de seguridad para titulares casi calcados. Es estricta a proposito:
    # con 0.75 el historico juntaba "noticias de mayo" con "noticias de junio"
    # y dos lanzamientos distintos de Gemini. Lo semantico lo decide el LLM.
    ka, kb = _story_words(a.get("title_es")), _story_words(b.get("title_es"))
    if len(ka) >= 5 and len(kb) >= 5 and len(ka & kb) / min(len(ka), len(kb)) >= 0.85:
        return True

    # Mismo hecho contado por el blog de un lab y por sus cuentas de X: titulares
    # distintos, pero comparten un nombre PROPIO del suceso (un modelo, una
    # persona; no "OpenAI" o "Nvidia") y las palabras clave del titular.
    # Visto el 2026-11-16: GPT-6 Astra y el Modelo Estandar, en 3 cards.
    ea = {str(e).strip().lower() for e in (a.get("entities") or []) if isinstance(e, str)}
    eb = {str(e).strip().lower() for e in (b.get("entities") or []) if isinstance(e, str)}
    # Solo nombres propios del suceso: varias palabras o con cifra ("GPT-6
    # Astra", "Jensen Huang"). Palabras sueltas como "flash" o "agents", que el
    # extractor antiguo tomaba por entidades, juntaban noticias distintas.
    specific = {e for e in (ea & eb) - GENERIC_ACTORS if " " in e or re.search(r"\d", e)}
    same_theme = (a.get("strategic_theme") or a.get("llm_theme")) == (b.get("strategic_theme") or b.get("llm_theme"))
    if specific and same_theme:
        skip = {w for e in specific for w in _story_words(e)}
        wa = (_story_words(a.get("title_es")) | _story_words(a.get("title_en"))) - skip - GENERIC_WORDS
        wb = (_story_words(b.get("title_es")) | _story_words(b.get("title_en"))) - skip - GENERIC_WORDS
        if len({w for w in wa & wb if not w.isdigit()}) >= 2:
            return True
    return False


# Actores que aparecen en muchas noticias distintas el mismo dia: compartirlos
# no indica que sea el mismo suceso.
GENERIC_ACTORS = {
    "openai", "anthropic", "google", "google deepmind", "deepmind", "meta", "microsoft", "nvidia",
    "amazon", "aws", "apple", "xai", "deepseek", "alibaba", "huawei", "tsmc", "intel", "amd",
    "mistral", "chatgpt", "claude", "gemini", "china", "estados unidos", "ee. uu.", "eeuu", "us", "usa",
    "large language models", "large language model", "llm", "llms", "ai", "ia", "inteligencia artificial",
    "artificial intelligence", "united states", "white house", "casa blanca",
}
GENERIC_WORDS = {"openai", "google", "anthropic", "nvidia", "nuevo", "nueva", "lanza", "launches", "para",
                 "with", "from", "sobre", "como", "modelo", "model", "models", "modelos",
                 "chip", "chips", "resumen", "análisis", "analysis", "nvidia", "meta", "apple", "agentes", "agents"}


def merge_same_story(ranked: list[dict]) -> int:
    """Fusiona los items que cuentan el mismo suceso. Devuelve cuantos se fusionan.

    `ranked` viene ordenado por score: el primero de cada suceso es la card que
    se publica; los demas quedan como verdict='duplicate' y pasan a su lista de
    "tambien en" (fuente + enlace), para no perder la cobertura.
    """
    leads: list[dict] = []
    merged = 0
    for it in ranked:
        if it.get("llm_score") is None or it.get("verdict") in ("noise", "unrated"):
            continue
        lead = next((x for x in leads if same_story(x, it)), None)
        if lead is None:
            leads.append(it)
            continue

        merged += 1
        it["verdict"] = "duplicate"
        lead_img = (lead.get("image_url") or "").strip()
        dup_img = (it.get("image_url") or "").strip()
        if not lead_img.startswith(("http://", "https://")) and dup_img.startswith(("http://", "https://")):
            lead["image_url"] = dup_img
        related = lead.setdefault("related", [])
        others = lead.setdefault("other_sources", [])
        for src, url in [(it.get("source"), it.get("url") or it.get("link") or "")] + [
            (r.get("source"), r.get("url") or "") for r in (it.get("related") or [])
        ]:
            if not src or src == lead.get("source"):
                continue
            if src not in others:
                others.append(src)
            if url and all(r.get("url") != url for r in related):
                related.append({"source": src, "url": url})
        for src in it.get("other_sources") or []:
            if src and src != lead.get("source") and src not in others:
                others.append(src)
    return merged


def apply_llm_results(candidates: list[dict], results_map: dict) -> list[dict]:
    reranked = []
    for it in candidates:
        rid = it.get("_rid")
        llm = results_map.get(str(rid)) or results_map.get(rid) # handle string/int keys

        if llm:
            # Contrato v2: juicio de relevancia, no score de impacto generico.
            it["llm_score"] = llm.get("relevance", llm.get("score"))
            it["verdict"] = (llm.get("verdict") or "signal").strip().lower()
            it["so_what"] = (llm.get("so_what") or "").strip()
            it["power_shift"] = (llm.get("power_shift") or "").strip()
            it["watch_next"] = (llm.get("watch_next") or "").strip()
            it["title_es"] = (llm.get("headline_es") or llm.get("title_es") or "").strip()
            it["llm_theme"] = (llm.get("theme") or "").strip()
            it["why"] = it["so_what"]          # alias legacy para render
            it["primary"] = llm.get("primary", it.get("primary", "misc"))
            it["tags"] = llm.get("tags", [])
            it["entities"] = llm.get("entities", [])
            it["_same_as"] = llm.get("same_story_as") or 0
            it["title_en"] = (llm.get("headline_en") or "").strip()
            it["so_what_en"] = (llm.get("so_what_en") or "").strip()
            it["power_shift_en"] = (llm.get("power_shift_en") or "").strip()
            it["watch_next_en"] = (llm.get("watch_next_en") or "").strip()
            if "evidence_kind" in llm:
                qualify_item(it, llm)
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

    # Antes del gate: si no, nueve cards del mismo suceso se comen los huecos
    # de MAX_SIGNALS y dejan fuera señales distintas.
    merged = merge_same_story(reranked)
    if merged:
        print(f"Mismo suceso: {merged} items fusionados en la card de su noticia principal.")

    # -- Gate de relevancia --------------------------------------------------
    signals = []
    context = []
    dropped = sum(1 for it in reranked if it.get("verdict") == "noise")
    unjudged = 0

    fresh_signals_available = sum(
        1
        for x in reranked
        if x.get("verdict") not in ("noise", "duplicate", "unrated")
        and x.get("llm_score") is not None
        and not x.get("is_repeat")
        and (
            x.get("verdict") == "signal"
            or (bool(x.get("power_shift")) and int(x.get("final_score") or 0) >= POWER_SHIFT_FLOOR)
        )
    )
    repeat_signals_count = 0

    for it in reranked:
        if it.get("verdict") in ("noise", "duplicate"):
            continue

        # Solo se envian al LLM los primeros LLM_BATCH_SIZE candidatos, asi que
        # la cola queda sin veredicto. Publicarla seria afirmar un filtrado que
        # no ha ocurrido: un item del puesto 25 que el LLM habria marcado noise
        # acababa en "Contexto" con score 0, como si hubiera sido evaluado.
        if it.get("verdict") == "unrated" or it.get("llm_score") is None:
            unjudged += 1
            continue

        # Se promueve a senal lo que el LLM juzgo asi. El power_shift solo
        # rescata items de relevancia alta: viene relleno en ~75% de los casos,
        # asi que sin umbral no filtraba nada.
        is_signal = (
            it.get("verdict") == "signal"
            or (bool(it.get("power_shift")) and int(it.get("final_score") or 0) >= POWER_SHIFT_FLOOR)
        )
        repeat_capped = (
            bool(it.get("is_repeat"))
            and fresh_signals_available >= 3
            and repeat_signals_count >= MAX_REPEAT_SIGNALS
        )
        if is_signal and not repeat_capped and len(signals) < MAX_SIGNALS:
            it["verdict"] = "signal"
            signals.append(it)
            if it.get("is_repeat"):
                repeat_signals_count += 1
        elif len(context) < MAX_CONTEXT:
            context.append(it)

    if unjudged:
        print(f"Gate: {unjudged} items descartados por no llegar al lote del LLM (sin veredicto).")

    gate_ran = any(it.get("verdict") in ("signal", "context", "noise") for it in reranked)

    if gate_ran:
        for it in signals:
            it["layer"] = "signal"
        for it in context:
            it["layer"] = "context"
        signals = demote_repeats_from_lead(signals, LEAD_SLOT_COUNT)
        final_items = signals + context
        print(f"Relevance gate: {len(signals)} signal / {len(context)} context / {dropped} noise descartados")
        if not final_items:
            print("Gate: dia sin senal - todo lo ingerido era ruido. Se muestra vacio a proposito.")
    else:
        # Sin veredictos (Gemini caido): modo degradado. No afirmamos relevancia
        # que no hemos podido juzgar; la UI avisa de que el filtro no se aplico.
        final_items = demote_repeats_from_lead(reranked[:10], LEAD_SLOT_COUNT)
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
            "thesis": "Sin datos suficientes para emitir una lectura del día.",
            "thesis_en": "Not enough data to give a reading of the day.",
            "signals": [],
            "risks": [],
            "watch": [],
            "entities_top": [],
        }

    top_items = sorted(final_items, key=lambda x: x.get("score", 0), reverse=True)[:3]
    lead_title = (top_items[0].get("title") or "").strip() if top_items else ""

    return {
        "thesis": "Análisis no disponible hoy: el filtro de relevancia no se ha aplicado.",
        "thesis_en": "Analysis unavailable today: the relevance filter was not applied.",
        "signals": [(it.get("title") or "").strip()[:130] for it in top_items if it.get("title")],
        "risks": [
            "Sin juicio del LLM no se puede distinguir señal de ruido: tratar todo como no verificado."
        ],
        "watch": ["Confirmar que el análisis vuelve a ejecutarse en el próximo run."],
        "entities_top": top_entities_list[:5],
    }


SNAPSHOT_DROP_KEYS = {"raw_title", "raw_summary", "_rid", "_same_as"}


def slim_item_for_snapshot(it: dict) -> dict:
    """Quita campos internos y recorta summary antes de commitear el JSON diario."""
    out = {k: v for k, v in it.items() if k not in SNAPSHOT_DROP_KEYS}
    out["summary"] = clip_text(out.get("summary") or "")
    return out


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

    today = radar_today_str()
    data_dir = Path("docs/data")
    data_dir.mkdir(parents=True, exist_ok=True)

    llm_done = data_dir / f"{today}.llm_done"
    llm_cache = data_dir / f"{today}.llm_cache.json"

    # 1) Ingest
    items, x_layer = ingest_feeds(cfg, per_source_cap)

    # 1.5) Source health - una fuente muerta debe ser visible, no fallar en silencio.
    #      La capa X se reporta aparte: 0 posts no es "6 cuentas muertas".
    configured = [s.get("name", "?") for s in cfg.get("sources", [])]
    source_health = build_source_health(configured, items, x_layer)
    print(f"Source health: {source_health['alive']}/{source_health['configured']} vivas")
    if source_health["dead"]:
        print(f"  SIN ITEMS: {', '.join(source_health['dead'])}")

    # 2) Dedup
    history = load_history(data_dir, today=today, days=10)
    deduped = exclude_reprints(dedup_items(items), history[-5:])

    # 2.5) Novelty (anti-repeticion respecto ultimos dias)
    history_urls, history_titles = load_recent_history(data_dir, today=today, days=5)
    recent_token_sets, recent_headlines = load_recent_context(data_dir, today=today, days=2)
    deduped = apply_novelty_penalty(deduped, history_urls, history_titles, recent_token_sets=recent_token_sets)

    before_age = len(deduped)
    deduped = [it for it in deduped if is_fresh_enough(it)]
    dropped_age = before_age - len(deduped)
    if dropped_age:
        print(f"Age filter: removed {dropped_age} stale items exceeding freshness threshold.")

    # 3) Preselect
    deduped.sort(key=lambda x: x.get("adjusted_score", x.get("score", 0)), reverse=True)
    candidates = deduped[:LLM_BATCH_SIZE]

    from src.fetch import enrich_items_with_images

    # 4) LLM Rank
    recent_headlines = with_open_stories(recent_headlines, history, candidates)
    results_map, briefings = generate_llm_data(candidates, llm_cache, llm_done, recent_headlines=recent_headlines)

    # 5) Apply LLM Results (gate de relevancia)
    final_items = apply_llm_results(candidates, results_map)
    # og:image solo para lo que se publica (~13 items), no para los 56 candidatos.
    final_items = enrich_items_with_images(final_items)

    # 6) Stats & Fallback Briefing
    score_avg, primary_dist, top_entities = calculate_stats(final_items)
    top_entities_list = [e for e, _ in top_entities]

    if briefings:
        briefing = merge_briefings(briefings, final_items)
    else:
        briefing = generate_fallback_briefing(final_items, primary_dist, top_entities_list)

    # 6.5) Memoria: continuidad entre dias. Determinista, sobrevive a fallos del LLM.
    degraded = not results_map and (bool(candidates) or not items)
    try:
        memory = {
            "watch_resolved": resolve_watchlist(history, final_items),
            "entity_deltas": entity_deltas(history, final_items, known_before(data_dir, today)),
            "threads": detect_threads(history, final_items),
        }
        level_label, level_class = activity_level(final_items, degraded=degraded)
    except Exception:
        print("MEMORY layer FAILED (traceback):")
        traceback.print_exc()
        memory = {"watch_resolved": [], "entity_deltas": {}, "threads": []}
        level_label, level_class = ("SIN FILTRAR", "quiet")

    try:
        memory["followups"] = followups(today, history, final_items, results_map, recent_headlines)
    except Exception:
        traceback.print_exc()
        memory["followups"] = previous_state(history)

    # Indicadores propios: pulso de la carrera y quien la mueve. Accesorios:
    # si fallan, la edicion sale igual sin ellos.
    pulse, who_moves = {}, []
    if not degraded:
        try:
            from src.pulse import HISTORY_EDITIONS, movers, pulse_block
            long_history = load_history(data_dir, today=today, days=HISTORY_EDITIONS + 10)
            pulse = pulse_block(long_history, final_items, today)
            who_moves = movers(long_history, final_items)
            from src.pulse import activity_from_pulse
            level_label, level_class = activity_from_pulse(pulse, (level_label, level_class))
        except Exception:
            print("PULSE FAILED (traceback):")
            traceback.print_exc()

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
        "pulse": pulse,
        "movers": who_moves,
        "activity": {"label": level_label, "class": level_class},
        "source_health": source_health,
        "x_layer": x_layer,
        "degraded": degraded,
        "llm_error": LLM_LAST_ERROR if degraded else "",
        # candidates fue mutado in-place por apply_llm_results, asi que lleva los veredictos
        "dropped_noise": sum(1 for it in candidates if it.get("verdict") == "noise"),
        "merged_duplicates": sum(1 for it in candidates if it.get("verdict") == "duplicate"),
        "counts": {
            "signal": sum(1 for it in final_items if it.get("layer") == "signal"),
            "context": sum(1 for it in final_items if it.get("layer") == "context"),
        },
        "items": [slim_item_for_snapshot(it) for it in final_items],
    }

    Path(f"docs/data/{today}.json").write_text(
        json.dumps(daily_snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # 8) Render HTML
    # El panel de mercado es accesorio: una API de terceros caida no puede
    # impedir que se publique el radar. Sin el try, un fallo aqui dejaba el
    # snapshot escrito pero el index.html sin regenerar, con la web congelada.
    try:
        from src.market import get_market_overview
        market_data = get_market_overview()
    except Exception:
        print("MARKET panel FAILED (traceback):")
        traceback.print_exc()
        market_data = None

    # Publicar las mismas cotizaciones ya consultadas para NEXUS NEWTAB.
    # No repetir la consulta a Yahoo/CoinGecko ni llamar a Gemini.
    try:
        from src.newtab_market import publish_market
        publish_market(market_data)
    except Exception:
        print("NEXUS MARKET publication failed (non-blocking):")
        traceback.print_exc()

    page = render_index(final_items, briefing=briefing, snapshot=daily_snapshot, market=market_data)
    Path("docs").mkdir(exist_ok=True)
    Path("docs/index.html").write_text(page, encoding="utf-8")

    # 9) Weekly
    try:
        from src.weekly import main as weekly_main
        weekly_main()
        print("WEEKLY OK -> docs/weekly.html")
    except Exception:
        print("WEEKLY FAILED (traceback):")
        traceback.print_exc()

    # 10) Archivo: índice + una página por snapshot. No llama a Gemini.
    try:
        from src.archive import write_archive
        n_days = write_archive(Path("docs"))
        print(f"ARCHIVO OK -> docs/archivo.html ({n_days} días)")
    except Exception:
        print("ARCHIVO FAILED (traceback):")
        traceback.print_exc()


if __name__ == "__main__":
    main()
