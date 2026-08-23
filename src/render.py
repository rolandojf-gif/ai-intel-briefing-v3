"""Render del radar diario estilo Perplexity Discover.

Direccion visual: carbon + turquesa de Perplexity (#191a1a / #20b8cd), tipografia
Space Grotesk para titulares e Inter para cuerpo, y la sena de identidad del feed
Discover: rejilla de cards con imagen 16:9 arriba y titular debajo, con tabs de
tema filtrables en cliente. La capa de memoria y el mercado viven en la sidebar.
"""

from collections import Counter
from datetime import datetime
from urllib.parse import urlparse
import re

from jinja2 import Environment, select_autoescape


# -- Utilidades de texto -----------------------------------------------------

def _safe_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return "#"
    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return raw
    return "#"


def truncate_text(text: str, limit: int = 140) -> str:
    raw = re.sub(r"\s+", " ", (text or "").strip())
    if len(raw) <= limit:
        return raw
    return raw[: max(0, limit - 1)].rstrip() + "…"


def clean_text(text: str) -> str:
    """Limpia restos de scraping: markdown de imagenes, urls sueltas, espacios."""
    raw = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text or "")
    raw = re.sub(r"https?://\S+", " ", raw)
    raw = re.sub(r"&#\d+;", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def display_title(item: dict) -> str:
    """Prefiere el titular reescrito por el LLM: los originales llegan sucios."""
    t = clean_text(item.get("title_es") or "")
    if not t:
        t = clean_text(item.get("title") or "")
    return t or "(sin titulo)"


# -- Fuentes -----------------------------------------------------------------

SOURCE_DOMAIN_HINTS = {
    "openai": "openai.com",
    "anthropic": "anthropic.com",
    "deepmind": "deepmind.google",
    "google ai": "blog.google",
    "meta ai": "ai.meta.com",
    "mistral": "mistral.ai",
    "qwen": "qwenlm.github.io",
    "deepseek": "deepseek.com",
    "moonshot": "moonshot.cn",
    "chinatalk": "chinatalk.media",
    "semianalysis": "semianalysis.com",
    "semiwiki": "semiwiki.com",
    "nvidia": "nvidia.com",
    "epoch": "epoch.ai",
    "interconnects": "interconnects.ai",
    "import ai": "importai.substack.com",
    "latent space": "latent.space",
    "simon willison": "simonwillison.net",
    "hugging face": "huggingface.co",
    "arc prize": "arcprize.org",
    "artificial analysis": "artificialanalysis.ai",
    "openrouter": "openrouter.ai",
    "supermicro": "supermicro.com",
    "reuters": "reuters.com",
    "bloomberg": "bloomberg.com",
    "business insider": "businessinsider.com",
    "yahoo finance": "finance.yahoo.com",
    "venturebeat": "venturebeat.com",
    "the verge": "theverge.com",
    "techcrunch": "techcrunch.com",
    "ars technica": "arstechnica.com",
    "techradar": "techradar.com",
}


def source_label(source: str) -> str:
    raw = (source or "Fuente").strip()
    if raw.startswith("X @"):
        return raw.replace("X @", "@", 1)
    return raw.replace(" (AI)", "")


def source_logo_url(source: str, url: str = "") -> str:
    src = (source or "").strip().lower()
    for key, domain in SOURCE_DOMAIN_HINTS.items():
        if key in src:
            return f"https://www.google.com/s2/favicons?domain={domain}&sz=64"
    host = urlparse(url or "").netloc.replace("www.", "")
    return f"https://www.google.com/s2/favicons?domain={host or 'github.com'}&sz=64"


def _xml_escape(text: str) -> str:
    """Escapa texto para insertarlo en un SVG.

    El & va PRIMERO o se re-escaparian los & de las propias entidades.
    """
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _wrap_svg_title(title: str, per_line: int = 32, max_lines: int = 3) -> list[str]:
    """Parte el titular en lineas cortas por limite de palabra.

    SVG no reajusta texto solo: `width` en <text> no hace nada, asi que un
    titular largo se salia del lienzo. Hay que partirlo a mano en <tspan>.
    """
    words = (title or "").split()
    lines: list[str] = []
    current = ""
    for w in words:
        candidate = f"{current} {w}".strip()
        if len(candidate) <= per_line:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = w
        if len(lines) == max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)

    if not lines:
        return ["AI Intelligence"]
    # Si sobraron palabras, marcamos el corte en la ultima linea visible.
    used = sum(len(x.split()) for x in lines)
    if used < len(words):
        lines[-1] = lines[-1].rstrip(",;:.") + "…"
    return lines


