"""Portada generada para los items sin imagen (o cuya imagen remota no carga).

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


def cover_svg(theme_key: str, theme_label: str, source: str, seed: str = "") -> str:
    accent, tint, motif = THEME_STYLE.get((theme_key or "").strip(), DEFAULT_STYLE)
    rng = random.Random(int(hashlib.md5((seed or theme_key or "").encode("utf-8")).hexdigest()[:12], 16))
    art = MOTIFS[motif](rng, accent)
    label = xml_escape((theme_label or "Señal")[:26].upper())  # mayusculas ANTES de escapar: &AMP; no es XML
    src = xml_escape((source or "")[:40].upper())
    head = "'Space Grotesk', 'Arial Narrow', Arial, sans-serif"
    mono = "'JetBrains Mono', ui-monospace, Menlo, monospace"
    tw = max(60, int(len(label) * 23.5))  # ancho aproximado de la etiqueta en mayusculas
    source_row = (
        f'<rect x="40" y="298" width="12" height="12" fill="{accent}" stroke="#E8E7E1" stroke-width="2"/>'
        f'<text x="62" y="309" fill="#E8E7E1" font-family="{mono}" font-size="15" font-weight="600" letter-spacing=".5">{src}</text>'
    ) if src else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}">'
        f'<defs>'
        f'<pattern id="p" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M24 0H0V24" fill="none" stroke="#E8E7E1" stroke-opacity=".06"/></pattern>'
        # Velo de asfalto abajo a la izquierda: la etiqueta se lee sobre cualquier motivo.
        f'<linearGradient id="v" x1="0" y1="1" x2=".75" y2=".1"><stop offset="0" stop-color="#0F0F0E" stop-opacity=".96"/><stop offset=".55" stop-color="#0F0F0E" stop-opacity=".4"/><stop offset="1" stop-color="#0F0F0E" stop-opacity="0"/></linearGradient>'
        f'</defs>'
        f'<rect width="{W}" height="{H}" fill="#0F0F0E"/><rect width="{W}" height="{H}" fill="url(#p)"/>'
        f'{art}'
        f'<rect width="{W}" height="{H}" fill="url(#v)"/>'
        # Etiqueta de tema en bloque de color con sombra dura, como las tags de la marca.
        f'<rect x="46" y="236" width="{tw + 28}" height="50" fill="#E8E7E1"/>'
        f'<rect x="40" y="230" width="{tw + 28}" height="50" fill="{accent}" stroke="#E8E7E1" stroke-width="2"/>'
        f'<text x="54" y="268" fill="#121211" font-family="{head}" font-size="34" font-weight="700" letter-spacing="-.5">{label}</text>'
        f'{source_row}'
        f'</svg>'
    )


def cover_data_uri(theme_key: str, theme_label: str, source: str, seed: str = "") -> str:
    svg = cover_svg(theme_key, theme_label, source, seed)
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")
