"""Portada editorial generada para las fichas del radar.

Lleva solo el TEMA y la FUENTE: el titular ya esta justo debajo, en la card.
Cada tema tiene su color y su motivo grafico, y el dibujo se siembra con el
item (titulo + url), asi que dos cards del mismo tema no salen identicas pero
la misma noticia siempre produce la misma portada.

Es SVG puro, sin filtros ni fuentes externas: va incrustado como data URI en un
<img>, donde no se cargan recursos de fuera.
"""
from __future__ import annotations

import base64
import hashlib
import math
import random

W, H = 640, 360

# tema -> (color de acento, sin uso, motivo)
# Paleta de la marca (moloch.sh / brain.gym) sobre asfalto, como su panel oscuro.
THEME_STYLE = {
    "compute_chips_dc": ("#CCFF00", "", "chips"),
    "frontier_capability": ("#FF5722", "", "waves"),
    "agents_automation": ("#34D399", "", "graph"),
    "model_economics": ("#FBBF24", "", "bars"),
    "model_economics_pricing": ("#FBBF24", "", "bars"),
    "china_stack": ("#FF5C7A", "", "stack"),
    "geopolitics_power": ("#E8E7E1", "", "globe"),
}
DEFAULT_STYLE = ("#FF8A5C", "", "radar")


def xml_escape(text: str) -> str:
    """El & va PRIMERO o se re-escaparian los & de las propias entidades."""
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _n(x: float) -> str:
    """Numero corto para el SVG: un decimal como mucho."""
    return f"{x:.1f}".rstrip("0").rstrip(".")


def _chips(r: random.Random, c: str) -> str:
    """Mapa de obleas: una rejilla de dados con algunos encendidos."""
    cols, rows, size, gap = 9, 6, 30, 8
    x0, y0 = W - cols * (size + gap) - 14, 26
    # Un solo <rect> definido y reutilizado: 54 dados sin repetir atributos.
    out = [f'<defs><rect id="d" width="{size}" height="{size}" rx="5"/></defs><g fill="{c}">']
    for i in range(cols):
        for j in range(rows):
            # Se desvanece hacia la izquierda para dejar sitio al texto.
            fade = ((i + 1) / cols) ** 0.7
            lit = r.random()
            op = (0.95 if lit > 0.84 else 0.42 if lit > 0.55 else 0.14) * fade
            out.append(f'<use href="#d" x="{x0 + i * (size + gap)}" y="{y0 + j * (size + gap)}" opacity="{_n(op)}"/>')
    out.append("</g>")
    return "".join(out)


def _waves(r: random.Random, c: str) -> str:
    """Frente de onda: arcos concentricos que salen de un foco."""
    cx, cy = r.randint(430, 560), r.randint(60, 150)
    out = []
    for k in range(9):
        rad = 34 + k * 38
        out.append(
            f'<circle cx="{cx}" cy="{cy}" r="{rad}" fill="none" stroke="{c}" '
            f'stroke-width="{_n(2.4 - k * 0.2)}" opacity="{_n(0.62 - k * 0.06)}"/>'
        )
    out.append(f'<circle cx="{cx}" cy="{cy}" r="9" fill="{c}"/>')
    for _ in range(5):
        a, rad = r.uniform(0.4, 3.4), r.choice([72, 110, 148, 186, 224])
        out.append(f'<circle cx="{_n(cx + rad * math.cos(a))}" cy="{_n(cy + rad * math.sin(a))}" r="4.5" fill="{c}" opacity=".9"/>')
    return "".join(out)


