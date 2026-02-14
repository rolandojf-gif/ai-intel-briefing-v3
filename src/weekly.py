# src/weekly.py
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Tuple

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


def slope(xs: List[float]) -> float:
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


def recency_weights(n: int, halflife_days: float = 3.0) -> List[float]:
    # newest has weight 1.0; older decays with half-life
    if n <= 0:
        return []
    w = []
    for i in range(n):
        age = (n - 1) - i
        w.append(0.5 ** (age / halflife_days))
    return w


def weighted_total(series: List[int], weights: List[float]) -> float:
    return sum(v * w for v, w in zip(series, weights))


def delta_recent_vs_early(series: List[int], weights: List[float]) -> float:
    n = len(series)
    if n < 4:
        return 0.0
    k = min(3, n // 2)  # compara ~3 últimos vs ~3 primeros (si hay pocos días, se adapta)
    early = sum(series[i] * weights[i] for i in range(k))
    recent = sum(series[n - k + i] * weights[n - k + i] for i in range(k))
    return recent - early


def hhi_from_counts(counts: Dict[str, float]) -> float:
    total = sum(counts.values()) or 0.0
    if total <= 0:
        return 0.0
    return sum((v / total) ** 2 for v in counts.values())


def top_share(counts: Dict[str, float], topn: int = 3) -> float:
    total = sum(counts.values()) or 0.0
    if total <= 0:
        return 0.0
    vals = sorted(counts.values(), reverse=True)[:topn]
    return sum(vals) / total


def pick_items_for_entity(snapshots: List[Dict[str, Any]], entity: str, limit: int = 6) -> List[Dict[str, Any]]:
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


def pick_items_for_category(snapshots: List[Dict[str, Any]], category: str, limit: int = 6) -> List[Dict[str, Any]]:
    hits = []
    for snap in reversed(snapshots):
        for it in (snap.get("items", []) or []):
            if not isinstance(it, dict):
                continue
            cat = (it.get("primary") or "misc").strip()
            if cat == category:
                hits.append(it)
                if len(hits) >= limit:
                    return hits
    return hits


def html_escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main():
    files = list_latest(7)
    if not files:
        OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
        OUT_HTML.write_text("<html><body><p>No data.</p></body></html>", encoding="utf-8")
        return

    days = [p.stem for p in files]
    snapshots = [load_day(p) for p in files]
    n = len(snapshots)
    weights = recency_weights(n, halflife_days=3.0)

    ent_series: Dict[str, List[int]] = {}
    cat_series: Dict[str, List[int]] = {}
    total_items_per_day: List[int] = []

    # Construye series
    for di, snap in enumerate(snapshots):
        items = snap.get("items", []) or []
        total_items_per_day.append(len(items))

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
            cat_series.setdefault(c, [0] * n)[di] = v
        for e, v in local_ent.items():
            ent_series.setdefault(e, [0] * n)[di] = v

    # Metrics por entidad
    ent_rows = []
    ent_weighted_counts: Dict[str, float] = {}
    for e, series in ent_series.items():
        wt = weighted_total(series, weights)
        ent_weighted_counts[e] = wt
        ent_rows.append({
            "name": e,
            "series": series,
            "total": sum(series),
            "streak": streak(series),
            "slope": slope([float(x) for x in series]),
            "w_total": wt,
            "delta": delta_recent_vs_early(series, weights),
            "last": series[-1] if series else 0,
        })

    # Momentum ranking entidades: ponderado + delta (reciente vs temprano)
    ent_rows.sort(key=lambda r: (r["w_total"], r["delta"], r["streak"], r["total"]), reverse=True)

    # Metrics por categoría
    cat_rows = []
    cat_weighted_counts: Dict[str, float] = {}
    cat_share_series: Dict[str, List[float]] = {}

    for c, series in cat_series.items():
        wt = weighted_total(series, weights)
        cat_weighted_counts[c] = wt
        shares = []
        for i, v in enumerate(series):
            denom = total_items_per_day[i] or 1
            shares.append(v / denom)
        cat_share_series[c] = shares

        cat_rows.append({
            "name": c,
            "series": series,
            "share": shares,
            "total": sum(series),
            "streak": streak(series),
            "slope": slope([float(x) for x in series]),
            "share_slope": slope(shares),
            "w_total": wt,
            "delta_share": delta_recent_vs_early([int(round(s * 1000)) for s in shares], weights),  # proxy
        })

    # Momentum ranking categorías: share_slope + w_total
    cat_rows.sort(key=lambda r: (r["share_slope"], r["w_total"], r["total"], r["streak"]), reverse=True)

    # Rotación narrativa: compara share reciente vs temprano (promedios)
    k = min(3, max(1, n // 2))
    rot = []
    for r in cat_rows:
        s = r["share"]
        if len(s) < 2:
            continue
        early = sum(s[:k]) / k
        recent = sum(s[-k:]) / k
        rot.append({
            "name": r["name"],
            "early": early,
            "recent": recent,
            "delta": recent - early,
            "series": r["series"],
        })
    rot.sort(key=lambda x: x["delta"], reverse=True)

    risers = rot[:5]
    fallers = list(reversed(rot[-5:])) if len(rot) >= 5 else list(reversed(rot))

    # Concentración (HHI) en menciones ponderadas
    ent_hhi = hhi_from_counts(ent_weighted_counts)
    cat_hhi = hhi_from_counts(cat_weighted_counts)
    ent_top3 = top_share(ent_weighted_counts, 3)
    cat_top3 = top_share(cat_weighted_counts, 3)

    # New entrants: 0 en primeros (n-k) días, aparece en últimos k días
    new_k = min(3, n)
    new_ents = []
    for r in ent_rows:
        s = r["series"]
        if sum(s[:max(0, n - new_k)]) == 0 and sum(s[-new_k:]) > 0:
            new_ents.append(r)
    new_ents.sort(key=lambda r: (r["w_total"], r["last"], r["delta"]), reverse=True)
    new_ents = new_ents[:8]

    # Breakouts: última jornada >=2 y antes casi nada
    breakouts = []
    for r in ent_rows:
        s = r["series"]
        if not s:
            continue
        last = s[-1]
        prev_avg = (sum(s[:-1]) / max(1, (len(s) - 1)))
        if last >= 2 and prev_avg <= 0.5:
            breakouts.append(r)
    breakouts.sort(key=lambda r: (r["last"], r["w_total"], r["delta"]), reverse=True)
    breakouts = breakouts[:8]

    # Implicaciones (directas, sin poesía)
    implications = []
    dominant = cat_rows[0] if cat_rows else None
    hot_ent = ent_rows[0] if ent_rows else None

    if dominant:
        implications.append(
            f"Dominante: {dominant['name']} (share_slope {dominant['share_slope']:.3f}, w_total {dominant['w_total']:.2f})."
        )
    if hot_ent:
        implications.append(
            f"Tractor: {hot_ent['name']} (w_total {hot_ent['w_total']:.2f}, delta {hot_ent['delta']:.2f}, streak {hot_ent['streak']}d)."
        )

    if ent_hhi >= 0.18:
        implications.append(f"Concentración alta en entidades (HHI {ent_hhi:.3f}). Señal: narrativa dominada por pocos actores.")
    else:
        implications.append(f"Concentración moderada en entidades (HHI {ent_hhi:.3f}).")

    if cat_hhi >= 0.25:
        implications.append(f"Concentración alta en categorías (HHI {cat_hhi:.3f}). Señal: el radar se está yendo a un tema único.")
    else:
        implications.append(f"Concentración moderada en categorías (HHI {cat_hhi:.3f}).")

    # HTML blocks
    def li_entity(r):
        return (
            f"<li><span class='k'>{html_escape(r['name'])}</span> "
            f"<span class='s'>{spark(r['series'])}</span>"
            f"<span class='m'>w {r['w_total']:.2f} · Δ {r['delta']:.2f} · streak {r['streak']} · total {r['total']}</span></li>"
        )

    def li_cat(r):
        return (
            f"<li><span class='k'>{html_escape(r['name'])}</span> "
            f"<span class='s'>{spark(r['series'])}</span>"
            f"<span class='m'>share_slope {r['share_slope']:.3f} · w {r['w_total']:.2f} · total {r['total']} · streak {r['streak']}</span></li>"
        )

    ent_li = "\n".join(li_entity(r) for r in ent_rows[:12]) or "<li>Sin datos</li>"
    cat_li = "\n".join(li_cat(r) for r in cat_rows[:10]) or "<li>Sin datos</li>"

    imp_li = "\n".join(f"<li>{html_escape(x)}</li>" for x in implications)

    risers_li = "\n".join(
        f"<li><span class='k'>{html_escape(r['name'])}</span> "
        f"<span class='m'>share {r['early']:.2%} → {r['recent']:.2%} (Δ {r['delta']:+.2%})</span></li>"
        for r in risers
    ) or "<li>Sin datos</li>"

    fallers_li = "\n".join(
        f"<li><span class='k'>{html_escape(r['name'])}</span> "
        f"<span class='m'>share {r['early']:.2%} → {r['recent']:.2%} (Δ {r['delta']:+.2%})</span></li>"
        for r in fallers
    ) or "<li>Sin datos</li>"

    new_li = "\n".join(li_entity(r) for r in new_ents) or "<li>Sin datos</li>"
    bo_li = "\n".join(li_entity(r) for r in breakouts) or "<li>Sin datos</li>"

    # Clusters navegables: top 5 entidades + top 3 categorías
    clusters = []
    for r in ent_rows[:5]:
        entity = r["name"]
        items = pick_items_for_entity(snapshots, entity, limit=6)
        li = []
        for it in items:
            title = html_escape((it.get("title") or "").strip())
            url = (it.get("url") or it.get("link") or "").strip()
            src = html_escape((it.get("source") or "").strip())
            cat = html_escape(((it.get("primary") or "misc").strip()))
            if url:
                li.append(f"<li><a href='{url}' target='_blank' rel='noopener'>{title}</a> <span class='m'>[{src}] [{cat}]</span></li>")
            else:
                li.append(f"<li>{title} <span class='m'>[{src}] [{cat}]</span></li>")
        clusters.append(f"<section class='card'><h2>{html_escape(entity)}</h2><ul>{''.join(li)}</ul></section>")

    cat_clusters = []
    for r in cat_rows[:3]:
        category = r["name"]
        items = pick_items_for_category(snapshots, category, limit=6)
        li = []
        for it in items:
            title = html_escape((it.get("title") or "").strip())
            url = (it.get("url") or it.get("link") or "").strip()
            src = html_escape((it.get("source") or "").strip())
            cat = html_escape(((it.get("primary") or "misc").strip()))
            if url:
                li.append(f"<li><a href='{url}' target='_blank' rel='noopener'>{title}</a> <span class='m'>[{src}] [{cat}]</span></li>")
            else:
                li.append(f"<li>{title} <span class='m'>[{src}] [{cat}]</span></li>")
        cat_clusters.append(f"<section class='card'><h2>Categoria: {html_escape(category)}</h2><ul>{''.join(li)}</ul></section>")

    clusters_html = "<div class='grid'>" + "".join(clusters) + "</div>" if clusters else ""
    cat_clusters_html = "<div class='grid'>" + "".join(cat_clusters) + "</div>" if cat_clusters else ""

    period = f"{days[0]} → {days[-1]}"

    html = f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Weekly Radar · {period}</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin:0; background:#0b0e14; color:#e6edf3; }}
    header {{ padding:20px; border-bottom:1px solid #222; background:#0b0e14; position:sticky; top:0; z-index: 5; }}
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
    .pill {{ display:inline-block; padding:2px 8px; border:1px solid #1f2a3a; border-radius:999px; color:#9aa4b2; font-size:12px; margin-right:8px; }}
    .metrics {{ margin-top:8px; color:#9aa4b2; font-size:12px; }}
    @media (max-width:900px) {{ .grid {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
<header>
  <div class="wrap">
    <h1>Weekly Radar · {period}</h1>
    <div class="metrics">
      <span class="pill">ventana: {n} días</span>
      <span class="pill">recency half-life: 3d</span>
      <span class="pill">ent HHI: {ent_hhi:.3f} (top3 {ent_top3:.1%})</span>
      <span class="pill">cat HHI: {cat_hhi:.3f} (top3 {cat_top3:.1%})</span>
    </div>
  </div>
</header>

<main class="wrap">
  <div class="grid">
    <section class="card">
      <h2>Entidades · momentum (ponderado)</h2>
      <ul>{ent_li}</ul>
    </section>

    <section class="card">
      <h2>Categorías · share momentum</h2>
      <ul>{cat_li}</ul>
    </section>
  </div>

  <div class="grid" style="margin-top:14px">
    <section class="card">
      <h2>Rotación narrativa · suben</h2>
      <ul>{risers_li}</ul>
    </section>

    <section class="card">
      <h2>Rotación narrativa · bajan</h2>
      <ul>{fallers_li}</ul>
    </section>
  </div>

  <section class="card" style="margin-top:14px">
    <h2>Implicaciones</h2>
    <ul>{imp_li}</ul>
  </section>

  <div class="grid" style="margin-top:14px">
    <section class="card">
      <h2>New entrants (últimos días)</h2>
      <ul>{new_li}</ul>
    </section>

    <section class="card">
      <h2>Breakouts (salto reciente)</h2>
      <ul>{bo_li}</ul>
    </section>
  </div>

  <section style="margin-top:14px">
    <h2 style="color:#cbd5e1; font-size:15px; margin:0 0 10px 0;">Clusters · top entidades</h2>
    {clusters_html}
  </section>

  <section style="margin-top:14px">
    <h2 style="color:#cbd5e1; font-size:15px; margin:0 0 10px 0;">Clusters · top categorías</h2>
    {cat_clusters_html}
  </section>
</main>

</body>
</html>
"""

    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