def item_fallback_image(item: dict) -> str:
    """Genera una imagen SVG tematica si el articulo no tiene imagen OpenGraph.

    Todo el texto insertado se escapa: las etiquetas "COMPUTE & CHIPS" y
    "AGENTS & REASONING" llevaban un & literal, que es XML invalido, y el
    navegador descartaba el SVG entero mostrando el icono de imagen rota.
    Afectaba a cualquier item sin imagen OG con esos dos temas.
    """
    theme = (item.get("strategic_theme") or item.get("primary") or "ai").lower()

    if "chip" in theme or "compute" in theme or "infra" in theme:
        c1, c2 = "#1c1e1e", "#12343c"
        accent = "#20b8cd"
        label = "COMPUTE & CHIPS"
    elif "model" in theme or "frontier" in theme:
        c1, c2 = "#1c1e1e", "#0f3b33"
        accent = "#34d1b2"
        label = "FRONTIER MODELS"
    elif "agent" in theme:
        c1, c2 = "#1c1e1e", "#2a2145"
        accent = "#b28bf2"
        label = "AGENTS & REASONING"
    else:
        c1, c2 = "#1c1e1e", "#33291a"
        accent = "#e8b750"
        label = "STRATEGIC INTEL"

    lines = _wrap_svg_title(display_title(item) or "AI Intelligence")
    tspans = "".join(
        f'<tspan x="40" dy="{0 if idx == 0 else 34}">{_xml_escape(line)}</tspan>'
        for idx, line in enumerate(lines)
    )
    source = _xml_escape(source_label(item.get("source", ""))[:38])

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 360" width="100%" height="100%">
  <defs>
    <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{c1}"/>
      <stop offset="100%" stop-color="{c2}"/>
    </linearGradient>
    <radialGradient id="r" cx="80%" cy="20%" r="60%">
      <stop offset="0%" stop-color="{accent}" stop-opacity="0.22"/>
      <stop offset="100%" stop-color="{c1}" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="640" height="360" fill="url(#g)"/>
  <rect width="640" height="360" fill="url(#r)"/>
  <circle cx="540" cy="70" r="130" fill="{accent}" opacity="0.10"/>
  <text x="40" y="76" fill="{accent}" font-family="system-ui, -apple-system, sans-serif" font-size="14" font-weight="800" letter-spacing="2">{_xml_escape(label)}</text>
  <text y="150" fill="#eceeed" font-family="system-ui, -apple-system, sans-serif" font-size="27" font-weight="700">{tspans}</text>
  <line x1="40" y1="308" x2="600" y2="308" stroke="#3d4040" stroke-width="1"/>
  <text x="40" y="332" fill="#9b9f9e" font-family="system-ui, sans-serif" font-size="12">{source}</text>
