# src/weekly.py
from __future__ import annotations

import json
import html
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

DATA_DIR = Path("docs/data")
OUT_HTML = Path("docs/weekly.html")

CATEGORY_LABELS = {
    "models": "Frontier models",
    "infra": "Compute & chips",
    "invest": "Model economics",
    "geopol": "Geopolitics",
    "misc": "Other",
}


def parse_date(stem: str) -> datetime:
    try:
        return datetime.strptime(stem, "%Y-%m-%d")
    except ValueError:
        return datetime.min


def is_daily_snapshot_file(p: Path) -> bool:
    if not p.is_file() or p.suffix.lower() != ".json":
        return False
    return parse_date(p.stem) != datetime.min


def list_latest(n: int = 7) -> List[Path]:
    if not DATA_DIR.exists():
        return []
    files = [p for p in DATA_DIR.glob("*.json") if is_daily_snapshot_file(p)]
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
            cat = item_theme(it)
            if cat == category:
                hits.append(it)
                if len(hits) >= limit:
                    return hits
    return hits


def html_escape(s: str) -> str:
    return html.escape(s or "", quote=True)


def safe_href(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return "#"
    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return html_escape(raw)
    return "#"


def item_theme(it: Dict[str, Any]) -> str:
    raw = (it.get("strategic_theme") or it.get("primary") or "other")
    return (raw or "other").strip() or "other"


def human_category(category: str) -> str:
    from src.render import THEME_LABELS, human_theme
    key = (category or "other").strip()
    if key in THEME_LABELS or key.lower() in THEME_LABELS:
        return human_theme(key)
    return CATEGORY_LABELS.get(key, human_theme(key))


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
    source_series: Dict[str, List[int]] = {}
    total_items_per_day: List[int] = []

    # Construye series
    for di, snap in enumerate(snapshots):
        items = snap.get("items", []) or []
        total_items_per_day.append(len(items))

        local_ent: Dict[str, int] = {}
        local_cat: Dict[str, int] = {}
        local_source: Dict[str, int] = {}

        for it in items:
            if not isinstance(it, dict):
                continue

            cat = item_theme(it)
            local_cat[cat] = local_cat.get(cat, 0) + 1

            src = (it.get("source") or "unknown").strip() or "unknown"
            local_source[src] = local_source.get(src, 0) + 1

            for e in (it.get("entities") or []):
                if isinstance(e, str) and e.strip():
                    e2 = e.strip()
                    local_ent[e2] = local_ent.get(e2, 0) + 1

        for c, v in local_cat.items():
            cat_series.setdefault(c, [0] * n)[di] = v
        for s, v in local_source.items():
            source_series.setdefault(s, [0] * n)[di] = v
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

    # Métricas por fuente
    source_rows = []
    source_weighted_counts: Dict[str, float] = {}
    for src, series in source_series.items():
        wt = weighted_total(series, weights)
        source_weighted_counts[src] = wt
        source_rows.append({
            "name": src,
            "series": series,
            "total": sum(series),
            "streak": streak(series),
            "w_total": wt,
            "delta": delta_recent_vs_early(series, weights),
        })
    source_rows.sort(key=lambda r: (r["w_total"], r["total"], r["streak"]), reverse=True)
    x_rows = [r for r in source_rows if str(r["name"]).startswith("X ")]
    x_weighted_total = sum(r["w_total"] for r in x_rows)
    x_mentions_total = sum(r["total"] for r in x_rows)

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

    # Lectura de la semana, en castellano. Las métricas se quedan en el cálculo.
    implications = []
    dominant = cat_rows[0] if cat_rows else None
    hot_ent = ent_rows[0] if ent_rows else None

    if dominant:
        implications.append(f"Esta semana manda {human_category(dominant['name'])}.")
    if hot_ent:
        racha = hot_ent["streak"]
        racha_txt = f"{racha} día seguido" if racha == 1 else f"{racha} días seguidos"
        implications.append(f"{hot_ent['name']} es el tractor ({racha_txt}).")

    if ent_hhi >= 0.18:
        implications.append("Pocos nombres concentran la conversación.")
    else:
        implications.append("La conversación está repartida entre varios actores.")

    if cat_hhi >= 0.25:
        implications.append("El radar se está yendo a un solo tema.")
    else:
        implications.append("Los temas están repartidos.")

    active_sources_count = len([s for s in source_rows if s["total"] > 0])
    implications.append(f"{active_sources_count} fuentes con cobertura esta semana.")

    def meta_line(r, extra: str = "") -> str:
        bits = [spark(r["series"])]
        if r.get("streak"):
            bits.append(f"racha {r['streak']}d")
        if r.get("total"):
            bits.append(f"{r['total']} menciones")
        if extra:
            bits.append(extra)
        return " · ".join(bits)

    def li_entity(r):
        return (
            f"<li><span class='k'>{html_escape(r['name'])}</span>"
            f"<span class='m'>{html_escape(meta_line(r))}</span></li>"
        )

    def li_cat(r):
        extra = ""
        shares = r.get("share") or []
        if len(shares) >= 2:
            extra = f"{shares[0]:.0%} → {shares[-1]:.0%}"
        return (
            f"<li><span class='k'>{html_escape(human_category(r['name']))}</span>"
            f"<span class='m'>{html_escape(meta_line(r, extra))}</span></li>"
        )

    def li_source(r):
        return (
            f"<li><span class='k'>{html_escape(r['name'])}</span>"
            f"<span class='m'>{html_escape(meta_line(r))}</span></li>"
        )

    ent_li = "\n".join(li_entity(r) for r in ent_rows[:12]) or "<li>Sin datos</li>"
    cat_li = "\n".join(li_cat(r) for r in cat_rows[:10]) or "<li>Sin datos</li>"
    source_li = "\n".join(li_source(r) for r in source_rows[:10]) or "<li>Sin datos</li>"
    imp_li = "\n".join(f"<li>{html_escape(x)}</li>" for x in implications)

    def rot_line(r):
        return (
            f"<li><span class='k'>{html_escape(human_category(r['name']))}</span>"
            f"<span class='m'>{r['early']:.0%} → {r['recent']:.0%}</span></li>"
        )

    risers_li = "\n".join(rot_line(r) for r in risers) or "<li>Sin datos</li>"
    fallers_li = "\n".join(rot_line(r) for r in fallers) or "<li>Sin datos</li>"
    new_li = "\n".join(li_entity(r) for r in new_ents) or "<li>Sin datos</li>"
    bo_li = "\n".join(li_entity(r) for r in breakouts) or "<li>Sin datos</li>"

    def item_row(it: Dict[str, Any]) -> str:
        title = html_escape((it.get("title_es") or it.get("title") or "").strip() or "(sin título)")
        url = (it.get("url") or it.get("link") or "").strip()
        src = html_escape((it.get("source") or "").strip())
        href = safe_href(url)
        if url:
            return (
                f"<a class='hit' href='{href}' target='_blank' rel='noopener noreferrer'>"
                f"<span class='ht'>{title}</span><span class='hs'>{src}</span></a>"
            )
        return f"<div class='hit'><span class='ht'>{title}</span><span class='hs'>{src}</span></div>"

    def cluster_card(title: str, items: List[Dict[str, Any]]) -> str:
        rows = "".join(item_row(it) for it in items) or "<div class='none'>Sin piezas esta semana.</div>"
        return f"<section class='widget'><div class='widget-title'><span>{html_escape(title)}</span></div>{rows}</section>"

    clusters = [cluster_card(r["name"], pick_items_for_entity(snapshots, r["name"], limit=6)) for r in ent_rows[:5]]
    cat_clusters = [
        cluster_card(human_category(r["name"]), pick_items_for_category(snapshots, r["name"], limit=6))
        for r in cat_rows[:3]
    ]
    clusters_html = "".join(clusters)
    cat_clusters_html = "".join(cat_clusters)

    period = f"{days[0]} → {days[-1]}"
    total_analyzed = sum(s["total"] for s in source_rows)

    html = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Semanal · AI Strategic Radar</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<style>
  :root{{
    --bg:#191a1a; --card:#202222; --card-hover:#262828; --line:#2f3131; --line-2:#3d4040;
    --txt:#e8e8e6; --txt-dim:#c8cbca; --dim:#9b9f9e; --dimmer:#6b6f6e;
    --accent:#20b8cd; --accent-soft:rgba(32,184,205,.12);
    --green:#4bd48b; --rose:#f2665f; --amber:#e8b750; --violet:#b28bf2;
    --mono:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,monospace;
    --sans:'Inter',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
    --disp:'Space Grotesk','Inter',system-ui,sans-serif;
    --r:16px;
  }}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--bg);color:var(--txt);font-family:var(--sans);line-height:1.5}}
  a{{color:inherit;text-decoration:none}}
  .wrap{{max-width:1100px;margin:0 auto;padding:0 24px 80px}}
  .topbar{{display:flex;align-items:center;justify-content:space-between;gap:16px;
          padding:18px 0;border-bottom:1px solid var(--line);margin-bottom:22px;flex-wrap:wrap}}
  .brand{{display:flex;align-items:center;gap:10px;font-family:var(--disp);font-size:17px;font-weight:700}}
  .brand .dot{{width:9px;height:9px;border-radius:50%;background:var(--accent);box-shadow:0 0 12px var(--accent)}}
  .brand .date{{font-family:var(--mono);font-size:11px;color:var(--dimmer);font-weight:400;margin-left:6px}}
  .nav{{display:flex;gap:6px}}
  .nav a{{font-size:13px;font-weight:600;padding:7px 15px;border-radius:999px;color:var(--dim)}}
  .nav a.on{{color:var(--accent);background:var(--accent-soft)}}
  .nav a:hover{{color:var(--txt)}}
  .lead h1{{margin:0 0 8px;font-family:var(--disp);font-size:clamp(22px,3vw,30px);letter-spacing:-.02em}}
  .lead p{{margin:0 0 22px;color:var(--dim);font-size:14.5px}}
  .grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
  .widget{{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:16px 18px}}
  .widget-title{{font-family:var(--disp);font-size:15px;font-weight:700;margin-bottom:12px}}
  .wide{{grid-column:1/-1}}
  ul.rows{{list-style:none;padding:0;margin:0}}
  ul.rows li{{display:flex;justify-content:space-between;gap:12px;align-items:baseline;
             padding:8px 0;border-bottom:1px solid var(--line);font-size:13.5px}}
  ul.rows li:last-child{{border-bottom:none;padding-bottom:0}}
  .k{{font-weight:600}}
  .m{{font-family:var(--mono);font-size:11px;color:var(--dimmer);white-space:nowrap}}
  .thesis{{padding:4px 0 6px}}
  .thesis li{{padding:7px 0;border-bottom:1px solid var(--line);font-size:14.5px;color:var(--txt-dim)}}
  .thesis li:last-child{{border-bottom:none}}
  .hit{{display:flex;justify-content:space-between;gap:12px;align-items:baseline;
        padding:8px 0;border-bottom:1px solid var(--line)}}
  .hit:last-child{{border-bottom:none;padding-bottom:0}}
  .hit:hover .ht{{color:var(--accent)}}
  .ht{{font-size:13.5px;font-weight:600;line-height:1.4}}
  .hs{{font-family:var(--mono);font-size:10px;color:var(--dimmer);flex-shrink:0}}
  .none{{font-size:13px;color:var(--dimmer);font-style:italic}}
  .section-h{{font-family:var(--disp);font-size:15px;font-weight:700;margin:28px 0 12px}}
  .clusters{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
  footer{{margin-top:48px;padding-top:16px;border-top:1px solid var(--line);
         font-family:var(--mono);font-size:10px;color:var(--dimmer)}}
  @media(max-width:800px){{
    .wrap{{padding:0 14px 60px}}
    .grid,.clusters{{grid-template-columns:1fr}}
    ul.rows li,.hit{{flex-direction:column;gap:4px}}
    .m{{white-space:normal}}
  }}
</style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div class="brand"><span class="dot"></span> AI Strategic Radar <span class="date">{html_escape(period)}</span></div>
    <nav class="nav">
      <a href="index.html">Diario</a>
      <a class="on" href="weekly.html">Semanal</a>
      <a href="archivo.html">Archivo</a>
    </nav>
  </div>

  <div class="lead">
    <h1>Semanal</h1>
    <p>{n} días · {html_escape(period)} · {total_analyzed} señales.</p>
  </div>

  <section class="widget thesis" style="margin-bottom:16px">
    <div class="widget-title">Lectura</div>
    <ul class="rows thesis">{imp_li}</ul>
  </section>

  <div class="grid">
    <section class="widget">
      <div class="widget-title">Quién tira</div>
      <ul class="rows">{ent_li}</ul>
    </section>
    <section class="widget">
      <div class="widget-title">Temas</div>
      <ul class="rows">{cat_li}</ul>
    </section>
    <section class="widget">
      <div class="widget-title">Temas que suben</div>
      <ul class="rows">{risers_li}</ul>
    </section>
    <section class="widget">
      <div class="widget-title">Temas que bajan</div>
      <ul class="rows">{fallers_li}</ul>
    </section>
    <section class="widget">
      <div class="widget-title">Nuevos nombres</div>
      <ul class="rows">{new_li}</ul>
    </section>
    <section class="widget">
      <div class="widget-title">Saltos</div>
      <ul class="rows">{bo_li}</ul>
    </section>
    <section class="widget wide">
      <div class="widget-title">Quién cubre</div>
      <ul class="rows">{source_li}</ul>
    </section>
  </div>

  <div class="section-h">Hilos por entidad</div>
  <div class="clusters">{clusters_html}</div>
  <div class="section-h">Hilos por tema</div>
  <div class="clusters">{cat_clusters_html}</div>

  <footer>{n} días · {html_escape(period)}</footer>
</div>
</body>
</html>
"""

    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
