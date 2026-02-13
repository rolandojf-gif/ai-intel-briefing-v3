from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List

DATA_DIR = Path("docs/data")
OUT_HTML = Path("docs/weekly.html")


def parse_date(stem: str) -> datetime:
    try:
        return datetime.strptime(stem, "%Y-%m-%d")
    except ValueError:
        return datetime.min


def list_latest(n: int = 7) -> List[Path]:
    if not DATA_DIR.exists():
        return []
    files = [p for p in DATA_DIR.glob("*.json") if p.is_file()]
    files.sort(key=lambda p: parse_date(p.stem))
    return files[-n:]


def load_day(p: Path) -> Dict[str, Any]:
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("date", p.stem)
            data.setdefault("items", [])
            return data
    except Exception:
        pass
    return {"date": p.stem, "items": []}


def slope(xs: List[int]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    x = list(range(n))
    mx = sum(x) / n
    my = sum(xs) / n
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, xs))
    den = sum((xi - mx) ** 2 for xi in x) or 1.0
    return num / den


def streak(xs: List[int]) -> int:
    s = 0
    for v in reversed(xs):
        if v > 0:
            s += 1
        else:
            break
    return s


def spark(series: List[int]) -> str:
    bars = "▁▂▃▄▅▆▇█"
    m = max(series) if series else 0
    if m == 0:
        return "▁" * len(series)
    out = ""
    for v in series:
        idx = int(round((v / m) * (len(bars) - 1)))
        out += bars[idx]
    return out


def pick_items_for_entity(
    snapshots: List[Dict[str, Any]],
    entity: str,
    limit: int = 6
) -> List[Dict[str, Any]]:
    hits = []
    for snap in reversed(snapshots):
        for it in (snap.get("items", []) or []):
            if not isinstance(it, dict):
                continue
            ents = it.get("entities") or []
            if entity in ents:
                hits.append(it)
                if len(hits) >= limit:
                    return hits
    return hits


def main():
    files = list_latest(7)
    if not files:
        OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
        OUT_HTML.write_text("<html><body><p>No data.</p></body></html>", encoding="utf-8")
        return

    days = [p.stem for p in files]
    snapshots = [load_day(p) for p in files]

    ent_series: Dict[str, List[int]] = {}
    cat_series: Dict[str, List[int]] = {}

    for di, snap in enumerate(snapshots):
        items = snap.get("items", []) or []

        local_ent: Dict[str, int] = {}
        local_cat: Dict[str, int] = {}

        for it in items:
            if not isinstance(it, dict):
                continue

            cat = (it.get("primary") or "misc").strip()
            local_cat[cat] = local_cat.get(cat, 0) + 1

            for e in (it.get("entities") or []):
                if isinstance(e, str) and e.strip():
                    e2 = e.strip()
                    local_ent[e2] = local_ent.get(e2, 0) + 1

        for c, v in local_cat.items():
            cat_series.setdefault(c, [0] * len(snapshots))[di] = v
        for e, v in local_ent.items():
            ent_series.setdefault(e, [0] * len(snapshots))[di] = v

    ent_rows = [{
        "name": e,
        "series": series,
        "total": sum(series),
        "streak": streak(series),
        "slope": slope(series),
    } for e, series in ent_series.items()]
    ent_rows.sort(key=lambda r: (r["streak"], r["total"], r["slope"]), reverse=True)

    cat_rows = [{
        "name": c,
        "series": series,
        "total": sum(series),
        "streak": streak(series),
        "slope": slope(series),
    } for c, series in cat_series.items()]
    cat_rows.sort(key=lambda r: (r["slope"], r["total"], r["streak"]), reverse=True)

    top_entities = ent_rows[:12]
    top_cats = cat_rows[:8]

    dominant = top_cats[0] if top_cats else None
    hot_ent = top_entities[0] if top_entities else None

    implications = []
    if dominant and dominant["slope"] > 0.25 and dominant["streak"] >= 3:
        implications.append(
            f"La categoría '{dominant['name']}' acelera (slope {dominant['slope']:.2f}, streak {dominant['streak']}d)."
        )
    if hot_ent and hot_ent["streak"] >= 3:
        implications.append(
            f"Entidad caliente: '{hot_ent['name']}' mantiene presencia (streak {hot_ent['streak']}d)."
        )
    if not implications:
        implications.append("No hay aceleraciones claras en esta ventana.")

    ent_li = "\n".join(
        f"<li><span class='k'>{r['name']}</span> <span class='s'>{spark(r['series'])}</span>"
        f"<span class='m'>streak {r['streak']} · total {r['total']} · slope {r['slope']:.2f}</span></li>"
        for r in top_entities
    ) or "<li>Sin datos</li>"

    cat_li = "\n".join(
        f"<li><span class='k'>{r['name']}</span> <span class='s'>{spark(r['series'])}</span>"
        f"<span class='m'>slope {r['slope']:.2f} · total {r['total']} · streak {r['streak']}</span></li>"
        for r in top_cats
    ) or "<li>Sin datos</li>"

    imp_li = "\n".join(f"<li>{x}</li>" for x in implications)

    clusters = []
    for r in top_entities[:5]:
        entity = r["name"]
        items = pick_items_for_entity(snapshots, entity, limit=6)
        li = []
        for it in items:
            title = (it.get("title") or "").strip()
            url = (it.get("url") or it.get("link") or "").strip()
            src = (it.get("source") or "").strip()
            cat = (it.get("primary") or "misc").strip()
            if url:
                li.append(f"<li><a href='{url}' target='_blank' rel='noopener'>{title}</a> <span class='m'>[{src}] [{cat}]</span></li>")
            else:
                li.append(f"<li>{title} <span class='m'>[{src}] [{cat}]</span></li>")
        clusters.append(f"<section class='card'><h2>{entity}</h2><ul>{''.join(li)}</ul></section>")

    clusters_html = "<div class='grid'>" + "".join(clusters) + "</div>" if clusters else ""

    period = f"{days[0]} → {days[-1]}"

    html = f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Weekly Radar · {period}</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin:0; background:#0b0e14; color:#e6edf3; }}
    header {{ padding:20px; border-bottom:1px solid #222; background:#0b0e14; position:sticky; top:0; }}
    .wrap {{ max-width:1100px; margin:0 auto; padding:18px; }}
    .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
    .card {{ background:#0f1420; border:1px solid #1f2a3a; border-radius:14px; padding:14px; }}
    h1 {{ margin:0 0 6px 0; font-size:18px; }}
    h2 {{ margin:0 0 10px 0; font-size:15px; color:#cbd5e1; }}
    ul {{ margin:0; padding-left:18px; }}
    li {{ margin:6px 0; line-height:1.25rem; }}
    a {{ color:#8ab4f8; text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
    .k {{ font-weight:600; }}
    .s {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; margin-left:8px; }}
    .m {{ color:#9aa4b2; margin-left:8px; font-size:12px; }}
    @media (max-width:900px) {{ .grid {{ grid-template-columns:1fr; }} }}
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
      <h2>Entidades repetidas (streak)</h2>
      <ul>{ent_li}</ul>
    </section>

    <section class="card">
      <h2>Categorías en ascenso (primary)</h2>
      <ul>{cat_li}</ul>
    </section>
  </div>

  <section class="card" style="margin-top:14px">
    <h2>Implicaciones estratégicas</h2>
    <ul>{imp_li}</ul>
  </section>

  <section style="margin-top:14px">
    <h2 style="color:#cbd5e1; font-size:15px; margin:0 0 10px 0;">Clusters (top entidades)</h2>
    {clusters_html}
  </section>
</main>

</body>
</html>
"""

    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