def _graph(r: random.Random, c: str) -> str:
    """Agentes: nodos enlazados con sus vecinos mas cercanos."""
    # Rejilla con desorden: nodos repartidos por toda la zona, sin amontonarse.
    pts = [
        (300 + col * 80 + r.randint(8, 62), 24 + row * 78 + r.randint(6, 58))
        for row in range(3) for col in range(4)
    ]
    edges = set()
    for i, (x, y) in enumerate(pts):
        near = sorted(range(len(pts)), key=lambda j: (pts[j][0] - x) ** 2 + (pts[j][1] - y) ** 2)[1:3]
        edges.update((min(i, j), max(i, j)) for j in near)
    out = [
        f'<line x1="{pts[i][0]}" y1="{pts[i][1]}" x2="{pts[j][0]}" y2="{pts[j][1]}" stroke="{c}" stroke-width="1.6" opacity=".38"/>'
        for i, j in sorted(edges)
    ]
    for i, (x, y) in enumerate(pts):
        big = i % 4 == 0
        out.append(f'<circle cx="{x}" cy="{y}" r="{11 if big else 6}" fill="{c}" opacity="{".95" if big else ".6"}"/>')
        if big:
            out.append(f'<circle cx="{x}" cy="{y}" r="20" fill="none" stroke="{c}" stroke-width="1.4" opacity=".4"/>')
    return "".join(out)


def _bars(r: random.Random, c: str) -> str:
    """Economia: barras con tendencia y la linea que las une."""
    n, bw, gap = 9, 26, 12
    x0, base = W - n * (bw + gap) - 18, 262
    out, tops = [], []
    h = r.randint(40, 80)
    for i in range(n):
        h = max(26, min(210, h + r.randint(-22, 46)))
        x = x0 + i * (bw + gap)
        out.append(f'<rect x="{x}" y="{base - h}" width="{bw}" height="{h}" rx="4" fill="{c}" opacity="{_n(0.16 + 0.07 * i)}"/>')
        tops.append((x + bw / 2, base - h - 12))
    path = " ".join(f"{'M' if i == 0 else 'L'}{_n(x)} {_n(y)}" for i, (x, y) in enumerate(tops))
    out.append(f'<path d="{path}" fill="none" stroke="{c}" stroke-width="2.6" stroke-linejoin="round" opacity=".95"/>')
    out.append(f'<circle cx="{_n(tops[-1][0])}" cy="{_n(tops[-1][1])}" r="6" fill="{c}"/>')
    return "".join(out)


def _stack(r: random.Random, c: str) -> str:
    """Stack: capas en isometrica, una de ellas resaltada."""
    cx, w, d = r.randint(440, 500), 150, 44
    hot = r.randint(0, 4)
    out = []
    for k in range(5):
        cy = 236 - k * 40
        pts = f"{cx},{cy - d} {cx + w},{cy} {cx},{cy + d} {cx - w},{cy}"
        out.append(
            f'<polygon points="{pts}" fill="{c}" fill-opacity="{".55" if k == hot else ".1"}" '
            f'stroke="{c}" stroke-width="1.8" stroke-opacity="{".95" if k == hot else ".5"}"/>'
        )
    return "".join(out)


def _globe(r: random.Random, c: str) -> str:
    """Geopolitica: esfera con meridianos, paralelos y unos puntos calientes."""
    cx, cy, rad = r.randint(450, 520), 138, 132
    out = [f'<circle cx="{cx}" cy="{cy}" r="{rad}" fill="{c}" fill-opacity=".07" stroke="{c}" stroke-width="2" opacity=".8"/>']
    for rx in (44, 88):
        out.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{rad}" fill="none" stroke="{c}" stroke-width="1.3" opacity=".4"/>')
    out.append(f'<line x1="{cx}" y1="{cy - rad}" x2="{cx}" y2="{cy + rad}" stroke="{c}" stroke-width="1.3" opacity=".4"/>')
    for dy in (-78, -40, 0, 40, 78):
        half = math.sqrt(rad * rad - dy * dy)
        out.append(f'<line x1="{_n(cx - half)}" y1="{cy + dy}" x2="{_n(cx + half)}" y2="{cy + dy}" stroke="{c}" stroke-width="1.3" opacity=".4"/>')
    for _ in range(4):
        a, q = r.uniform(0, 6.28), r.uniform(0.15, 0.8) * rad
        x, y = cx + q * math.cos(a), cy + q * math.sin(a)
        out.append(f'<circle cx="{_n(x)}" cy="{_n(y)}" r="6" fill="{c}"/><circle cx="{_n(x)}" cy="{_n(y)}" r="14" fill="none" stroke="{c}" stroke-width="1.3" opacity=".5"/>')
    return "".join(out)


