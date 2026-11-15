# src/weekly.py
from __future__ import annotations

from src.brand import BASE_CSS as BRAND_CSS, HEAD as BRAND_HEAD, HTML_ATTRS, THEME_JS, bi, credits as brand_credits, header as brand_header, seo_head
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


def select_analyzed(loaded: List[tuple], n: int = 7) -> tuple:
    """Las `n` ultimas ediciones ANALIZADAS: (dias, snapshots, n_excluidas).

    Un dia degradado no paso por el filtro de relevancia: sus items son ruido
    sin juzgar con temas puestos por keywords. Contarlos como señales hacia que
    el semanal sacara conclusiones ("esta semana manda X") de material sin
    filtrar. Se saltan y se completa la ventana con ediciones anteriores.
    Si no hay ninguna analizada se usan las ultimas tal cual: mejor un semanal
    avisado que una pagina vacia.
    """
    good = [(d, s) for d, s in loaded if not s.get("degraded")][-n:]
    if not good:
        good = loaded[-n:]
        return [d for d, _ in good], [s for _, s in good], 0
    first = good[0][0]
    excluded = sum(1 for d, s in loaded if s.get("degraded") and d > first)
    return [d for d, _ in good], [s for _, s in good], excluded


def main():
    # El doble de la ventana: margen para saltar ediciones degradadas.
    files = list_latest(14)
    if not files:
        OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
        OUT_HTML.write_text("<html><body><p>No data.</p></body></html>", encoding="utf-8")
        return

    days, snapshots, n_degraded = select_analyzed([(p.stem, load_day(p)) for p in files])
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
        implications.append((f"Esta semana manda {human_category(dominant['name'])}.", f"This week is led by {human_category(dominant['name'])}."))
    if hot_ent:
        racha = hot_ent["streak"]
        racha_txt = f"{racha} día seguido" if racha == 1 else f"{racha} días seguidos"
        racha_en = f"{racha} day running" if racha == 1 else f"{racha} days running"
        implications.append((f"{hot_ent['name']} es el tractor ({racha_txt}).", f"{hot_ent['name']} is the driver ({racha_en})."))

    if ent_hhi >= 0.18:
        implications.append(("Pocos nombres concentran la conversación.", "A few names dominate the conversation."))
    else:
        implications.append(("La conversación está repartida entre varios actores.", "The conversation is spread across several players."))

    if cat_hhi >= 0.25:
        implications.append(("El radar se está yendo a un solo tema.", "The radar is narrowing to a single theme."))
    else:
        implications.append(("Los temas están repartidos.", "Themes are evenly spread."))

    active_sources_count = len([s for s in source_rows if s["total"] > 0])
    implications.append((f"{active_sources_count} fuentes con cobertura esta semana.", f"{active_sources_count} sources with coverage this week."))

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
    imp_li = "\n".join(f"<li>{bi(es, en)}</li>" for es, en in implications)

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
    n_txt = "1 edición" if n == 1 else f"{n} ediciones"
    if n_degraded:
        n_txt += f" · {n_degraded} sin filtrar excluida{'s' if n_degraded != 1 else ''}"
    elif any(s.get("degraded") for s in snapshots):
        n_txt += " (sin filtrar)"
    total_analyzed = sum(s["total"] for s in source_rows)

    html = f"""<!doctype html>
<html {HTML_ATTRS}>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
{seo_head("RADAR.IA · Semanal: quién tira y qué temas mandan", path="weekly.html")}{BRAND_HEAD}<style>{BRAND_CSS}
  .wrap{{max-width:1100px;margin:0 auto;padding:0 24px 80px}}
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

  .wrap{{max-width:1100px;margin:0 auto;padding:28px 24px 80px}}
  .lead p{{color:var(--muted);font-size:17px;margin:0 0 24px}}
  .widget{{background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow);padding:14px 16px;border-radius:0}}
  .widget-title{{display:flex;align-items:center;gap:9px;margin:-14px -16px 10px;padding:10px 16px;border-bottom:2px solid var(--ink);
                background:var(--card-2);font:700 12px/1.2 var(--f-mono);text-transform:uppercase;letter-spacing:.06em}}
  .widget-title::before{{content:"";width:10px;height:10px;background:var(--orange);border:2px solid var(--ink)}}
  .grid,.clusters{{gap:22px}}
  ul.rows li,.hit,.thesis li{{border-bottom:1px dashed var(--line)}}
  .thesis li{{font-size:15px;color:var(--text)}}
  .k{{font-family:var(--f-head);font-weight:700}}
  .m,.hs{{font-family:var(--f-mono);color:var(--muted)}}
  .hit:hover .ht{{color:inherit;text-decoration:underline}}
  .section-h{{display:flex;align-items:center;gap:10px;font:700 13px/1.2 var(--f-mono);text-transform:uppercase;letter-spacing:.08em;margin:36px 0 14px}}
  .section-h::before{{content:"";width:12px;height:12px;background:var(--orange);border:2px solid var(--ink)}}
  footer{{border-top:3px solid var(--ink);font:400 12px var(--f-mono);color:var(--muted)}}
</style>
</head>
<body>
{brand_header("weekly")}
<div class="wrap">

  <div class="lead">
    <span class="kicker">{html_escape(period)}</span>
    <h1 class="page-h1">{bi("Semanal","Weekly")}</h1>
    <p>{n_txt} · {html_escape(period)} · {total_analyzed} {bi("señales","signals")}.</p>
  </div>

  <section class="widget" style="margin-bottom:16px">
    <div class="widget-title">{bi("Lectura","Reading")}</div>
    <ul class="rows thesis">{imp_li}</ul>
  </section>

  <div class="grid">
    <section class="widget">
      <div class="widget-title">{bi("Quién tira","Who drives")}</div>
      <ul class="rows">{ent_li}</ul>
    </section>
    <section class="widget">
      <div class="widget-title">{bi("Temas","Themes")}</div>
      <ul class="rows">{cat_li}</ul>
    </section>
    <section class="widget">
      <div class="widget-title">{bi("Temas que suben","Rising themes")}</div>
      <ul class="rows">{risers_li}</ul>
    </section>
    <section class="widget">
      <div class="widget-title">{bi("Temas que bajan","Falling themes")}</div>
      <ul class="rows">{fallers_li}</ul>
    </section>
    <section class="widget">
      <div class="widget-title">{bi("Nuevos nombres","New names")}</div>
      <ul class="rows">{new_li}</ul>
    </section>
    <section class="widget">
      <div class="widget-title">{bi("Saltos","Breakouts")}</div>
      <ul class="rows">{bo_li}</ul>
    </section>
    <section class="widget wide">
      <div class="widget-title">{bi("Quién cubre","Who covers")}</div>
      <ul class="rows">{source_li}</ul>
    </section>
  </div>

  <div class="section-h">{bi("Hilos por entidad","Threads by entity")}</div>
  <div class="clusters">{clusters_html}</div>
  <div class="section-h">{bi("Hilos por tema","Threads by theme")}</div>
  <div class="clusters">{cat_clusters_html}</div>

  {brand_credits()}
  <footer>{n_txt} · {html_escape(period)}</footer>
</div>
{THEME_JS}
</body>
</html>
"""

    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
