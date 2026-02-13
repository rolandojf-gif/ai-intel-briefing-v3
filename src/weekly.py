from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple
import math

DATA_DIR = Path("docs/data")
OUT_HTML = Path("docs/weekly.html")

# Ajusta alias según tu dominio (IA/semis/política tech/etc.)
ENTITY_ALIASES = {
    "open ai": "OpenAI",
    "anthropic ai": "Anthropic",
    "google deepmind": "DeepMind",
    "nvidia corp": "NVIDIA",
    "advanced micro devices": "AMD",
}
CATEGORY_ALIASES = {
    "semiconductors": "hardware",
    "chips": "hardware",
    "datacenter": "infrastructure",
    "cybersecurity": "security",
}

STOP_ENTITIES = {
    "ai", "genai", "llm", "cloud", "data", "chip", "chips", "model", "models"
}

def list_latest_json(n: int = 7) -> List[Path]:
    if not DATA_DIR.exists():
        return []
    files = sorted(DATA_DIR.glob("*.json"))
    # Espera formato YYYY-MM-DD.json
    def key(p: Path):
        try:
            return datetime.strptime(p.stem, "%Y-%m-%d")
        except ValueError:
            return datetime.min
    files = sorted(files, key=key)
    return files[-n:]

def norm_entity(e: str) -> str:
    e2 = re.sub(r"\s+", " ", e.strip())
    if not e2:
        return ""
    low = e2.lower()
    if low in ENTITY_ALIASES:
        return ENTITY_ALIASES[low]
    # Title Case suave, salvo acrónimos
    if e2.isupper() and len(e2) <= 6:
        return e2
    # Conserva casing común de marcas conocidas si aparecen
    return e2

def norm_category(c: str) -> str:
    c2 = re.sub(r"\s+", " ", (c or "").strip().lower())
    return CATEGORY_ALIASES.get(c2, c2 or "uncategorized")

def safe_get_item_entities(item: Dict[str, Any]) -> List[str]:
    ents = item.get("entities")
    if isinstance(ents, list) and ents:
        out = []
        for e in ents:
            if not isinstance(e, str):
                continue
            ne = norm_entity(e)
            if ne and ne.lower() not in STOP_ENTITIES:
                out.append(ne)
        return dedupe_preserve_order(out)

    # fallback ultra-simple: capitalizadas / tickers
    text = " ".join([
        str(item.get("title", "")),
        str(item.get("summary", "")),
    ])
    cand = re.findall(r"\b([A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]{2,}){0,2})\b", text)
    tick = re.findall(r"\b([A-Z]{2,5})\b", text)
    merged = cand + tick
    out = []
    for e in merged:
        ne = norm_entity(e)
        if not ne:
            continue
        if ne.lower() in STOP_ENTITIES:
            continue
        out.append(ne)
    return dedupe_preserve_order(out)[:12]