def _radar(r: random.Random, c: str) -> str:
    """Por defecto, la marca: un radar con su barrido y varios ecos."""
    cx, cy = r.randint(450, 520), 140
    out = [f'<circle cx="{cx}" cy="{cy}" r="{rad}" fill="none" stroke="{c}" stroke-width="1.5" opacity=".42"/>' for rad in (44, 88, 132)]
    out.append(f'<line x1="{cx - 132}" y1="{cy}" x2="{cx + 132}" y2="{cy}" stroke="{c}" stroke-width="1" opacity=".3"/>')
    out.append(f'<line x1="{cx}" y1="{cy - 132}" x2="{cx}" y2="{cy + 132}" stroke="{c}" stroke-width="1" opacity=".3"/>')
    a = r.uniform(3.6, 5.6)
    x1, y1 = cx + 132 * math.cos(a), cy + 132 * math.sin(a)
    x2, y2 = cx + 132 * math.cos(a + 0.7), cy + 132 * math.sin(a + 0.7)
    out.append(f'<path d="M{cx} {cy} L{_n(x1)} {_n(y1)} A132 132 0 0 1 {_n(x2)} {_n(y2)} Z" fill="{c}" opacity=".2"/>')
    out.append(f'<line x1="{cx}" y1="{cy}" x2="{_n(x2)}" y2="{_n(y2)}" stroke="{c}" stroke-width="2.2" opacity=".9"/>')
    for _ in range(4):
        b, q = r.uniform(0, 6.28), r.uniform(30, 120)
        out.append(f'<circle cx="{_n(cx + q * math.cos(b))}" cy="{_n(cy + q * math.sin(b))}" r="5" fill="{c}" opacity=".9"/>')
    return "".join(out)


MOTIFS = {"chips": _chips, "waves": _waves, "graph": _graph, "bars": _bars,
          "stack": _stack, "globe": _globe, "radar": _radar}


def theme_accent(theme_key: str) -> str:
    accent, _tint, _motif = THEME_STYLE.get((theme_key or "").strip(), DEFAULT_STYLE)
    return accent


def motif_watermark_svg(theme_key: str, seed: str = "") -> str:
    """Motivo geométrico limpio (sin texto) para el fondo atmosférico del Hero Dossier."""
    accent, _tint, motif = THEME_STYLE.get((theme_key or "").strip(), DEFAULT_STYLE)
    rng = random.Random(int(hashlib.md5((seed or theme_key or "").encode("utf-8")).hexdigest()[:12], 16))
    art = MOTIFS[motif](rng, accent)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" preserveAspectRatio="xMaxYMin slice" aria-hidden="true">'
        f'{art}'
        f'</svg>'
    )


