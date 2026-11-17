# src/weekly.py
from __future__ import annotations

from src.brand import BASE_CSS as BRAND_CSS, HEAD as BRAND_HEAD, HTML_ATTRS, THEME_JS, bi, credits as brand_credits, header as brand_header, seo_head
from src.config import ENTITY_ALIASES
from src.render import (
    ACTIVITY_EN,
    THEME_LABELS,
    THEME_LABELS_EN,
    clean_text,
    display_title,
    human_theme,
    item_fallback_image,
    score_tier,
    score_value,
    source_label,
    source_logo_url,
    truncate_text,
)
import json
import html
import re
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


def normalize_entity(e: str) -> str:
    val = re.sub(r"\s+", " ", (e or "").strip())
    if not val:
        return ""
    if val in ENTITY_ALIASES:
        return ENTITY_ALIASES[val]
    low = val.lower()
    for src, dst in ENTITY_ALIASES.items():
        if low == src.lower():
            return dst
    return val


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
    k = min(3, n // 2)
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


def _item_dedup_key(it: Dict[str, Any]) -> str:
    url = (it.get("url") or it.get("link") or "").strip().lower()
    if url:
        parsed = urlparse(url)
        clean_u = f"{parsed.netloc.replace('www.', '')}{parsed.path.rstrip('/')}"
        if clean_u:
            return f"u:{clean_u}"
    title = re.sub(r"\W+", " ", (it.get("title_es") or it.get("title") or "").lower()).strip()
    return f"t:{title[:80]}"


def pick_items_for_entity(snapshots: List[Dict[str, Any]], entity: str, limit: int = 6) -> List[Dict[str, Any]]:
    hits = []
    seen = set()
    target = normalize_entity(entity)
    for snap in reversed(snapshots):
        day_str = str(snap.get("date") or "")
        for it in (snap.get("items", []) or []):
            if not isinstance(it, dict):
                continue
            ents = [normalize_entity(e) for e in (it.get("entities") or []) if isinstance(e, str)]
            if target in ents:
                key = _item_dedup_key(it)
                if key in seen:
                    continue
                seen.add(key)
                enriched = dict(it)
                enriched.setdefault("_date", day_str)
                hits.append(enriched)
                if len(hits) >= limit:
                    return hits
    return hits


def pick_items_for_category(snapshots: List[Dict[str, Any]], category: str, limit: int = 6) -> List[Dict[str, Any]]:
    hits = []
    seen = set()
    for snap in reversed(snapshots):
        day_str = str(snap.get("date") or "")
        for it in (snap.get("items", []) or []):
            if not isinstance(it, dict):
                continue
            cat = item_theme(it)
            if cat == category:
                key = _item_dedup_key(it)
                if key in seen:
                    continue
                seen.add(key)
                enriched = dict(it)
                enriched.setdefault("_date", day_str)
                hits.append(enriched)
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
    key = (category or "other").strip()
    if key in THEME_LABELS or key.lower() in THEME_LABELS:
        return human_theme(key)
    return CATEGORY_LABELS.get(key, human_theme(key))


def human_category_en(category: str) -> str:
    key = (category or "other").strip()
    return THEME_LABELS_EN.get(key, CATEGORY_LABELS.get(key, human_category(key)))


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


def _mini_bars_html(series: List[int], days: List[str], accent_last: bool = True) -> str:
    """Renderiza una micro-gráfica de barras CSS para la serie diaria."""
    if not series:
        return ""
    m = max(series) or 1
    cells = []
    last_idx = len(series) - 1
    for idx, val in enumerate(series):
        pct = 14 if val == 0 else max(24, int(round((val / m) * 100)))
        cls = "b-zero" if val == 0 else ("b-now" if (accent_last and idx == last_idx) else "b-on")
        day_lbl = days[idx] if idx < len(days) else ""
        tip = html_escape(f"{day_lbl}: {val}")
        cells.append(f"<i class='{cls}' style='height:{pct}%' title='{tip}'></i>")
    return f"<span class='mini-bars' aria-hidden='true'>{''.join(cells)}</span>"


def _pick_weekly_top_signals(snapshots: List[Dict[str, Any]], limit: int = 6) -> List[Dict[str, Any]]:
    """Selecciona las mejores señales únicas de la semana, ordenadas por relevancia."""
    by_key: Dict[str, Dict[str, Any]] = {}
    for snap in snapshots:
        day_str = str(snap.get("date") or "")
        for raw in (snap.get("items") or []):
            if not isinstance(raw, dict):
                continue
            sc = score_value(raw)
            it = dict(raw)
            it["score"] = sc
            it["_date"] = day_str
            key = _item_dedup_key(it)
            prev = by_key.get(key)
            if prev is None or (it.get("layer") == "signal" and prev.get("layer") != "signal") or sc > prev.get("score", 0):
                by_key[key] = it

    candidates = list(by_key.values())
    signals = [it for it in candidates if it.get("layer") == "signal"]
    pool = signals if len(signals) >= limit else candidates
    pool.sort(key=lambda x: (x.get("score", 0), x.get("_date", "")), reverse=True)
    return pool[:limit]


def main():
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
    source_sample_url: Dict[str, str] = {}
    total_items_per_day: List[int] = []
    signals_per_day: List[int] = []
    context_per_day: List[int] = []
    dropped_per_day: List[int] = []
    avg_score_per_day: List[float] = []

    confirmed_watches: List[Dict[str, Any]] = []
    seen_watch_texts = set()
    weekly_risks: List[Tuple[str, str, str]] = []
    seen_risks = set()

    for di, snap in enumerate(snapshots):
        items = snap.get("items", []) or []
        total_items_per_day.append(len(items))
        sig_c = sum(1 for it in items if isinstance(it, dict) and it.get("layer") == "signal")
        ctx_c = sum(1 for it in items if isinstance(it, dict) and it.get("layer") == "context")
        if sig_c == 0 and ctx_c == 0:
            sig_c = len(items)
        signals_per_day.append(sig_c)
        context_per_day.append(ctx_c)
        dropped_per_day.append(int(snap.get("dropped_noise") or 0))

        scores_today = [score_value(it) for it in items if isinstance(it, dict) and score_value(it) > 0]
        avg_sc = float(snap.get("score_avg") or (sum(scores_today) / len(scores_today) if scores_today else 0.0))
        avg_score_per_day.append(avg_sc)

        # Recopila señales confirmadas (watch_resolved == hit)
        mem = snap.get("memory") or {}
        for w in (mem.get("watch_resolved") or []):
            if isinstance(w, dict) and w.get("status") == "hit":
                wt_txt = clean_text(w.get("text") or "")
                if wt_txt and wt_txt.lower() not in seen_watch_texts:
                    seen_watch_texts.add(wt_txt.lower())
                    confirmed_watches.append({
                        "date": snap.get("date") or days[di],
                        "text": wt_txt,
                        "text_en": clean_text(w.get("text_en") or "") or wt_txt,
                        "evidence": clean_text(w.get("evidence") or ""),
                        "evidence_en": clean_text(w.get("evidence_en") or ""),
                    })

        # Recopila riesgos estratégicos de los briefings
        br = snap.get("briefing") or {}
        r_es_list = br.get("risks") or []
        r_en_list = br.get("risks_en") or []
        for ri, r_es in enumerate(r_es_list[:2]):
            if not isinstance(r_es, str) or not r_es.strip():
                continue
            clean_r = clean_text(r_es)
            r_key = clean_r[:50].lower()
            if r_key not in seen_risks:
                seen_risks.add(r_key)
                clean_r_en = clean_text(r_en_list[ri]) if ri < len(r_en_list) and isinstance(r_en_list[ri], str) else ""
                weekly_risks.append((snap.get("date") or days[di], clean_r, clean_r_en))

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
            if src not in source_sample_url and (it.get("url") or it.get("link")):
                source_sample_url[src] = str(it.get("url") or it.get("link") or "")

            for e in (it.get("entities") or []):
                if isinstance(e, str) and e.strip():
                    e2 = normalize_entity(e)
                    if e2:
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

    ent_rows.sort(key=lambda r: (r["w_total"], r["delta"], r["streak"], r["total"]), reverse=True)

    # Metrics por categoría
    cat_rows = []
    cat_weighted_counts: Dict[str, float] = {}
    k_rot = min(3, max(1, n // 2))

    for c, series in cat_series.items():
        wt = weighted_total(series, weights)
        cat_weighted_counts[c] = wt
        shares = []
        for i, v in enumerate(series):
            denom = total_items_per_day[i] or 1
            shares.append(v / denom)

        early_sh = sum(shares[:k_rot]) / k_rot if len(shares) >= 2 else (shares[0] if shares else 0.0)
        recent_sh = sum(shares[-k_rot:]) / k_rot if len(shares) >= 2 else (shares[-1] if shares else 0.0)

        cat_rows.append({
            "name": c,
            "series": series,
            "share": shares,
            "total": sum(series),
            "streak": streak(series),
            "slope": slope([float(x) for x in series]),
            "share_slope": slope(shares),
            "w_total": wt,
            "early_share": early_sh,
            "recent_share": recent_sh,
            "rot_delta": recent_sh - early_sh,
            "delta_share": delta_recent_vs_early([int(round(s * 1000)) for s in shares], weights),
        })

    cat_rows.sort(key=lambda r: (r["w_total"], r["total"], r["share_slope"], r["streak"]), reverse=True)

    # Métricas por fuente
    source_rows = []
    for src, series in source_series.items():
        wt = weighted_total(series, weights)
        source_rows.append({
            "name": src,
            "label": source_label(src),
            "logo": source_logo_url(src, source_sample_url.get(src, "")),
            "series": series,
            "total": sum(series),
            "streak": streak(series),
            "w_total": wt,
            "delta": delta_recent_vs_early(series, weights),
        })
    source_rows.sort(key=lambda r: (r["total"], r["w_total"], r["streak"]), reverse=True)

    # Rotación narrativa: compara share reciente vs temprano
    rot = sorted(cat_rows, key=lambda x: x["rot_delta"], reverse=True)
    risers = [r for r in rot if r["rot_delta"] > 0.01][:3]
    fallers = [r for r in reversed(rot) if r["rot_delta"] < -0.01][:3]

    # Concentración
    ent_conc = hhi_from_counts(ent_weighted_counts)
    cat_conc = hhi_from_counts(cat_weighted_counts)
    ent_top3 = top_share(ent_weighted_counts, 3)

    # New entrants: 0 en primeros (n-k) días, aparece en últimos k días
    new_k = min(3, n)
    new_ents = []
    for r in ent_rows:
        s = r["series"]
        if sum(s[:max(0, n - new_k)]) == 0 and sum(s[-new_k:]) > 0:
            new_ents.append(r)
    new_ents.sort(key=lambda r: (r["w_total"], r["last"], r["delta"]), reverse=True)
    new_ents = new_ents[:8]
    new_ent_names = {r["name"] for r in new_ents}

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
    breakout_names = {r["name"] for r in breakouts}

    total_analyzed = sum(total_items_per_day)
    total_signals = sum(signals_per_day)
    total_context = sum(context_per_day)
    total_dropped = sum(dropped_per_day)
    weekly_avg_score = int(round(sum(avg_score_per_day) / len(avg_score_per_day))) if avg_score_per_day else 0
    alert_days = sum(1 for s in snapshots if str((s.get("activity") or {}).get("label") or "").upper() == "ALERTA")
    active_sources_count = len([s for s in source_rows if s["total"] > 0])

    dominant = cat_rows[0] if cat_rows else None
    hot_ent = ent_rows[0] if ent_rows else None
    dom_share_pct = int(round((dominant["total"] / max(1, total_analyzed)) * 100)) if dominant else 0

    # Lectura ejecutiva de la semana, bilingüe
    implications = []
    if dominant:
        implications.append((
            "Vector principal:",
            "Lead vector:",
            f"{human_category(dominant['name'])} concentra el {dom_share_pct}% de las piezas de la semana ({dominant['total']} apariciones).",
            f"{human_category_en(dominant['name'])} accounts for {dom_share_pct}% of this week's items ({dominant['total']} appearances).",
        ))
    if hot_ent:
        racha = hot_ent["streak"]
        racha_txt = f"{racha} día seguido" if racha == 1 else f"{racha} días seguidos"
        racha_en = f"{racha} day running" if racha == 1 else f"{racha} days running"
        runner_ups = ", ".join(r["name"] for r in ent_rows[1:4])
        extra_es = f" seguido de {runner_ups}" if runner_ups else ""
        extra_en = f" followed by {runner_ups}" if runner_ups else ""
        implications.append((
            "Protagonista:",
            "Lead driver:",
            f"{hot_ent['name']} marca el paso ({hot_ent['total']} menciones, {racha_txt}){extra_es}.",
            f"{hot_ent['name']} sets the pace ({hot_ent['total']} mentions, {racha_en}){extra_en}.",
        ))
    if risers:
        top_riser = risers[0]
        pts = int(round(top_riser["rot_delta"] * 100))
        implications.append((
            "Rotación temática:",
            "Theme rotation:",
            f"{human_category(top_riser['name'])} gana tracción en el tramo final (+{pts} pts de cuota).",
            f"{human_category_en(top_riser['name'])} gains traction in the final stretch (+{pts} pts of share).",
        ))
    if ent_conc >= 0.18:
        top3_pct = int(round(ent_top3 * 100))
        implications.append((
            "Concentración alta:",
            "High concentration:",
            f"los 3 actores principales acaparan el {top3_pct}% del peso estratégico.",
            f"the top 3 players capture {top3_pct}% of the strategic weight.",
        ))
    else:
        implications.append((
            "Tablero abierto:",
            "Open board:",
            "la conversación está repartida entre múltiples laboratorios y actores sin un único monopolio.",
            "the conversation is distributed across multiple labs and players without a single monopoly.",
        ))
    if cat_conc >= 0.25:
        implications.append((
            "Foco estrecho:",
            "Narrow focus:",
            f"el radar converge en un único frente dominante y filtra {total_dropped} piezas de ruido.",
            f"the radar converges on a single dominant front while filtering {total_dropped} noise items.",
        ))
    else:
        implications.append((
            "Cobertura diversa:",
            "Broad coverage:",
            f"{active_sources_count} fuentes activas repartidas en varios frentes y {total_dropped} piezas de ruido descartadas.",
            f"{active_sources_count} active sources across multiple fronts and {total_dropped} noise items filtered out.",
        ))

    imp_li = "\n".join(
        f"<li><span class='idx'>{i:02d}</span><div class='imp-body'><b>{bi(k_es, k_en)}</b> {bi(v_es, v_en)}</div></li>"
        for i, (k_es, k_en, v_es, v_en) in enumerate(implications, 1)
    )

    # Tarjetas de las 6 señales más potentes de la semana
    top_signals = _pick_weekly_top_signals(snapshots, limit=6)
    top_cards_html_list = []
    for rank_i, it in enumerate(top_signals, 1):
        sc = it.get("score") or score_value(it)
        sc_cls = score_tier(sc)
        th_key = item_theme(it)
        th_es = human_category(th_key)
        th_en = human_category_en(th_key)
        t_es = display_title(it)
        t_en = clean_text(it.get("title_en") or "") or clean_text(it.get("title") or "") or t_es
        sw_es = truncate_text(clean_text(it.get("so_what") or ""), 175)
        sw_en = truncate_text(clean_text(it.get("so_what_en") or "") or clean_text(it.get("so_what") or ""), 175)
        pw_es = truncate_text(clean_text(it.get("power_shift") or ""), 85)
        pw_en = truncate_text(clean_text(it.get("power_shift_en") or "") or clean_text(it.get("power_shift") or ""), 85)
        url = safe_href(it.get("url") or it.get("link") or "")
        src_lbl = html_escape(source_label(it.get("source", "")))
        logo = html_escape(source_logo_url(it.get("source", ""), it.get("url") or it.get("link") or ""))
        date_str = html_escape(it.get("_date") or "")
        short_date = date_str[5:] if len(date_str) >= 10 else date_str

        fb_es = html_escape(item_fallback_image(it, "es"))
        fb_en = html_escape(item_fallback_image(it, "en"))
        raw_img = (it.get("image_url") or "").strip()
        if raw_img.startswith(("http://", "https://")):
            img_html = (
                f"<img class='wk-card-img' src='{html_escape(raw_img)}' "
                f"data-fb='{fb_es}' data-fb-en='{fb_en}' alt='' loading='lazy' referrerpolicy='no-referrer'/>"
            )
        else:
            img_html = (
                f"<img class='wk-card-img l-es' src='{fb_es}' alt='' loading='lazy'/>"
                f"<img class='wk-card-img l-en' src='{fb_en}' alt='' loading='lazy'/>"
            )

        pw_block = ""
        if pw_es:
            pw_block = (
                f"<div class='wk-card-foot'>"
                f"<div class='fact pw'><span class='k'>{bi('Impacto', 'Impact')}</span>"
                f"<span class='v'>{bi(pw_es, pw_en)}</span></div>"
                f"</div>"
            )

        sw_block = f"<p class='wk-card-sw'>{bi(sw_es, sw_en)}</p>" if sw_es else ""

        top_cards_html_list.append(
            f"<article class='wk-card'>"
            f"<a class='wk-card-media' href='{url}' target='_blank' rel='noopener noreferrer'>"
            f"<span class='wk-rank'>#{rank_i:02d}</span>"
            f"{img_html}"
            f"</a>"
            f"<div class='wk-card-body'>"
            f"<div class='meta-row'>"
            f"<span class='cx-tag'>{bi(th_es, th_en)}</span>"
            f"<span class='src'><img src='{logo}' alt='' loading='lazy'/>{src_lbl}</span>"
            f"<a class='wk-date' href='d/{date_str}.html'>{short_date}</a>"
            f"<span class='score {sc_cls}'>{sc}/100</span>"
            f"</div>"
            f"<h3 class='wk-card-title'><a href='{url}' target='_blank' rel='noopener noreferrer'>{bi(t_es, t_en)}</a></h3>"
            f"{sw_block}"
            f"{pw_block}"
            f"</div>"
            f"</article>"
        )
    top_cards_html = "\n".join(top_cards_html_list)

    # Crónica día a día (Timeline)
    max_day_items = max(total_items_per_day) if total_items_per_day else 1
    timeline_rows = []
    for di in range(n - 1, -1, -1):
        d_str = days[di]
        snap = snapshots[di]
        br = snap.get("briefing") or {}
        th_es = clean_text(br.get("thesis") or "")
        th_en = clean_text(br.get("thesis_en") or "") or th_es
        if not th_es:
            day_items = snap.get("items") or []
            th_es = display_title(day_items[0]) if day_items else "Sin movimientos de frontera."
            th_en = clean_text((day_items[0].get("title_en") if day_items else "") or "") or th_es
        act = snap.get("activity") or {"label": "ACTIVO", "class": "active"}
        act_lbl = str(act.get("label") or "ACTIVO")
        act_en = ACTIVITY_EN.get(act_lbl, act_lbl)
        act_cls = "alert" if act_lbl == "ALERTA" else ("active" if act_lbl == "ACTIVO" else "quiet")
        n_sig = signals_per_day[di]
        n_ctx = context_per_day[di]
        avg_sc = int(round(avg_score_per_day[di]))
        sc_cls = score_tier(avg_sc)
        pct_bar = max(12, int(round((total_items_per_day[di] / max(1, max_day_items)) * 100)))

        timeline_rows.append(
            f"<a class='tl-day' href='d/{html_escape(d_str)}.html'>"
            f"<div class='tl-head'>"
            f"<span class='tl-date'>{html_escape(d_str)}</span>"
            f"<span class='tl-act {act_cls}'>{bi(act_lbl, act_en)}</span>"
            f"<span class='tl-cnt'>{n_sig} {bi('señales', 'signals')}{f' · +{n_ctx} ctx' if n_ctx else ''}</span>"
            f"<span class='score {sc_cls}'>{bi('Media', 'Avg')} {avg_sc}/100</span>"
            f"</div>"
            f"<p class='tl-thesis'>{bi(truncate_text(th_es, 165), truncate_text(th_en, 165))}</p>"
            f"<div class='tl-bar'><i style='width:{pct_bar}%'></i></div>"
            f"</a>"
        )
    timeline_html = "\n".join(timeline_rows)

    # Ranking visual de entidades ("Quién tira")
    max_ent_total = max((r["total"] for r in ent_rows[:10]), default=1) or 1
    ent_items_html = []
    for idx, r in enumerate(ent_rows[:10], 1):
        pct = max(8, int(round((r["total"] / max_ent_total) * 100)))
        badges = []
        if r["name"] in breakout_names:
            badges.append(f"<span class='p-badge b-bo'>{bi('Salto', 'Breakout')}</span>")
        elif r["name"] in new_ent_names:
            badges.append(f"<span class='p-badge b-new'>{bi('Nuevo', 'New')}</span>")
        elif r["delta"] > 0.6:
            badges.append("<span class='p-badge b-up'>▲</span>")
        if r["streak"] >= 2:
            s = r["streak"]
            badges.append(f"<span class='p-badge b-str'>{bi(f'racha {s}d', f'{s}d streak')}</span>")
        badge_str = "".join(badges)
        mini = _mini_bars_html(r["series"], days)
        t = r["total"]
        ent_items_html.append(
            f"<li class='stat-row'>"
            f"<div class='stat-top'>"
            f"<span class='stat-rk'>{idx:02d}</span>"
            f"<span class='k'>{html_escape(r['name'])}</span>"
            f"{badge_str}"
            f"<span class='stat-right'>{mini}<span class='m'>{bi(f'{t} menciones', f'{t} mentions')}</span></span>"
            f"</div>"
            f"<div class='bar-track'><i style='width:{pct}%'></i></div>"
            f"</li>"
        )
    ent_li = "\n".join(ent_items_html) or f"<li class='none'>{bi('Sin datos', 'No data')}</li>"

    # Chips de Nuevos nombres y Saltos
    new_chips = "".join(
        f"<span class='chip chip-new'><b>{html_escape(r['name'])}</b> <small>{r['total']}×</small></span>"
        for r in new_ents[:6]
    ) or f"<span class='none'>{bi('Sin nuevas entradas', 'No new entrants')}</span>"

    bo_chips = "".join(
        f"<span class='chip chip-bo'><b>{html_escape(r['name'])}</b> <small>+{r['last']} {bi('hoy', 'latest')}</small></span>"
        for r in breakouts[:6]
    ) or f"<span class='none'>{bi('Sin picos bruscos en el cierre', 'No sharp spikes on close')}</span>"

    # Mapa visual de Temas y Rotación
    max_cat_total = max((r["total"] for r in cat_rows), default=1) or 1
    cat_items_html = []
    for r in cat_rows[:8]:
        pct = max(8, int(round((r["total"] / max_cat_total) * 100)))
        share_pct = int(round((r["total"] / max(1, total_analyzed)) * 100))
        delta_pts = int(round(r["rot_delta"] * 100))
        if delta_pts >= 3:
            rot_badge = f"<span class='rot-pill up'>▲ +{delta_pts} pts</span>"
        elif delta_pts <= -3:
            rot_badge = f"<span class='rot-pill down'>▼ {delta_pts} pts</span>"
        else:
            rot_badge = f"<span class='rot-pill flat'>＝ {r['early_share']:.0%} → {r['recent_share']:.0%}</span>"
        mini = _mini_bars_html(r["series"], days)
        t = r["total"]
        cat_items_html.append(
            f"<li class='stat-row'>"
            f"<div class='stat-top'>"
            f"<span class='k'>{bi(human_category(r['name']), human_category_en(r['name']))}</span>"
            f"{rot_badge}"
            f"<span class='stat-right'>{mini}<span class='m'>{share_pct}% · {bi(f'{t} señales', f'{t} signals')}</span></span>"
            f"</div>"
            f"<div class='bar-track cat-bar'><i style='width:{pct}%'></i></div>"
            f"</li>"
        )
    cat_li = "\n".join(cat_items_html) or f"<li class='none'>{bi('Sin datos', 'No data')}</li>"

    risers_chips = "".join(
        f"<div class='rot-item up'><span>{bi(human_category(r['name']), human_category_en(r['name']))}</span>"
        f"<b>{r['early_share']:.0%} → {r['recent_share']:.0%}</b></div>"
        for r in risers
    ) or f"<div class='none'>{bi('Sin subidas marcadas', 'No sharp risers')}</div>"

    fallers_chips = "".join(
        f"<div class='rot-item down'><span>{bi(human_category(r['name']), human_category_en(r['name']))}</span>"
        f"<b>{r['early_share']:.0%} → {r['recent_share']:.0%}</b></div>"
        for r in fallers
    ) or f"<div class='none'>{bi('Sin caídas marcadas', 'No sharp drops')}</div>"

    # Ecosistema de fuentes ("Quién cubre")
    max_src_total = max((r["total"] for r in source_rows[:12]), default=1) or 1
    src_cards_html = []
    for r in source_rows[:12]:
        pct = max(8, int(round((r["total"] / max_src_total) * 100)))
        mini = _mini_bars_html(r["series"], days)
        t = r["total"]
        s = r["streak"]
        streak_str = f" · {s}d" if s >= 2 else ""
        src_cards_html.append(
            f"<div class='src-card'>"
            f"<div class='src-card-top'>"
            f"<span class='src'><img src='{html_escape(r['logo'])}' alt='' loading='lazy'/>{html_escape(r['label'])}</span>"
            f"<span class='m'>{t}{streak_str}</span>"
            f"</div>"
            f"<div class='src-card-bot'>"
            f"<div class='bar-track src-bar'><i style='width:{pct}%'></i></div>"
            f"{mini}"
            f"</div>"
            f"</div>"
        )
    source_grid_html = "\n".join(src_cards_html) or f"<div class='none'>{bi('Sin datos', 'No data')}</div>"

    # Riesgos y predicciones confirmadas en la columna de síntesis
    watch_hits_html = ""
    if confirmed_watches:
        w_rows_list = []
        for w in confirmed_watches[:3]:
            ev_html = ""
            if w["evidence"]:
                ev_html = f"<div class='wk-hit-ev'>→ {bi(w['evidence'], w['evidence_en'])}</div>"
            w_rows_list.append(
                f"<div class='wk-watch-hit'>"
                f"<span class='wk-hit-ic'>✓</span>"
                f"<div><div class='wk-hit-t'>{bi(w['text'], w['text_en'])}</div>"
                f"{ev_html}</div></div>"
            )
        w_rows = "".join(w_rows_list)
        watch_hits_html = (
            f"<div class='wk-subbox'>"
            f"<div class='wk-sub-h'><span>{bi('Señales confirmadas esta semana', 'Signals confirmed this week')}</span>"
            f"<span class='lbl'>{len(confirmed_watches)} hit{'s' if len(confirmed_watches) != 1 else ''}</span></div>"
            f"{w_rows}</div>"
        )

    risks_html = ""
    if weekly_risks:
        r_rows = "".join(
            f"<div class='wk-risk-row'><span class='wk-rk-ic'>!</span>"
            f"<div>{bi(r_es, r_en or r_es)}</div></div>"
            for _, r_es, r_en in weekly_risks[:3]
        )
        risks_html = (
            f"<div class='wk-subbox'>"
            f"<div class='wk-sub-h'><span>{bi('Cuellos de botella y riesgos', 'Bottlenecks & key risks')}</span></div>"
            f"{r_rows}</div>"
        )

    # Hilos por entidad y por tema (con score, fecha, fuente y bajada)
    def item_row(it: Dict[str, Any]) -> str:
        title_es = display_title(it)
        title_en = clean_text(it.get("title_en") or "") or clean_text(it.get("title") or "") or title_es
        title_html = bi(title_es, title_en)
        sw_es = truncate_text(clean_text(it.get("so_what") or ""), 135)
        sw_en = truncate_text(clean_text(it.get("so_what_en") or "") or clean_text(it.get("so_what") or ""), 135)
        url = (it.get("url") or it.get("link") or "").strip()
        src = html_escape(source_label(it.get("source") or ""))
        logo = html_escape(source_logo_url(it.get("source") or "", url))
        sc = score_value(it)
        sc_cls = score_tier(sc)
        d_str = html_escape(str(it.get("_date") or ""))
        short_d = d_str[5:] if len(d_str) >= 10 else d_str
        href = safe_href(url)
        tag = "a" if url else "div"
        href_attr = f" href='{href}' target='_blank' rel='noopener noreferrer'" if url else ""
        hw_html = f"<div class='hw'>{bi(sw_es, sw_en)}</div>" if sw_es else ""
        date_span = f" · <span>{short_d}</span>" if short_d else ""
        return (
            f"<{tag} class='hit'{href_attr}>"
            f"<div class='hit-main'>"
            f"<div class='ht'>{title_html}</div>"
            f"{hw_html}"
            f"<div class='hm'><img src='{logo}' alt='' loading='lazy'/><span>{src}</span>"
            f"{date_span}</div>"
            f"</div>"
            f"<span class='score {sc_cls}'>{sc}/100</span>"
            f"</{tag}>"
        )

    def cluster_card(title_html: str, items: List[Dict[str, Any]], series: List[int], total_count: int, group_kind: str) -> str:
        rows = "".join(item_row(it) for it in items) or f"<div class='none'>{bi('Sin piezas esta semana.', 'No items this week.')}</div>"
        mini = _mini_bars_html(series, days)
        cnt_lbl = bi(f"{total_count} menciones", f"{total_count} mentions")
        return (
            f"<section class='widget cluster-card' data-cluster='{group_kind}'>"
            f"<div class='widget-title'><span>{title_html}</span>"
            f"<span class='lbl'>{mini} <b>{cnt_lbl}</b></span></div>"
            f"<div class='hit-list'>{rows}</div>"
            f"</section>"
        )

    clusters = [
        cluster_card(
            html_escape(r["name"]),
            pick_items_for_entity(snapshots, r["name"], limit=5),
            r["series"],
            r["total"],
            "entity",
        )
        for r in ent_rows[:6]
    ]
    cat_clusters = [
        cluster_card(
            bi(human_category(r["name"]), human_category_en(r["name"])),
            pick_items_for_category(snapshots, r["name"], limit=5),
            r["series"],
            r["total"],
            "theme",
        )
        for r in cat_rows[:4]
    ]
    clusters_html = "".join(clusters)
    cat_clusters_html = "".join(cat_clusters)

    period = f"{days[0]} → {days[-1]}"
    n_es = "1 edición" if n == 1 else f"{n} ediciones"
    n_en = "1 edition" if n == 1 else f"{n} editions"
    if n_degraded:
        n_es += f" · {n_degraded} sin filtrar excluida{'s' if n_degraded != 1 else ''}"
        n_en += f" · {n_degraded} unfiltered excluded"
    elif any(s.get("degraded") for s in snapshots):
        n_es += " (sin filtrar)"
        n_en += " (unfiltered)"
    n_txt = bi(n_es, n_en)

    dom_name_html = bi(human_category(dominant["name"]), human_category_en(dominant["name"])) if dominant else bi("Sin datos", "No data")
    hot_ent_name = html_escape(hot_ent["name"]) if hot_ent else "—"
    hot_ent_mentions = hot_ent["total"] if hot_ent else 0
    hot_ent_streak = hot_ent["streak"] if hot_ent else 0
    score_series_int = [int(round(s)) for s in avg_score_per_day]
    score_mini_bars = _mini_bars_html(score_series_int, days)
    vol_mini_bars = _mini_bars_html(total_items_per_day, days)

    out_html = f"""<!doctype html>
<html {HTML_ATTRS}>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
{seo_head("RADAR.IA · Semanal: quién tira y qué temas mandan", path="weekly.html")}{BRAND_HEAD}<script>
  document.addEventListener('error', function(ev){{
    var t = ev.target;
    if (!t || t.tagName !== 'IMG') return;
    var fb = t.getAttribute('data-fb');
    if (fb) {{
      var en = t.getAttribute('data-fb-en');
      t.removeAttribute('data-fb'); t.removeAttribute('data-fb-en'); t.removeAttribute('loading');
      if (en) {{ var c = t.cloneNode(false); c.src = en; c.classList.add('l-en'); t.classList.add('l-es'); t.parentNode.insertBefore(c, t.nextSibling); }}
      t.src = fb;
    }} else {{
      t.style.visibility = 'hidden';
    }}
  }}, true);
</script>
<style>{BRAND_CSS}
  .wrap{{max-width:1500px;margin:0 auto;padding:28px 24px 80px}}

  /* -- Cabecera y KPIs de la semana -- */
  .wk-header{{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;flex-wrap:wrap;margin:0 0 22px}}
  .wk-header .page-h1{{margin:6px 0 8px}}
  .wk-sub{{margin:0;color:var(--muted);font-size:16.5px;max-width:68ch;line-height:1.5}}

  .kpi-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:18px;margin:0 0 26px}}
  .kpi-card{{background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow);padding:14px 16px;display:flex;flex-direction:column;justify-content:space-between;gap:8px}}
  .kpi-card.accent{{background:var(--asphalt);color:#E8E7E1}}
  .kpi-card.accent .kpi-lbl,.kpi-card.accent .kpi-foot{{color:#9C9B95}}
  .kpi-card.accent .kpi-val{{color:#fff}}
  .kpi-card.accent .kicker{{color:var(--lime)}}
  .kpi-top{{display:flex;justify-content:space-between;align-items:center;gap:8px}}
  .kpi-lbl{{font:700 10.5px/1.2 var(--f-mono);text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}}
  .kpi-val{{font:700 clamp(24px,2.2vw,34px)/1.05 var(--f-head);letter-spacing:-.03em;margin:2px 0}}
  .kpi-foot{{display:flex;justify-content:space-between;align-items:center;gap:8px;font:400 11.5px/1.35 var(--f-mono);color:var(--muted);border-top:1px dashed var(--line);padding-top:8px}}
  .kpi-card.accent .kpi-foot{{border-top-color:#34342F}}

  /* -- Mini-barras 7 días -- */
  .mini-bars{{display:inline-flex;align-items:flex-end;gap:2px;height:18px;vertical-align:middle;padding:1px 2px;background:var(--card-2);border:1px solid var(--line)}}
  .kpi-card.accent .mini-bars{{background:#1E1E1C;border-color:#34342F}}
  .mini-bars i{{width:4px;background:var(--muted);opacity:.65;transition:opacity .12s}}
  .mini-bars i.b-zero{{background:var(--line);opacity:.4}}
  .mini-bars i.b-now{{background:var(--orange);opacity:1}}
  .kpi-card.accent .mini-bars i.b-now{{background:var(--lime)}}

  /* -- Puntuaciones con gradiente de intensidad -- */
  .score{{display:inline-flex;align-items:center;font:700 11px/1 var(--f-mono);margin-left:auto;padding:4px 7px;
         border:1px solid var(--line);background:var(--card-2);color:var(--muted);font-variant-numeric:tabular-nums;
         letter-spacing:.02em;flex-shrink:0}}
  .score.s-95{{background:#FF4500;color:#121211;border:2px solid var(--ink);box-shadow:1px 1px 0 var(--ink)}}
  .score.s-88{{background:#FF8A5C;color:#121211;border:1.5px solid var(--ink)}}
  .score.s-80{{background:#FFE4D6;color:#9A3412;border:1.5px solid #EA580C}}
  .score.s-70{{background:#F3F1EA;color:var(--muted);border:1px solid var(--line)}}
  .score.s-low{{background:var(--card-2);color:var(--muted);border:1px solid var(--line);opacity:.82}}
  :root[data-theme="dark"] .score.s-80{{background:rgba(255,87,34,.22);color:#FFA07A;border-color:#EA580C}}
  :root[data-theme="dark"] .score.s-70{{background:#232320;color:var(--muted);border-color:var(--line)}}
  @media (prefers-color-scheme: dark){{
    :root:not([data-theme="light"]) .score.s-80{{background:rgba(255,87,34,.22);color:#FFA07A;border-color:#EA580C}}
    :root:not([data-theme="light"]) .score.s-70{{background:#232320;color:var(--muted);border-color:var(--line)}}
  }}

  /* -- Bloque de apertura: Síntesis + Crónica Día a Día -- */
  .wk-opening{{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,1.25fr);gap:24px;align-items:start;margin:0 0 36px}}
  .widget{{background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow);padding:16px 18px}}
  .widget-title{{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:-16px -18px 14px;
                padding:11px 18px;border-bottom:2px solid var(--ink);background:var(--card-2);
                font:700 12px/1.2 var(--f-mono);text-transform:uppercase;letter-spacing:.06em}}
  .widget-title>span:first-child{{display:flex;align-items:center;gap:9px}}
  .widget-title>span:first-child::before{{content:"";width:10px;height:10px;background:var(--orange);border:2px solid var(--ink);flex-shrink:0}}
  .widget-title .lbl{{display:inline-flex;align-items:center;gap:8px;font:400 10.5px var(--f-mono);color:var(--muted);text-transform:uppercase}}

  .thesis-list{{list-style:none;margin:0;padding:0}}
  .thesis-list li{{display:grid;grid-template-columns:28px 1fr;gap:10px;padding:10px 0;border-bottom:1px dashed var(--line);font-size:14.5px;line-height:1.5}}
  .thesis-list li:first-child{{padding-top:2px}}
  .thesis-list li:last-child{{border-bottom:none;padding-bottom:0}}
  .thesis-list .idx{{font:700 11.5px/1.8 var(--f-mono);color:var(--orange-ink)}}
  .imp-body b{{font-family:var(--f-head);font-weight:700}}

  .wk-subbox{{margin-top:16px;padding-top:14px;border-top:2px solid var(--ink)}}
  .wk-sub-h{{display:flex;justify-content:space-between;align-items:center;font:700 11px/1.2 var(--f-mono);text-transform:uppercase;letter-spacing:.06em;margin-bottom:10px;color:var(--muted)}}
  .wk-watch-hit,.wk-risk-row{{display:flex;gap:10px;align-items:flex-start;padding:7px 0;border-bottom:1px dashed var(--line);font-size:13.5px;line-height:1.45}}
  .wk-watch-hit:last-child,.wk-risk-row:last-child{{border-bottom:none;padding-bottom:0}}
  .wk-hit-ic{{display:inline-grid;place-content:center;width:18px;height:18px;background:var(--open);color:#121211;font:700 11px var(--f-mono);border:1px solid var(--ink);flex-shrink:0;margin-top:1px}}
  .wk-hit-t{{font-weight:600}}
  .wk-hit-ev{{font-size:12px;color:var(--open);margin-top:2px}}
  .wk-rk-ic{{display:inline-grid;place-content:center;width:18px;height:18px;background:#FBBF24;color:#121211;font:700 11px var(--f-mono);border:1px solid var(--ink);flex-shrink:0;margin-top:1px}}

  /* -- Crónica Día a Día -- */
  .tl-list{{display:grid;gap:10px}}
  .tl-day{{display:block;padding:11px 13px;background:var(--card-2);border:1.5px solid var(--ink);transition:transform .08s,box-shadow .08s,background .08s}}
  .tl-day:hover{{transform:translate(-2px,-2px);box-shadow:var(--shadow-sm);background:var(--card)}}
  .tl-head{{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px}}
  .tl-date{{font:700 12px/1 var(--f-mono);color:var(--orange-ink)}}
  .tl-act{{font:700 9.5px/1 var(--f-mono);text-transform:uppercase;padding:3px 5px;border:1px solid var(--ink);background:var(--card)}}
  .tl-act.alert{{background:var(--orange);color:#121211}}
  .tl-act.active{{background:var(--lime);color:#121211}}
  .tl-cnt{{font:400 11px var(--f-mono);color:var(--muted)}}
  .tl-thesis{{margin:0 0 8px;font-size:13.5px;line-height:1.45;color:var(--text);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
  .tl-bar{{height:4px;background:var(--line);overflow:hidden}}
  .tl-bar i{{display:block;height:100%;background:var(--orange)}}

  /* -- Secciones y cabeceras -- */
  .section-head{{display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap;margin:38px 0 16px;padding-bottom:8px;border-bottom:3px solid var(--ink)}}
  .section-h{{display:flex;align-items:center;gap:10px;margin:0;font:700 clamp(18px,1.8vw,22px)/1.15 var(--f-head);text-transform:uppercase;letter-spacing:-.01em}}
  .section-h::before{{content:"";width:12px;height:12px;background:var(--orange);border:2px solid var(--ink);flex-shrink:0}}
  .section-sub{{margin:0;font:400 11.5px var(--f-mono);color:var(--muted);text-transform:uppercase}}

  /* -- Top 6 Señales de la Semana -- */
  .wk-cards{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}}
  .wk-card{{background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow);display:flex;flex-direction:column;transition:transform .1s,box-shadow .1s}}
  .wk-card:hover{{transform:translate(-2px,-2px);box-shadow:6px 6px 0 var(--ink)}}
  .wk-card-media{{position:relative;display:block;border-bottom:2px solid var(--ink);background:var(--asphalt)}}
  .wk-card-img{{display:block;width:100%;aspect-ratio:16/9;object-fit:cover}}
  .wk-rank{{position:absolute;top:8px;left:8px;z-index:2;font:700 11px/1 var(--f-mono);padding:4px 7px;background:var(--asphalt);color:var(--lime);border:1.5px solid var(--ink)}}
  .wk-card-body{{padding:14px 16px 16px;display:flex;flex-direction:column;gap:8px;flex:1}}
  .meta-row{{display:flex;align-items:center;gap:7px;flex-wrap:wrap}}
  .cx-tag{{display:inline-block;font:700 10px/1 var(--f-mono);text-transform:uppercase;padding:3px 6px;border:1px solid var(--ink);background:var(--card-2);color:var(--text);flex-shrink:0}}
  .src{{display:inline-flex;align-items:center;gap:6px;font:600 11px var(--f-mono);color:var(--muted);text-transform:uppercase}}
  .src img{{width:16px;height:16px;padding:1px;background:var(--logo-bg);border:1px solid var(--line);flex-shrink:0}}
  .wk-date{{font:600 10.5px var(--f-mono);color:var(--orange-ink);text-decoration:underline;text-underline-offset:2px}}
  .wk-card-title{{margin:0;font:700 18px/1.22 var(--f-head);letter-spacing:-.01em}}
  .wk-card-title a:hover,.hit:hover .ht{{text-decoration:underline;text-decoration-thickness:2px;text-underline-offset:3px}}
  .wk-card-sw{{margin:0;font-size:13.5px;line-height:1.5;color:var(--muted);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
  .wk-card-foot{{margin-top:auto;padding-top:10px;border-top:1px dashed var(--line)}}
  .fact{{display:flex;gap:8px;align-items:flex-start;font-size:12px;line-height:1.4}}
  .fact .k{{font:700 10px var(--f-mono);text-transform:uppercase;flex-shrink:0;padding:2px 5px;border:1px solid var(--ink);background:var(--orange);color:#121211}}
  .fact .v{{min-width:0;flex:1;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}

  /* -- Dinámica de poder y temas -- */
  .grid{{display:grid;grid-template-columns:1fr 1fr;gap:22px}}
  .wide{{grid-column:1/-1}}
  ul.rows{{list-style:none;padding:0;margin:0}}
  .stat-row{{padding:9px 0;border-bottom:1px dashed var(--line)}}
  .stat-row:first-child{{padding-top:2px}}
  .stat-row:last-child{{border-bottom:none;padding-bottom:0}}
  .stat-top{{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px}}
  .stat-rk{{font:700 11px var(--f-mono);color:var(--orange-ink);width:20px;flex-shrink:0}}
  .k{{font:700 14.5px/1.2 var(--f-head)}}
  .stat-right{{margin-left:auto;display:inline-flex;align-items:center;gap:8px}}
  .m{{font:600 11px var(--f-mono);color:var(--muted);white-space:nowrap}}
  .bar-track{{height:7px;background:var(--card-2);border:1px solid var(--ink);overflow:hidden}}
  .bar-track i{{display:block;height:100%;background:linear-gradient(90deg,var(--orange),#FF8A5C)}}
  .bar-track.cat-bar i{{background:linear-gradient(90deg,var(--ink),var(--orange))}}
  .bar-track.src-bar i{{background:var(--lime)}}

  .p-badge,.rot-pill{{font:700 9.5px/1 var(--f-mono);text-transform:uppercase;padding:3px 5px;border:1px solid var(--ink);flex-shrink:0}}
  .p-badge.b-new{{background:var(--lime);color:#121211}}
  .p-badge.b-bo{{background:var(--orange);color:#121211}}
  .p-badge.b-up{{background:var(--card-2);color:var(--open)}}
  .p-badge.b-str{{background:var(--card-2);color:var(--text)}}
  .rot-pill.up{{background:rgba(14,159,110,.15);color:var(--open);border-color:var(--open)}}
  .rot-pill.down{{background:rgba(200,30,58,.12);color:var(--bad);border-color:var(--bad)}}
  .rot-pill.flat{{background:var(--card-2);color:var(--muted);border-color:var(--line)}}

  .sub-splits{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:14px;padding-top:12px;border-top:2px solid var(--ink)}}
  .sub-box{{background:var(--card-2);border:1px solid var(--line);padding:10px 12px}}
  .sub-box-h{{font:700 10.5px/1.2 var(--f-mono);text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:8px}}
  .chips{{display:flex;gap:6px;flex-wrap:wrap}}
  .chip{{display:inline-flex;align-items:center;gap:5px;font:600 11.5px/1.1 var(--f-mono);padding:4px 7px;border:1px solid var(--ink);background:var(--card)}}
  .chip small{{color:var(--muted);font-size:10px}}
  .chip-new{{border-left:4px solid var(--lime)}}
  .chip-bo{{border-left:4px solid var(--orange)}}

  .rot-item{{display:flex;justify-content:space-between;align-items:center;gap:8px;font-size:12.5px;padding:4px 0;border-bottom:1px dashed var(--line)}}
  .rot-item:last-child{{border-bottom:none;padding-bottom:0}}
  .rot-item b{{font:700 11px var(--f-mono)}}
  .rot-item.up b{{color:var(--open)}}
  .rot-item.down b{{color:var(--bad)}}

  /* -- Ecosistema de fuentes -- */
  .src-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}}
  .src-card{{background:var(--card-2);border:1.5px solid var(--ink);padding:10px 12px;display:flex;flex-direction:column;gap:8px}}
  .src-card-top{{display:flex;justify-content:space-between;align-items:center;gap:8px}}
  .src-card-bot{{display:grid;grid-template-columns:1fr auto;align-items:center;gap:10px}}

  /* -- Explorador de Hilos -- */
  .filter-bar{{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 18px}}
  .f-tab{{appearance:none;font:700 11.5px/1.2 var(--f-mono);text-transform:uppercase;padding:7px 12px;cursor:pointer;
          border:2px solid var(--ink);background:var(--card);color:var(--text);box-shadow:var(--shadow-sm)}}
  .f-tab:hover{{background:rgba(204,255,0,.3)}}
  .f-tab.on{{background:var(--lime);color:#121211}}

  .clusters{{display:grid;grid-template-columns:1fr 1fr;gap:22px}}
  .hit{{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;
        padding:10px 0;border-bottom:1px dashed var(--line)}}
  .hit:first-child{{padding-top:2px}}
  .hit:last-child{{border-bottom:none;padding-bottom:0}}
  .hit-main{{min-width:0;flex:1}}
  .ht{{font:700 14.5px/1.32 var(--f-head)}}
  .hw{{font-size:12.5px;color:var(--muted);line-height:1.45;margin-top:3px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
  .hm{{display:flex;align-items:center;gap:6px;font:400 10.5px var(--f-mono);color:var(--muted);margin-top:5px;text-transform:uppercase}}
  .hm img{{width:14px;height:14px;background:var(--logo-bg);border:1px solid var(--line)}}
  .none{{font-size:13px;color:var(--muted);font-style:italic}}

  footer{{margin-top:56px;padding-top:14px;border-top:3px solid var(--ink);display:flex;justify-content:space-between;
         gap:16px;flex-wrap:wrap;font:400 12px var(--f-mono);color:var(--muted)}}

  @media(max-width:1160px){{
    .kpi-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}
    .wk-opening{{grid-template-columns:1fr}}
    .wk-cards{{grid-template-columns:repeat(2,minmax(0,1fr))}}
    .src-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}
  }}
  @media(max-width:760px){{
    .wrap{{padding:20px 16px 60px}}
    .kpi-grid,.grid,.clusters,.wk-cards,.src-grid,.sub-splits{{grid-template-columns:1fr}}
  }}
</style>
</head>
<body>
{brand_header("weekly")}
<div class="strip">
  <span>{bi("Ventana","Window")} <b class="hl">{html_escape(period)}</b></span>
  <span class="it">{n_txt}</span>
  <span class="it">{total_signals} {bi("señales","signals")} · {total_context} {bi("de contexto","context")}</span>
  <span class="it">{total_dropped} {bi("descartadas por ruido","dropped as noise")}</span>
  <span class="it">{active_sources_count} {bi("fuentes activas","active sources")}</span>
</div>
<div class="wrap">

  <header class="wk-header">
    <div>
      <span class="kicker">{bi("DOSSIER SEMANAL","WEEKLY DOSSIER")} · {html_escape(period)}</span>
      <h1 class="page-h1">{bi("Semanal","Weekly")}</h1>
      <p class="wk-sub">{bi("Síntesis ejecutiva de las últimas ediciones analizadas: qué historias han movido la aguja, quién acumula tracción y hacia dónde rota la conversación estratégica.",
                            "Executive synthesis of the latest analyzed editions: which stories moved the needle, who is gaining traction, and where the strategic conversation is rotating.")}</p>
    </div>
  </header>

  <!-- 4 KPIs de vistazo rápido -->
  <section class="kpi-grid" aria-label="Weekly KPIs">
    <div class="kpi-card accent">
      <div class="kpi-top">
        <span class="kicker">{bi("Volumen filtrado","Filtered volume")}</span>
        {vol_mini_bars}
      </div>
      <div class="kpi-val">{total_analyzed} {bi("piezas","items")}</div>
      <div class="kpi-foot">
        <span>{total_signals} {bi("señales","signals")} · {total_context} ctx</span>
        <span>{total_dropped} {bi("ruido","noise")}</span>
      </div>
    </div>

    <div class="kpi-card">
      <div class="kpi-top">
        <span class="kpi-lbl">{bi("Frente dominante","Dominant front")}</span>
        <span class="cx-tag">{dom_share_pct}% {bi("cuota","share")}</span>
      </div>
      <div class="kpi-val">{dom_name_html}</div>
      <div class="kpi-foot">
        <span>{dominant['total'] if dominant else 0} {bi("apariciones en la semana","appearances this week")}</span>
        <span>{n_txt}</span>
      </div>
    </div>

    <div class="kpi-card">
      <div class="kpi-top">
        <span class="kpi-lbl">{bi("Actor tractor","Lead driver")}</span>
        <span class="p-badge b-str">{bi(f"racha {hot_ent_streak}d", f"{hot_ent_streak}d streak")}</span>
      </div>
      <div class="kpi-val">{hot_ent_name}</div>
      <div class="kpi-foot">
        <span>{hot_ent_mentions} {bi("menciones","mentions")}</span>
        <span>Top 3: {int(round(ent_top3 * 100))}% {bi("del peso","of weight")}</span>
      </div>
    </div>

    <div class="kpi-card">
      <div class="kpi-top">
        <span class="kpi-lbl">{bi("Intensidad media","Average intensity")}</span>
        {score_mini_bars}
      </div>
      <div class="kpi-val">{weekly_avg_score}/100</div>
      <div class="kpi-foot">
        <span>{alert_days}/{n} {bi("días en alerta","days on alert")}</span>
        <span>{active_sources_count} {bi("fuentes","sources")}</span>
      </div>
    </div>
  </section>

  <!-- Apertura a 2 columnas: Lectura de la semana + Crónica Día a Día -->
  <section class="wk-opening">
    <div class="widget">
      <div class="widget-title">
        <span>{bi("Lectura estratégica de la semana","Strategic reading of the week")}</span>
        <span class="lbl">01 / {bi("Síntesis","Synthesis")}</span>
      </div>
      <ol class="thesis-list">{imp_li}</ol>
      {watch_hits_html}
      {risks_html}
    </div>

    <div class="widget">
      <div class="widget-title">
        <span>{bi("La semana día a día","Day-by-day chronicle")}</span>
        <span class="lbl">{bi("Pulsa un día para abrir su edición","Click any day to open its edition")}</span>
      </div>
      <div class="tl-list">{timeline_html}</div>
    </div>
  </section>

  <!-- Top 6 Señales Clave de la Semana -->
  <div class="section-head">
    <h2 class="section-h">{bi("Las señales clave de la semana","Top signals of the week")}</h2>
    <p class="section-sub">{bi("Las 6 noticias de mayor impacto estratégico en la ventana analizada","The 6 highest-impact strategic stories across the analyzed window")}</p>
  </div>
  <section class="wk-cards">
    {top_cards_html}
  </section>

  <!-- Dinámica de Poder y Narrativa -->
  <div class="section-head">
    <h2 class="section-h">{bi("Dinámica de poder y rotación temática","Power dynamics & theme rotation")}</h2>
    <p class="section-sub">{bi("Tracción acumulada, rachas activas y desplazamiento de temas","Cumulative traction, active streaks, and thematic shifts")}</p>
  </div>
  <div class="grid">
    <section class="widget">
      <div class="widget-title">
        <span>{bi("Quién tira de la carrera","Who drives the race")}</span>
        <span class="lbl">{bi("7 días · volumen y racha","7 days · volume & streak")}</span>
      </div>
      <ul class="rows">{ent_li}</ul>
      <div class="sub-splits">
        <div class="sub-box">
          <div class="sub-box-h">{bi("Nuevos nombres","New names")}</div>
          <div class="chips">{new_chips}</div>
        </div>
        <div class="sub-box">
          <div class="sub-box-h">{bi("Saltos de cierre","Breakouts")}</div>
          <div class="chips">{bo_chips}</div>
        </div>
      </div>
    </section>

    <section class="widget">
      <div class="widget-title">
        <span>{bi("Temas y rotación narrativa","Themes & narrative rotation")}</span>
        <span class="lbl">{bi("Inicio → cierre de semana","Start → end of week")}</span>
      </div>
      <ul class="rows">{cat_li}</ul>
      <div class="sub-splits">
        <div class="sub-box">
          <div class="sub-box-h">{bi("Temas que suben","Rising themes")}</div>
          {risers_chips}
        </div>
        <div class="sub-box">
          <div class="sub-box-h">{bi("Temas que bajan","Cooling themes")}</div>
          {fallers_chips}
        </div>
      </div>
    </section>

    <section class="widget wide">
      <div class="widget-title">
        <span>{bi("Quién cubre la carrera","Who covers the race")}</span>
        <span class="lbl">{active_sources_count} {bi("fuentes con señal esta semana","sources with signal this week")}</span>
      </div>
      <div class="src-grid">{source_grid_html}</div>
    </section>
  </div>

  <!-- Explorador de Hilos de la Semana -->
  <div class="section-head">
    <h2 class="section-h">{bi("Hilos de la semana","Weekly threads")}</h2>
    <p class="section-sub">{bi("Todas las piezas agrupadas por protagonista y por frente estratégico","All stories grouped by key player and strategic front")}</p>
  </div>
  <div class="filter-bar" id="wk-tabs" role="tablist">
    <button type="button" role="tab" aria-selected="true" class="f-tab on" data-cfilter="all">{bi("Todos los hilos","All threads")}</button>
    <button type="button" role="tab" aria-selected="false" class="f-tab" data-cfilter="entity">{bi("Hilos por entidad","Threads by entity")}</button>
    <button type="button" role="tab" aria-selected="false" class="f-tab" data-cfilter="theme">{bi("Hilos por tema","Threads by theme")}</button>
  </div>

  <div id="block-entity">
    <div class="section-h" style="margin:18px 0 12px;font-size:15px">{bi("Hilos por entidad","Threads by entity")}</div>
    <div class="clusters">{clusters_html}</div>
  </div>

  <div id="block-theme">
    <div class="section-h" style="margin:28px 0 12px;font-size:15px">{bi("Hilos por tema","Threads by theme")}</div>
    <div class="clusters">{cat_clusters_html}</div>
  </div>

  {brand_credits()}
  <footer>
    <span>{n_txt} · {html_escape(period)}</span>
    <span>{total_analyzed} {bi("piezas analizadas","analyzed items")} · {active_sources_count} {bi("fuentes","sources")}</span>
  </footer>
</div>
<script>
  (function(){{
    var tabs = document.querySelectorAll('#wk-tabs .f-tab');
    var bEnt = document.getElementById('block-entity');
    var bThm = document.getElementById('block-theme');
    if (!tabs.length || !bEnt || !bThm) return;
    tabs.forEach(function(btn){{
      btn.addEventListener('click', function(){{
        tabs.forEach(function(x){{
          x.classList.remove('on');
          x.setAttribute('aria-selected', 'false');
        }});
        btn.classList.add('on');
        btn.setAttribute('aria-selected', 'true');
        var f = btn.getAttribute('data-cfilter');
        bEnt.style.display = (f === 'all' || f === 'entity') ? '' : 'none';
        bThm.style.display = (f === 'all' || f === 'theme') ? '' : 'none';
      }});
    }});
  }})();
</script>
{THEME_JS}
</body>
</html>
"""

    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(out_html, encoding="utf-8")


if __name__ == "__main__":
    main()