def dedupe_preserve_order(xs: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in xs:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out

def recency_weights(k: int) -> List[float]:
    # pesos crecientes hacia el final (día más reciente pesa más)
    # ejemplo 7 días: [0.7,0.8,0.9,1.0,1.15,1.3,1.5]
    base = 0.7
    step = 0.1
    w = [base + i * step for i in range(k)]
    # boost final suave
    w[-3:] = [w[-3]*1.05, w[-2]*1.15, w[-1]*1.25]
    return w

def load_week() -> Tuple[List[str], List[List[Dict[str, Any]]]]:
    files = list_latest_json(7)
    days = [p.stem for p in files]
    all_items_by_day: List[List[Dict[str, Any]]] = []
    for p in files:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            data = []
        # soporta schema: {"items":[...]} o lista directa
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            items = data["items"]
        elif isinstance(data, list):
            items = data
        else:
            items = []
        # normaliza category/entities en caliente
        normed = []
        for it in items:
            if not isinstance(it, dict):
                continue
            it2 = dict(it)
            it2["category"] = norm_category(it2.get("category", "uncategorized"))
            it2["entities_norm"] = safe_get_item_entities(it2)
            normed.append(it2)
        all_items_by_day.append(normed)
    return days, all_items_by_day

def count_series(all_items_by_day: List[List[Dict[str, Any]]]) -> Tuple[Dict[str, List[int]], Dict[str, List[int]]]:
    # entity_counts[entity] = [d1,d2,...]
    # cat_counts[cat] = [d1,d2,...]
    entity_counts: Dict[str, List[int]] = {}
    cat_counts: Dict[str, List[int]] = {}

    for di, items in enumerate(all_items_by_day):
        # categorías
        local_cat: Dict[str, int] = {}
        # entidades
        local_ent: Dict[str, int] = {}

        for it in items:
            c = it.get("category", "uncategorized")
            local_cat[c] = local_cat.get(c, 0) + 1

            for e in it.get("entities_norm", []):
                local_ent[e] = local_ent.get(e, 0) + 1

        for c, v in local_cat.items():
            cat_counts.setdefault(c, [0]*len(all_items_by_day))[di] = v
        for e, v in local_ent.items():
            entity_counts.setdefault(e, [0]*len(all_items_by_day))[di] = v

    return entity_counts, cat_counts

def slope(xs: List[int]) -> float:
    # pendiente lineal simple (least squares) sobre índices 0..n-1
    n = len(xs)
    if n < 2:
        return 0.0
    x = list(range(n))
    mx = sum(x)/n
    my = sum(xs)/n
    num = sum((xi-mx)*(yi-my) for xi, yi in zip(x, xs))
    den = sum((xi-mx)**2 for xi in x) or 1.0
    return num/den

def momentum(counts: List[int], weights: List[float]) -> float:
    # recency-weighted freq + burst vs media
    if not counts:
        return 0.0
    wsum = sum(c*w for c, w in zip(counts, weights))
    avg = sum(counts)/len(counts)
    last = counts[-1]
    burst = (last - avg) / (avg + 1e-6)
    return wsum + 2.0 * burst

def streak(counts: List[int]) -> int:
    s = 0
    for v in reversed(counts):
        if v > 0:
            s += 1
        else:
            break
    return s

def select_top_signals(entity_counts: Dict[str, List[int]], cat_counts: Dict[str, List[int]]) -> Dict[str, Any]:
    k = len(next(iter(cat_counts.values()))) if cat_counts else 7
    w = recency_weights(k)

    ent_rows = []
    for e, series in entity_counts.items():
        ent_rows.append({
            "name": e,
            "series": series,
            "momentum": momentum(series, w),
            "streak": streak(series),
            "total": sum(series),
            "slope": slope(series),
        })
    ent_rows.sort(key=lambda r: (r["momentum"], r["streak"], r["total"]), reverse=True)

    cat_rows = []
    for c, series in cat_counts.items():
        total = sum(series)
        cat_rows.append({
            "name": c,
            "series": series,
            "momentum": momentum(series, w),
            "streak": streak(series),
            "total": total,
            "slope": slope(series),
        })
    cat_rows.sort(key=lambda r: (r["momentum"], r["slope"], r["total"]), reverse=True)

    return {
        "top_entities": ent_rows[:15],
        "top_categories": cat_rows[:10],
    }

def pick_items_for_entity(all_items_by_day: List[List[Dict[str, Any]]], entity: str, limit: int = 6) -> List[Dict[str, Any]]:
    hits = []
    for items in reversed(all_items_by_day):
        for it in items:
            if entity in (it.get("entities_norm") or []):
                hits.append(it)
                if len(hits) >= limit:
                    return hits
    return hits

def render_weekly(days: List[str], all_items_by_day: List[List[Dict[str, Any]]]) -> str:
    entity_counts, cat_counts = count_series(all_items_by_day)
    signals = select_top_signals(entity_counts, cat_counts)

    # “Implicaciones” minimalistas: reglas duras, cero poesía.
    # Si luego quieres, lo elevamos con un mini-prompt a Gemini, pero primero que funcione.
    implications = []
    if signals["top_categories"]:
        c0 = signals["top_categories"][0]
        if c0["slope"] > 0.3 and c0["streak"] >= 3:
            implications.append(f"Señal: la categoría '{c0['name']}' está acelerando (streak {c0['streak']} días, pendiente {c0['slope']:.2f}). Probable re-priorización del ciclo informativo hacia ese frente.")
    if signals["top_entities"]:
        e0 = signals["top_entities"][0]
        if e0["streak"] >= 3:
            implications.append(f"Entidad caliente: '{e0['name']}' aparece de forma sostenida (streak {e0['streak']} días). Esto suele correlacionar con 'tema tractor' o anuncio en cascada.")
    if not implications:
        implications.append("Semana plana: no hay aceleraciones claras. Eso es señal en sí misma (o el filtro está demasiado estricto).")

    # HTML simple, legible, imprimible
    def spark(series: List[int]) -> str:
        # mini “sparkline” textual
        bars = "▁▂▃▄▅▆▇█"
        m = max(series) if series else 1
        out = ""
        for v in series:
            idx = 0 if m == 0 else int(round((v/m) * (len(bars)-1)))
            out += bars[idx]
        return out

    top_entities_html = []
    for r in signals["top_entities"]:
        top_entities_html.append(
            f"<li><span class='k'>{r['name']}</span> "
            f"<span class='s'>{spark(r['series'])}</span> "
            f"<span class='m'>mom {r['momentum']:.2f} · streak {r['streak']} · total {r['total']}</span></li>"
        )

    top_cats_html = []
    for r in signals["top_categories"]:
        top_cats_html.append(
            f"<li><span class='k'>{r['name']}</span> "
            f"<span class='s'>{spark(r['series'])}</span> "
            f"<span class='m'>mom {r['momentum']:.2f} · slope {r['slope']:.2f} · total {r['total']}</span></li>"
        )

    clusters_html = []
    for r in signals["top_entities"][:5]:
        items = pick_items_for_entity(all_items_by_day, r["name"], limit=6)
        li = []
        for it in items:
            title = (it.get("title") or "").strip()
            url = (it.get("url") or it.get("link") or "").strip()
            src = (it.get("source") or "").strip()
            cat = (it.get("category") or "").strip()
            if url:
                li.append(f"<li><a href='{url}' target='_blank' rel='noopener'>{title}</a> <span class='meta'>[{src}] [{cat}]</span></li>")
            else:
                li.append(f"<li>{title} <span class='meta'>[{src}] [{cat}]</span></li>")
        clusters_html.append(
            f"<section class='card'><h3>{r['name']}</h3><ul>{''.join(li)}</ul></section>"
        )

    period = f"{days[0]} → {days[-1]}" if days else "sin datos"

    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Weekly Radar · {period}</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 0; background: #0b0e14; color: #e6edf3; }}
    header {{ padding: 20px; border-bottom: 1px solid #222; background: #0b0e14; position: sticky; top: 0; }}
    .wrap {{ max-width: 1100px; margin: 0 auto; padding: 18px; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
    .card {{ background: #0f1420; border: 1px solid #1f2a3a; border-radius: 14px; padding: 14px; }}
    h1 {{ margin: 0 0 6px 0; font-size: 18px; }}
    h2 {{ margin: 0 0 10px 0; font-size: 15px; color: #cbd5e1; }}
    h3 {{ margin: 0 0 10px 0; font-size: 14px; }}
    ul {{ margin: 0; padding-left: 18px; }}
    li {{ margin: 6px 0; line-height: 1.25rem; }}
    a {{ color: #8ab4f8; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .k {{ font-weight: 600; }}
    .s {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; margin-left: 8px; }}
    .m {{ color: #9aa4b2; margin-left: 8px; font-size: 12px; }}
    .meta {{ color: #9aa4b2; font-size: 12px; margin-left: 6px; }}
    .imp li {{ color: #e6edf3; }}
    footer {{ padding: 20px; color: #9aa4b2; font-size: 12px; }}
    @media (max-width: 900px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
<header>
  <div class="wrap">
    <h1>Weekly Radar · {period}</h1>
    <div style="color:#9aa4b2; font-size:12px">Ventana: últimos {len(days)} días · Fuente: docs/data/*.json</div>
  </div>
</header>

<main class="wrap">
  <div class="grid">
    <section class="card">
      <h2>Entidades con momentum</h2>
      <ul>
        {''.join(top_entities_html) if top_entities_html else "<li>Sin datos</li>"}
      </ul>
    </section>

    <section class="card">
      <h2>Categorías en ascenso</h2>
      <ul>
        {''.join(top_cats_html) if top_cats_html else "<li>Sin datos</li>"}
      </ul>
    </section>
  </div>

  <section class="card" style="margin-top:14px">
    <h2>Implicaciones estratégicas</h2>
    <ul class="imp">
      {''.join(f"<li>{x}</li>" for x in implications)}
    </ul>
  </section>

  <section style="margin-top:14px">
    <h2>Clusters (top entidades)</h2>
    <div class="grid">
      {''.join(clusters_html) if clusters_html else "<div class='card'>Sin clusters</div>"}
    </div>
  </section>
</main>

<footer class="wrap">
  Generado automáticamente · Si esto parece un agregador, es que el scoring aún es flojo.
</footer>
</body>
</html>
"""

def main():
    days, all_items_by_day = load_week()
    html = render_weekly(days, all_items_by_day)
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"OK -> {OUT_HTML}")

if __name__ == "__main__":
    main()