def cover_svg(
    theme_key: str,
    theme_label: str,
    source: str,
    seed: str = "",
    entity: str = "",
    score: int = 0,
) -> str:
    accent, _tint, motif = THEME_STYLE.get((theme_key or "").strip(), DEFAULT_STYLE)
    rng = random.Random(int(hashlib.md5((seed or theme_key or "").encode("utf-8")).hexdigest()[:12], 16))
    art = MOTIFS[motif](rng, accent)
    label = xml_escape((theme_label or "Señal")[:26].upper())  # mayusculas ANTES de escapar: &AMP; no es XML
    src = xml_escape((source or "")[:36].upper())
    ent_raw = (entity or "").strip()
    ent = xml_escape(ent_raw[:20].upper()) if ent_raw else ""
    head = "'Space Grotesk', 'Arial Narrow', Arial, sans-serif"
    mono = "'JetBrains Mono', ui-monospace, Menlo, monospace"

    # Etiqueta compacta de tema arriba a la izquierda (píldora brutalista)
    pill_w = max(92, int(len(label) * 9.8) + 28)
    top_pill = (
        f'<rect x="34" y="30" width="{pill_w}" height="30" fill="#181816" stroke="{accent}" stroke-width="1.8"/>'
        f'<rect x="34" y="30" width="8" height="30" fill="{accent}"/>'
        f'<text x="52" y="50" fill="#F4F3EF" font-family="{mono}" font-size="13" font-weight="700" letter-spacing=".8">{label}</text>'
    )

    # Sello opcional de puntuación arriba a la derecha
    score_badge = ""
    if isinstance(score, (int, float)) and score > 0:
        sc_int = int(round(score))
        sc_fill = "#FF4500" if sc_int >= 95 else ("#FF8A5C" if sc_int >= 88 else "#242421")
        sc_txt = "#121211" if sc_int >= 88 else "#E8E7E1"
        score_badge = (
            f'<rect x="{W - 96}" y="28" width="62" height="32" fill="{sc_fill}" stroke="#E8E7E1" stroke-width="1.6"/>'
            f'<text x="{W - 65}" y="50" text-anchor="middle" fill="{sc_txt}" font-family="{mono}" font-size="16" font-weight="700">{sc_int}</text>'
        )

    # Bloque tipográfico principal abajo a la izquierda: entidad protagonista o tema
    if ent:
        ent_size = 44 if len(ent_raw) <= 11 else (36 if len(ent_raw) <= 15 else 29)
        main_block = (
            f'<rect x="34" y="216" width="6" height="58" fill="{accent}"/>'
            f'<text x="52" y="264" fill="#F4F3EF" font-family="{head}" font-size="{ent_size}" font-weight="700" letter-spacing="-1">{ent}</text>'
        )
    else:
        lbl_size = 34 if len(theme_label or "") <= 18 else 28
        main_block = (
            f'<rect x="34" y="222" width="6" height="48" fill="{accent}"/>'
            f'<text x="52" y="260" fill="#F4F3EF" font-family="{head}" font-size="{lbl_size}" font-weight="700" letter-spacing="-.6">{label}</text>'
        )

    source_row = (
        f'<rect x="34" y="294" width="10" height="10" fill="{accent}"/>'
        f'<text x="54" y="304" fill="#C6C5BE" font-family="{mono}" font-size="13.5" font-weight="600" letter-spacing=".6">{src}</text>'
    ) if src else ""

    # Marcas de registro técnicas en las esquinas
    ticks = (
        f'<path d="M18 32V18H32 M{W-32} 18H{W-18}V32 M18 {H-32}V{H-18}H32 M{W-32} {H-18}H{W-18}V{H-32}" '
        f'fill="none" stroke="#E8E7E1" stroke-opacity=".22" stroke-width="1.4"/>'
    )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}">'
        f'<defs>'
        f'<pattern id="p" width="28" height="28" patternUnits="userSpaceOnUse"><path d="M28 0H0V28" fill="none" stroke="#E8E7E1" stroke-opacity=".055"/></pattern>'
        f'<radialGradient id="g" cx=".76" cy=".34" r=".62"><stop offset="0" stop-color="{accent}" stop-opacity=".24"/><stop offset=".6" stop-color="{accent}" stop-opacity=".06"/><stop offset="1" stop-color="#0E0E0D" stop-opacity="0"/></radialGradient>'
        f'<linearGradient id="v" x1="0" y1="1" x2=".72" y2=".15"><stop offset="0" stop-color="#0E0E0D" stop-opacity=".97"/><stop offset=".52" stop-color="#0E0E0D" stop-opacity=".48"/><stop offset="1" stop-color="#0E0E0D" stop-opacity="0"/></linearGradient>'
        f'</defs>'
        f'<rect width="{W}" height="{H}" fill="#0E0E0D"/>'
        f'<rect width="{W}" height="{H}" fill="url(#p)"/>'
        f'<rect width="{W}" height="{H}" fill="url(#g)"/>'
        f'{art}'
        f'<rect width="{W}" height="{H}" fill="url(#v)"/>'
        f'{ticks}'
        f'{top_pill}'
        f'{score_badge}'
        f'{main_block}'
        f'{source_row}'
        f'</svg>'
    )


def cover_data_uri(
    theme_key: str,
    theme_label: str,
    source: str,
    seed: str = "",
    entity: str = "",
    score: int = 0,
) -> str:
    return svg_data_uri(cover_svg(theme_key, theme_label, source, seed, entity=entity, score=score))


def svg_data_uri(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")