</svg>'''
    import base64
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


# -- Temas y puntuacion ------------------------------------------------------

THEME_LABELS = {
    "frontier_capability": "Capacidad frontier",
    "agents_automation": "Agentes",
    "compute_chips_dc": "Compute & chips",
    "model_economics": "Economía de modelos",
    "model_economics_pricing": "Economía de modelos",
    "china_stack": "Stack chino",
    "geopolitics_power": "Geopolítica",
    "other": "Otras señales",
    "misc": "Otras señales",
}


def human_theme(theme: str) -> str:
    key = (theme or "other").strip()
    return THEME_LABELS.get(key, THEME_LABELS.get(key.lower(), key.replace("_", " ").capitalize()))


def score_value(item: dict) -> int:
    for key in ("final_score", "score", "adjusted_score", "heuristic_score"):
        val = item.get(key)
        if isinstance(val, (int, float)):
            return int(round(val))
        if isinstance(val, str):
            try:
                return int(round(float(val)))
            except ValueError:
                continue
    return 0


def item_entities(item: dict, limit: int = 5) -> list[str]:
    out, seen = [], set()
    for e in (item.get("entities") or []):
        if not isinstance(e, str):
            continue
        name = re.sub(r"\s+", " ", e.strip())
        if not name or len(name) < 3 or len(name) > 24 or len(name.split()) > 3:
            continue
        k = name.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(name)
        if len(out) >= limit:
            break
    return out


ENV = Environment(autoescape=select_autoescape(["html", "xml"]))
ENV.filters["safe_url"] = _safe_url

TEMPLATE = ENV.from_string("""
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>AI Strategic Radar</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<style>
  :root{
    --bg:#191a1a; --card:#202222; --card-hover:#262828; --line:#2f3131; --line-2:#3d4040;
    --txt:#e8e8e6; --txt-dim:#c8cbca; --dim:#9b9f9e; --dimmer:#6b6f6e;
    --accent:#20b8cd; --accent-soft:rgba(32,184,205,.12); --accent-line:rgba(32,184,205,.35);
    --green:#4bd48b; --rose:#f2665f; --amber:#e8b750; --violet:#b28bf2;
    --mono:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,monospace;
    --sans:'Inter',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
    --disp:'Space Grotesk','Inter',system-ui,sans-serif;
    --r:16px;
  }
  *{box-sizing:border-box}
  html{-webkit-text-size-adjust:100%}
  body{margin:0;background:var(--bg);color:var(--txt);font-family:var(--sans);line-height:1.5}
  a{color:inherit;text-decoration:none}
  img{max-width:100%}
  .wrap{max-width:1280px;margin:0 auto;padding:0 24px 80px}

  /* -- Barra superior -- */
  .topbar{display:flex;align-items:center;justify-content:space-between;gap:16px;
          padding:18px 0;border-bottom:1px solid var(--line);margin-bottom:20px;flex-wrap:wrap}
  .brand{display:flex;align-items:center;gap:10px;font-family:var(--disp);font-size:17px;font-weight:700;letter-spacing:-.01em}
  .brand .dot{width:9px;height:9px;border-radius:50%;background:var(--accent);box-shadow:0 0 12px var(--accent)}
  .brand .date{font-family:var(--mono);font-size:11px;color:var(--dimmer);font-weight:400;margin-left:6px}
  .top-r{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
  .state{display:inline-flex;align-items:center;gap:7px;font-family:var(--mono);font-size:10px;
         font-weight:700;letter-spacing:.16em;padding:6px 12px;border-radius:999px;border:1px solid}
  .state .sdot{width:5px;height:5px;border-radius:50%;background:currentColor}
  .state.alert{color:var(--rose);border-color:rgba(242,102,95,.4);background:rgba(242,102,95,.08)}
  .state.alert .sdot{animation:pulse 1.8s ease-in-out infinite}
  .state.active{color:var(--amber);border-color:rgba(232,183,80,.4);background:rgba(232,183,80,.08)}
  .state.quiet{color:var(--dim);border-color:var(--line-2);background:var(--card)}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
  .nav{display:flex;gap:6px}
  .nav a{font-size:13px;font-weight:600;padding:7px 15px;border-radius:999px;color:var(--dim)}
  .nav a.on{color:var(--accent);background:var(--accent-soft)}
  .nav a:hover{color:var(--txt)}
  .arch-bar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:0 0 18px;
            padding:10px 14px;background:var(--card);border:1px solid var(--line);border-radius:12px;
            font-size:13px;color:var(--dim)}
  .arch-bar a{color:var(--accent);font-weight:600}
  .arch-bar .here{font-family:var(--mono);font-size:12px;color:var(--txt);font-weight:600}

  /* -- Tesis -- */
  .thesis{padding:6px 0 18px}
  .thesis .lbl{font-family:var(--mono);font-size:10px;letter-spacing:.2em;color:var(--accent);
               text-transform:uppercase;font-weight:700;display:block;margin-bottom:8px}
  .thesis h1{margin:0;font-family:var(--disp);font-size:clamp(20px,2.6vw,28px);line-height:1.3;
             font-weight:600;letter-spacing:-.015em;max-width:62ch;color:var(--txt)}

  .degraded{margin:0 0 18px;padding:12px 16px;border:1px solid rgba(232,183,80,.35);
            border-left:3px solid var(--amber);background:rgba(232,183,80,.06);border-radius:10px;
            font-size:13px;color:#eccd8e;line-height:1.55}

  /* -- Tabs de tema (Discover) -- */
  .tabs{display:flex;gap:8px;flex-wrap:wrap;padding:4px 0 22px}
  .tab{font-size:13px;font-weight:600;padding:8px 16px;border-radius:999px;cursor:pointer;
       border:1px solid var(--line);background:var(--card);color:var(--dim);
       transition:all .15s ease;user-select:none}
  .tab:hover{color:var(--txt);border-color:var(--line-2)}
  .tab.on{color:#0e2b30;background:var(--accent);border-color:var(--accent);font-weight:700}
  .tab .n{font-family:var(--mono);font-size:10.5px;opacity:.75;margin-left:5px}

  /* -- Rejilla principal -- */
  .layout{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:26px;align-items:start}

  /* -- Hero (card destacada Discover) -- */
  .hero{background:var(--card);border:1px solid var(--line);border-radius:var(--r);
        overflow:hidden;margin-bottom:18px;transition:background .15s,border-color .15s}
  .hero:hover{background:var(--card-hover);border-color:var(--line-2)}
  .hero-img{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;background:#141616}
  .hero-body{padding:20px 22px 22px}
  .meta-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px}
  .src{display:inline-flex;align-items:center;gap:7px;font-size:12.5px;font-weight:600;color:var(--dim)}
  .src img{width:16px;height:16px;border-radius:4px;flex-shrink:0}
  .tag{font-family:var(--mono);font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;
       padding:3px 9px;border-radius:999px;color:var(--accent);background:var(--accent-soft);
       border:1px solid var(--accent-line);font-weight:700}
  .score{font-family:var(--mono);font-size:10.5px;color:var(--dimmer);margin-left:auto}
  .copy-btn{font-family:var(--mono);font-size:9.5px;font-weight:700;letter-spacing:.08em;
            text-transform:uppercase;padding:4px 10px;border-radius:999px;cursor:pointer;
            border:1px solid var(--line);background:transparent;color:var(--dim);flex-shrink:0}
  .copy-btn:hover{color:var(--accent);border-color:var(--accent-line);background:var(--accent-soft)}
  .copy-btn.ok{color:#0d2b1c;background:var(--green);border-color:var(--green)}
  .badge-new{font-family:var(--mono);font-size:9px;letter-spacing:.1em;text-transform:uppercase;
             font-weight:700;padding:3px 8px;border-radius:999px;color:#0d2b1c;
             background:var(--green);flex-shrink:0}
  .tab-new.on{color:#0d2b1c;background:var(--green);border-color:var(--green)}
  .multi{font-family:var(--mono);font-size:9.5px;color:var(--violet);border:1px solid rgba(178,139,242,.35);
         background:rgba(178,139,242,.1);padding:3px 8px;border-radius:999px;font-weight:700}
  .hero-title{margin:0 0 10px;font-family:var(--disp);font-size:clamp(19px,2.3vw,26px);
              line-height:1.28;font-weight:700;letter-spacing:-.015em}
  .hero-title a:hover{color:var(--accent)}
  .sw{font-size:14.5px;line-height:1.6;color:var(--txt-dim)}
  .facts{display:grid;gap:8px;margin-top:14px;padding-top:14px;border-top:1px solid var(--line)}
  @media(min-width:860px){.facts.two{grid-template-columns:1fr 1fr;gap:18px}}
  .fact{display:flex;gap:9px;align-items:flex-start;font-size:12.5px;line-height:1.5}
  .fact .k{font-family:var(--mono);font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;
           flex-shrink:0;padding-top:2px;font-weight:700}
  .fact.pw .k{color:var(--violet)} .fact.pw .v{color:#cfc0ee}
  .fact.wn .k{color:var(--amber)}  .fact.wn .v{color:#e3cf9b}
  .ents{display:flex;gap:6px;flex-wrap:wrap;margin-top:12px}
  .ent{font-family:var(--mono);font-size:10px;padding:3px 9px;border-radius:999px;
       background:rgba(255,255,255,.04);color:var(--dim);border:1px solid var(--line)}

  /* -- Rejilla de cards (Discover) -- */
  .grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:var(--r);
        overflow:hidden;display:flex;flex-direction:column;
        transition:background .15s,border-color .15s,transform .15s}
  .card:hover{background:var(--card-hover);border-color:var(--line-2);transform:translateY(-2px)}
  .card-img{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;background:#141616}
  .card-body{padding:14px 16px 16px;display:flex;flex-direction:column;gap:8px;flex:1}
  .card .meta-row{margin-bottom:0}
  .card-title{margin:0;font-family:var(--disp);font-size:16.5px;line-height:1.34;font-weight:600;letter-spacing:-.01em}
  .card-title a:hover{color:var(--accent)}
  .card .sw{font-size:13px;line-height:1.55;color:var(--dim);
            display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
  .card-foot{margin-top:auto;padding-top:10px;border-top:1px solid var(--line);display:grid;gap:6px}
  .card-foot .fact{font-size:11.5px}

  /* -- Contexto -- */
  .section-h{display:flex;align-items:baseline;justify-content:space-between;gap:12px;
             margin:26px 0 14px;padding-bottom:10px;border-bottom:1px solid var(--line)}
  .section-h h2{margin:0;font-family:var(--disp);font-size:15px;font-weight:700}
  .section-h .n{font-family:var(--mono);font-size:10.5px;color:var(--dimmer)}
  .ctx{display:grid;gap:8px}
  .cx{display:flex;gap:12px;align-items:flex-start;padding:13px 16px;background:var(--card);
      border:1px solid var(--line);border-radius:12px}
  .cx:hover{border-color:var(--line-2);background:var(--card-hover)}
  .cx img{width:16px;height:16px;border-radius:4px;flex-shrink:0;margin-top:3px}
  .cx-b{min-width:0;flex:1}
  .cx-t{font-size:14px;font-weight:600;line-height:1.4}
  .cx-t a:hover{color:var(--accent)}
  .cx-w{font-size:12.5px;color:var(--dim);margin-top:3px;line-height:1.5}
  .cx-m{font-family:var(--mono);font-size:9.5px;color:var(--dimmer);margin-top:5px;letter-spacing:.06em}

  .empty{padding:44px 26px;text-align:center;border:1px dashed var(--line-2);border-radius:var(--r);background:var(--card)}
  .empty .big{font-family:var(--disp);font-size:17px;font-weight:650;margin-bottom:8px}
  .empty .sub{font-size:13.5px;color:var(--dim);max-width:52ch;margin:0 auto;line-height:1.6}

  /* -- Sidebar -- */
  .sidebar{display:grid;gap:16px;position:sticky;top:16px}
  .widget{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:16px 18px}
  .widget-title{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin-bottom:13px}
  .widget-title span:first-child{font-family:var(--disp);font-size:14px;font-weight:700}
  .widget-title .lbl{font-family:var(--mono);font-size:9px;letter-spacing:.14em;color:var(--dimmer);text-transform:uppercase}

  .market-grid{display:grid;grid-template-columns:1fr 1fr;gap:9px}
  .m-box{background:rgba(255,255,255,.025);border:1px solid var(--line);border-radius:10px;padding:10px 11px}
  .m-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px}
  .m-lbl{font-size:11px;font-weight:600;color:var(--dim)}
  .m-chg{font-family:var(--mono);font-size:10.5px;font-weight:700}
  .m-chg.pos{color:var(--green)} .m-chg.neg{color:var(--rose)}
  .m-chg.na{color:var(--dimmer);font-weight:500}
  .m-price{font-family:var(--mono);font-size:12.5px;font-weight:700;color:var(--txt);margin-bottom:4px}
  .m-nodata{opacity:.55}
  .m-nodata .m-price{color:var(--dimmer);font-weight:500}
  .spark{width:100%;height:22px;display:block}

  .comp-item{display:flex;justify-content:space-between;align-items:center;gap:10px;
             padding:8px 0;border-bottom:1px solid var(--line)}
  .comp-item:last-child{border-bottom:none;padding-bottom:0}
  .comp-info{display:flex;align-items:center;gap:9px;min-width:0}
  .comp-logo{width:22px;height:22px;border-radius:6px;flex-shrink:0;background:#fff}
  .comp-name{font-size:12.5px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .comp-ticker{font-family:var(--mono);font-size:9.5px;color:var(--dimmer)}
  .comp-val{text-align:right;flex-shrink:0}
  .comp-price{font-family:var(--mono);font-size:11.5px;font-weight:700}
  .comp-price.na{color:var(--dimmer);font-weight:500}
  .comp-chg{font-family:var(--mono);font-size:10px;font-weight:700}
  .comp-chg.pos{color:var(--green)} .comp-chg.neg{color:var(--rose)}
  .comp-chg.na{color:var(--dimmer);font-weight:500}

  .wr{display:flex;gap:10px;align-items:flex-start;padding:8px 0;border-bottom:1px solid var(--line)}
  .wr:last-child{border-bottom:none;padding-bottom:0}
  .wr-ic{font-family:var(--mono);font-size:12px;font-weight:700;flex-shrink:0;line-height:1.5}
  .wr.hit .wr-ic{color:var(--green)} .wr.open .wr-ic{color:var(--dimmer)}
  .wr-t{font-size:12.5px;line-height:1.5}
  .wr.open .wr-t{color:var(--dim)}
  .wr-ev{font-size:11px;color:var(--green);margin-top:3px;line-height:1.4}

  .thr{display:flex;gap:11px;align-items:baseline;padding:8px 0;border-bottom:1px solid var(--line)}
  .thr:last-child{border-bottom:none;padding-bottom:0}
  .thr-d{font-family:var(--mono);font-size:9.5px;font-weight:700;color:var(--violet);flex-shrink:0;
         padding:2px 8px;border:1px solid rgba(178,139,242,.32);border-radius:999px;background:rgba(178,139,242,.08)}
  .thr-t{font-size:12.5px;font-weight:600}
  .thr-l{font-size:11.5px;color:var(--dim);margin-top:2px;line-height:1.4}
  .mv{display:flex;gap:8px;align-items:center;padding:7px 0;border-bottom:1px solid var(--line);font-size:12px;flex-wrap:wrap}
  .mv:last-child{border-bottom:none;padding-bottom:0}
  .mv-b{font-family:var(--mono);font-size:8.5px;letter-spacing:.08em;text-transform:uppercase;
        padding:2px 7px;border-radius:999px;flex-shrink:0;font-weight:700}
  .mv-b.new{color:var(--green);background:rgba(75,212,139,.1);border:1px solid rgba(75,212,139,.3)}
  .mv-b.ret{color:var(--amber);background:rgba(232,183,80,.1);border:1px solid rgba(232,183,80,.3)}
  .mv-b.str{color:var(--accent);background:var(--accent-soft);border:1px solid var(--accent-line)}
  .mv .nm{font-weight:600}
  .mv .dt{color:var(--dimmer);font-family:var(--mono);font-size:10px}
  .none{font-size:12px;color:var(--dimmer);font-style:italic}
  .rk{padding:8px 0;border-bottom:1px solid var(--line);font-size:12.5px;line-height:1.5;color:#e3cf9b}
  .rk:last-child{border-bottom:none;padding-bottom:0}
  .rk.w{color:#cfc0ee}

  footer{margin-top:56px;padding-top:18px;border-top:1px solid var(--line);
         display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;
         font-family:var(--mono);font-size:10px;color:var(--dimmer);letter-spacing:.05em}

  /* -- Responsive -- */
  @media(max-width:1080px){
    .layout{grid-template-columns:1fr}
    .sidebar{position:static}
  }
  @media(max-width:720px){
    .grid{grid-template-columns:1fr}
    .wrap{padding:0 14px 60px}
    .market-grid{grid-template-columns:1fr 1fr}
  }
</style>
</head>
<body>
<div class="wrap">

  <!-- Barra superior -->
  <div class="topbar">
    <div class="brand">
      <span class="dot"></span>
      AI Strategic Radar
      <span class="date">{{ generated_at }}</span>
    </div>
    <div class="top-r">
      <span class="state {{ activity.class }}"><span class="sdot"></span>{{ activity.label }}</span>
      <nav class="nav">
        <a class="{{ 'on' if nav == 'daily' else '' }}" href="{{ root }}index.html">Diario</a>
        <a class="{{ 'on' if nav == 'weekly' else '' }}" href="{{ root }}weekly.html">Semanal</a>
        <a class="{{ 'on' if nav == 'archivo' else '' }}" href="{{ root }}archivo.html">Archivo</a>
      </nav>
    </div>
  </div>

  {% if archive %}
  <div class="arch-bar">
    <a href="{{ root }}archivo.html">← Archivo</a>
    {% if archive.prev %}<a href="{{ root }}d/{{ archive.prev }}.html">{{ archive.prev }}</a>{% endif %}
    <span class="here">{{ generated_at }}</span>
    {% if archive.next %}<a href="{{ root }}d/{{ archive.next }}.html">{{ archive.next }}</a>{% endif %}
    <a href="{{ root }}index.html" style="margin-left:auto">Hoy</a>
  </div>
  {% endif %}

  <!-- Tesis del dia -->
  <div class="thesis">
    <span class="lbl">Tesis del día</span>
    <h1>{{ thesis }}</h1>
  </div>

  {% if degraded %}
  <div class="degraded">
    <b>Modo degradado.</b> El análisis del LLM no está disponible hoy, así que el filtro de
    relevancia no se ha aplicado. Lo que ves está ordenado por heurística y puede contener ruido.
  </div>
  {% endif %}
  {% if x_layer and x_layer.status in ['killed', 'disabled'] %}
  <div class="degraded">
    <b>Capa X apagada.</b>
    {% if x_layer.status == 'disabled' %}
    X_DISABLED=1: no se ha consultado el espejo.
    {% else %}
    El espejo no devolvió posts ({{ x_layer.configured }} cuentas). El briefing sigue con RSS.
    {% endif %}
  </div>
  {% endif %}

  <!-- Tabs de tema -->
  {% if theme_tabs or show_new_tab %}
  <div class="tabs" id="tabs">
    <span class="tab on" data-filter="all">Todas<span class="n">{{ n_signals + n_context }}</span></span>
    {% if show_new_tab %}
    <span class="tab tab-new" data-filter="__new__">Nuevo<span class="n">{{ n_new }}</span></span>
    {% endif %}
    {% for t in theme_tabs %}
    <span class="tab" data-filter="{{ t.key }}">{{ t.label }}<span class="n">{{ t.count }}</span></span>
    {% endfor %}
  </div>
  {% endif %}

  <div class="layout">

    <!-- Columna principal -->
    <div class="main-col">

      {% if hero %}
      <article class="hero" data-theme="{{ hero.theme_key }}" data-new="{{ 1 if hero.is_new else 0 }}">
        <a href="{{ (hero.url or hero.link)|safe_url }}" target="_blank" rel="noopener noreferrer">
          <img class="hero-img" src="{{ hero.image_url }}" alt="" loading="lazy" referrerpolicy="no-referrer"/>
        </a>
        <div class="hero-body">
          <div class="meta-row">
            <span class="tag">{{ hero.theme_label }}</span>
            {% if hero.is_new %}<span class="badge-new">Nuevo</span>{% endif %}
            <span class="src"><img src="{{ hero.logo }}" alt="" loading="lazy"/>{{ hero.source_label }}</span>
            {% if hero.other_sources %}<span class="multi">+{{ hero.other_sources|length }} medios</span>{% endif %}
            <span class="score">{{ hero.score }}</span>
            <button type="button" class="copy-btn" data-copy>Copiar</button>
          </div>
          <h2 class="hero-title">
            <a href="{{ (hero.url or hero.link)|safe_url }}" target="_blank" rel="noopener noreferrer">{{ hero.display_title }}</a>
          </h2>
          {% if hero.so_what %}<div class="sw">{{ hero.so_what }}</div>{% endif %}
          {% if hero.power_shift or hero.watch_next %}
          <div class="facts {% if hero.power_shift and hero.watch_next %}two{% endif %}">
            {% if hero.power_shift %}
            <div class="fact pw"><span class="k">Poder</span><span class="v">{{ hero.power_shift }}</span></div>
            {% endif %}
            {% if hero.watch_next %}
            <div class="fact wn"><span class="k">Vigilar</span><span class="v">{{ hero.watch_next }}</span></div>
            {% endif %}
          </div>
          {% endif %}
          {% if hero.ents %}
          <div class="ents">{% for e in hero.ents %}<span class="ent">{{ e }}</span>{% endfor %}</div>
          {% endif %}
        </div>
      </article>
      {% endif %}

      {% if stream %}
      <div class="grid">
        {% for it in stream %}
        <article class="card" data-theme="{{ it.theme_key }}" data-new="{{ 1 if it.is_new else 0 }}">
          <a href="{{ (it.url or it.link)|safe_url }}" target="_blank" rel="noopener noreferrer">
            <img class="card-img" src="{{ it.image_url }}" alt="" loading="lazy" referrerpolicy="no-referrer"/>
          </a>
          <div class="card-body">
            <div class="meta-row">
              {% if it.is_new %}<span class="badge-new">Nuevo</span>{% endif %}
              <span class="src"><img src="{{ it.logo }}" alt="" loading="lazy"/>{{ it.source_label }}</span>
              {% if it.other_sources %}<span class="multi">+{{ it.other_sources|length }}</span>{% endif %}
              <span class="score">{{ it.score }}</span>
              <button type="button" class="copy-btn" data-copy>Copiar</button>
            </div>
            <h3 class="card-title">
              <a href="{{ (it.url or it.link)|safe_url }}" target="_blank" rel="noopener noreferrer">{{ it.display_title }}</a>
            </h3>
            {% if it.so_what %}<div class="sw">{{ it.so_what }}</div>{% endif %}
            {% if it.power_shift or it.watch_next %}
            <div class="card-foot">
              {% if it.power_shift %}
              <div class="fact pw"><span class="k">Poder</span><span class="v">{{ it.power_shift }}</span></div>
              {% endif %}
              {% if it.watch_next %}
              <div class="fact wn"><span class="k">Vigilar</span><span class="v">{{ it.watch_next }}</span></div>
              {% endif %}
            </div>
            {% endif %}
          </div>
        </article>
        {% endfor %}
      </div>
      {% endif %}

      {% if not hero and not stream %}
      <div class="empty">
        <div class="big">Hoy no ha pasado nada que mueva la aguja.</div>
        <div class="sub">
          El filtro de relevancia descartó todo lo ingerido por irrelevante. Un día sin señal
          también es información: significa que la carrera frontier no se movió.
        </div>
      </div>
      {% endif %}

      {% if context %}
      <div class="section-h">
        <h2>Contexto</h2>
        <span class="n">de fondo, no cambia nada hoy</span>
      </div>
      <div class="ctx">
        {% for it in context %}
        <div class="cx" data-theme="{{ it.theme_key }}" data-new="{{ 1 if it.is_new else 0 }}">
          <img src="{{ it.logo }}" alt="" loading="lazy"/>
          <div class="cx-b">
            <div class="cx-t">
              <a href="{{ (it.url or it.link)|safe_url }}" target="_blank" rel="noopener noreferrer">{{ it.display_title }}</a>
            </div>
            {% if it.so_what %}<div class="cx-w">{{ it.so_what }}</div>{% endif %}
            <div class="cx-m">{{ it.theme_label }} · {{ it.source_label }} · {{ it.score }}</div>
          </div>
        </div>
        {% endfor %}
      </div>
      {% endif %}

    </div>

    <!-- Sidebar -->
    <aside class="sidebar">

      {% if market and market.macro %}
      <div class="widget">
        <div class="widget-title">
          <span>Perspectiva del mercado</span>
          <span class="lbl">Último cierre</span>
        </div>
        <div class="market-grid">
          {% for m in market.macro %}
          <div class="m-box{% if not m.available %} m-nodata{% endif %}">
            <div class="m-header">
              <span class="m-lbl">{{ m.label }}</span>
              {% if m.available %}
              <span class="m-chg {% if m.positive %}pos{% else %}neg{% endif %}">{{ m.change_str }}</span>
              {% else %}
              <span class="m-chg na" title="Cotización no disponible en este run">n/d</span>
              {% endif %}
            </div>
            <div class="m-price">{{ m.price_str }}</div>
            {{ m.sparkline_svg|safe }}
          </div>
          {% endfor %}
        </div>
      </div>
      {% endif %}

      {% if market and market.companies %}
      <div class="widget">
        <div class="widget-title">
          <span>Empresas en tendencia</span>
          <span class="lbl">AI & Semis</span>
        </div>
        <div class="company-list">
          {% for c in market.companies %}
          <div class="comp-item">
            <div class="comp-info">
              <img src="{{ c.logo }}" alt="" class="comp-logo" loading="lazy"/>
              <div>
                <div class="comp-name">{{ c.name }}</div>
                <div class="comp-ticker">{{ c.ticker }} · {{ c.exchange }}</div>
              </div>
            </div>
            <div class="comp-val">
              <div class="comp-price{% if not c.available %} na{% endif %}">{{ c.price_str }}</div>
              {% if c.available %}
              <div class="comp-chg {% if c.positive %}pos{% else %}neg{% endif %}">{{ c.change_str }}</div>
              {% else %}
              <div class="comp-chg na" title="Cotización no disponible en este run">n/d</div>
              {% endif %}
            </div>
          </div>
          {% endfor %}
        </div>
      </div>
      {% endif %}

      {% if watch_resolved %}
      <div class="widget">
        <div class="widget-title">
          <span>Vigilancia de ayer</span>
          <span class="lbl">{{ n_hits }}/{{ watch_resolved|length }} confirmadas</span>
        </div>
        {% for w in watch_resolved %}
        <div class="wr {{ w.status }}">
          <span class="wr-ic">{% if w.status == 'hit' %}✓{% else %}○{% endif %}</span>
          <div>
            <div class="wr-t">{{ w.text }}</div>
            {% if w.evidence %}<div class="wr-ev">→ {{ w.evidence }}</div>{% endif %}
          </div>
        </div>
        {% endfor %}
      </div>
      {% endif %}

      {% if threads or has_moves %}
      <div class="widget">
        <div class="widget-title">
          <span>Memoria del radar</span>
          <span class="lbl">Continuidad</span>
        </div>
        {% for t in threads %}
        <div class="thr">
          <span class="thr-d">DÍA {{ t.days }}</span>
          <div>
            <div class="thr-t">{{ t.label }}</div>
            {% if t.lead %}<div class="thr-l">{{ t.lead }}</div>{% endif %}
          </div>
        </div>
        {% endfor %}
        {% if not threads %}
        <div class="none">Ninguna narrativa encadena 3 o más días.</div>
        {% endif %}
        {% for e in deltas.new_entrants %}
        <div class="mv"><span class="mv-b new">Nuevo</span><span class="nm">{{ e }}</span>
          <span class="dt">primera aparición</span></div>
        {% endfor %}
        {% for r in deltas.returning %}
        <div class="mv"><span class="mv-b ret">Vuelve</span><span class="nm">{{ r.entity }}</span>
          <span class="dt">tras {{ r.silent_days }} días en silencio</span></div>
        {% endfor %}
        {% for s in deltas.streaks %}
        <div class="mv"><span class="mv-b str">Racha</span><span class="nm">{{ s.entity }}</span>
          <span class="dt">{{ s.days }} días seguidos</span></div>
        {% endfor %}
      </div>
      {% endif %}

      {% if risks or watch_list %}
      <div class="widget">
        <div class="widget-title">
          <span>Riesgos y vigilancia</span>
          <span class="lbl">Próximos días</span>
        </div>
        {% for r in risks %}<div class="rk">{{ r }}</div>{% endfor %}
        {% for w in watch_list %}<div class="rk w">{{ w }}</div>{% endfor %}
      </div>
      {% endif %}

    </aside>
  </div>

  <footer>
    <span>{{ n_dropped }} items descartados por el filtro de relevancia</span>
    <span>{{ sources_alive }}/{{ sources_total }} fuentes activas{% if sources_dead %} · sin items: {{ sources_dead }}{% endif %}{% if x_layer and x_layer.status == 'killed' %} · X: kill switch{% elif x_layer and x_layer.status == 'disabled' %} · X: disabled{% elif x_layer and x_layer.status == 'ok' and x_layer.posts %} · X: {{ x_layer.posts }} posts{% endif %}</span>
  </footer>

</div>

<script>
  (function(){
    var params = new URLSearchParams(location.search);
    var d = params.get('date');
    if (d && /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(d)) {
      location.replace('d/' + d + '.html');
      return;
    }

    function ficha(article){
      if (!article) return '';
      var a = article.querySelector('.hero-title a, .card-title a');
      var title = a ? (a.textContent || '').trim() : '';
      var swEl = article.querySelector('.sw');
      var sw = swEl ? (swEl.textContent || '').trim() : '';
      var url = a ? (a.getAttribute('href') || '').trim() : '';
      return [title, sw, url].filter(Boolean).join('\\n\\n');
    }
    function copied(btn){
      btn.classList.add('ok');
      btn.textContent = 'Copiado';
      setTimeout(function(){ btn.classList.remove('ok'); btn.textContent = 'Copiar'; }, 1600);
    }
    function fallback(text, btn){
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed';
      ta.style.left = '-9999px';
      document.body.appendChild(ta);
      ta.select();
      try { if (document.execCommand('copy')) copied(btn); } catch (e) {}
      document.body.removeChild(ta);
    }
    document.querySelectorAll('[data-copy]').forEach(function(btn){
      btn.addEventListener('click', function(ev){
        ev.preventDefault();
        ev.stopPropagation();
        var text = ficha(btn.closest('article'));
        if (!text) return;
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(function(){ copied(btn); }).catch(function(){ fallback(text, btn); });
        } else {
          fallback(text, btn);
        }
      });
    });

    var tabs = document.querySelectorAll('#tabs .tab');
    if (!tabs.length) return;
    tabs.forEach(function(t){
      t.addEventListener('click', function(){
        tabs.forEach(function(x){ x.classList.remove('on'); });
        t.classList.add('on');
        var f = t.getAttribute('data-filter');
        document.querySelectorAll('[data-theme]').forEach(function(c){
          var show;
          if (f === 'all')            show = true;
          else if (f === '__new__')   show = c.getAttribute('data-new') === '1';
          else                        show = c.getAttribute('data-theme') === f;
          c.style.display = show ? '' : 'none';
        });
      });
    });
  })();
</script>
</body>
</html>
""")


def render_index(items, briefing=None, snapshot=None, market=None, nav="daily", root="", archive=None):
    briefing = briefing or {}
    snapshot = snapshot or {}

    if market is None:
        try:
            from src.market import get_market_overview
            market = get_market_overview()
        except Exception:
            market = {}

    enriched = []
    for raw in (items or []):
        it = dict(raw)
        it["score"] = score_value(it)
        it["theme_key"] = (it.get("strategic_theme") or it.get("primary") or "other").strip() or "other"
        it["theme_label"] = human_theme(it["theme_key"])
        it["display_title"] = display_title(it)
        it["so_what"] = truncate_text(clean_text(it.get("so_what") or it.get("why") or ""), 230)
        it["power_shift"] = truncate_text(it.get("power_shift") or "", 120)
        it["watch_next"] = truncate_text(it.get("watch_next") or "", 120)
        it["ents"] = item_entities(it)
        it["source_label"] = source_label(it.get("source", ""))
        it["logo"] = source_logo_url(it.get("source", ""), it.get("url") or it.get("link") or "")
        # "Nuevo" = no aparecio en los snapshots de los ultimos 5 dias.
        # `is_repeat` ya lo calcula apply_novelty_penalty comparando URL
        # canonica y huella del titular contra el historico.
        it["is_new"] = not bool(it.get("is_repeat"))

        img = (it.get("image_url") or "").strip()
        if not img or not img.startswith(("http://", "https://")):
            img = item_fallback_image(it)
        it["image_url"] = img
        enriched.append(it)

    enriched.sort(key=lambda x: x.get("score", 0), reverse=True)

    signals = [it for it in enriched if it.get("layer") == "signal"]
    context = [it for it in enriched if it.get("layer") == "context"]
    if not signals and not context:
        signals = enriched  # modo degradado: sin veredictos, todo a la capa principal

    # El sort por score devolvería un repeat al hero. El radar es "qué cambió hoy".
    from src.main import LEAD_SLOT_COUNT, demote_repeats_from_lead
    signals = demote_repeats_from_lead(signals, LEAD_SLOT_COUNT)

    hero = signals[0] if signals else None
    stream = signals[1:] if len(signals) > 1 else []

    # Tabs de tema estilo Discover: solo los temas presentes hoy, con contador.
    visible = signals + context
    tab_counter = Counter(it["theme_key"] for it in visible)
    theme_tabs = [
        {"key": k, "label": human_theme(k), "count": c}
        for k, c in tab_counter.most_common()
    ]
    if len(theme_tabs) < 2:
        theme_tabs = []  # con un solo tema, las tabs no aportan nada

    # Tab "Nuevo": primeras apariciones. Solo se ofrece si discrimina algo;
    # si todo es nuevo (o nada lo es) el filtro no informaria.
    n_new = sum(1 for it in visible if it.get("is_new"))
    show_new_tab = 0 < n_new < len(visible)

    memory = snapshot.get("memory") or {}
    deltas = memory.get("entity_deltas") or {}
    watch_resolved = memory.get("watch_resolved") or []
    threads = memory.get("threads") or []
    has_moves = bool(deltas.get("new_entrants") or deltas.get("returning") or deltas.get("streaks"))

    thesis = clean_text(briefing.get("thesis") or "")
    if not thesis:
        sigs = briefing.get("signals") or []
        if sigs:
            thesis = clean_text(sigs[0])
        elif signals:
            thesis = signals[0]["display_title"]
        else:
            thesis = "Sin movimientos de frontera hoy."

    health = snapshot.get("source_health") or {}
    dead = health.get("dead") or []

    return TEMPLATE.render(
        generated_at=snapshot.get("date") or datetime.now().strftime("%Y-%m-%d"),
        activity=snapshot.get("activity") or {"label": "ACTIVO", "class": "active"},
        thesis=thesis,
        signals=signals,
        hero=hero,
        stream=stream,
        context=context,
        theme_tabs=theme_tabs,
        show_new_tab=show_new_tab,
        n_new=n_new,
        n_signals=len(signals),
        n_context=len(context),
        n_dropped=snapshot.get("dropped_noise", 0),
        degraded=bool(snapshot.get("degraded")),
        watch_resolved=watch_resolved,
        n_hits=sum(1 for w in watch_resolved if w.get("status") == "hit"),
        threads=threads,
        deltas=deltas,
        has_moves=has_moves,
        risks=(briefing.get("risks") or [])[:3],
        watch_list=(briefing.get("watch") or [])[:3],
        sources_alive=health.get("alive", 0),
        sources_total=health.get("configured", 0),
        sources_dead=", ".join(dead[:4]) if dead else "",
        market=market,
        nav=nav or "daily",
        root=root or "",
        archive=archive,
        x_layer=snapshot.get("x_layer") or (snapshot.get("source_health") or {}).get("x") or {},
    )
