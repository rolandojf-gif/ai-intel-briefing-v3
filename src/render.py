"""Render del radar diario estilo Perplexity Discover.

Direccion visual: Descubrimiento e inteligencia estrategica estilo Perplexity Discover.
Oscuro, jerarquia visual potente con imagenes 16:9 de alta resolucion, perspectiva
de mercado financiero y de semiconductores/IA, y capa de memoria estrategica.
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
    "paymentsdive": "paymentsdive.com",
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


def item_fallback_image(item: dict) -> str:
    """Genera una imagen SVG temática si el artículo no tiene imagen OpenGraph."""
    theme = (item.get("strategic_theme") or item.get("primary") or "ai").lower()
    title = (display_title(item) or "AI Intelligence").replace('"', '&quot;')[:60]
    
    # Paletas de color elegantes según el tema
    if "chip" in theme or "compute" in theme or "infra" in theme:
        c1, c2 = "#0f172a", "#1e1b4b"
        accent = "#38bdf8"
        label = "COMPUTE & CHIPS"
    elif "model" in theme or "frontier" in theme:
        c1, c2 = "#091e1a", "#042f2e"
        accent = "#2dd4bf"
        label = "FRONTIER MODELS"
    elif "agent" in theme:
        c1, c2 = "#1e1035", "#2e1065"
        accent = "#c084fc"
        label = "AGENTS & REASONING"
    else:
        c1, c2 = "#111827", "#1f2937"
        accent = "#fbbf24"
        label = "STRATEGIC INTEL"

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 360" width="100%" height="100%">
  <defs>
    <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{c1}"/>
      <stop offset="100%" stop-color="{c2}"/>
    </linearGradient>
    <radialGradient id="r" cx="80%" cy="20%" r="60%">
      <stop offset="0%" stop-color="{accent}" stop-opacity="0.25"/>
      <stop offset="100%" stop-color="{c1}" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="640" height="360" fill="url(#g)"/>
  <rect width="640" height="360" fill="url(#r)"/>
  <circle cx="540" cy="80" r="140" fill="{accent}" opacity="0.08" filter="blur(40px)"/>
  <text x="40" y="80" fill="{accent}" font-family="system-ui, -apple-system, sans-serif" font-size="14" font-weight="800" letter-spacing="2">{label}</text>
  <text x="40" y="160" fill="#f8fafc" font-family="system-ui, -apple-system, sans-serif" font-size="24" font-weight="700" width="560">{title}</text>
  <line x1="40" y1="310" x2="600" y2="310" stroke="#334155" stroke-width="1"/>
  <text x="40" y="332" fill="#94a3b8" font-family="system-ui, sans-serif" font-size="12">AI Strategic Radar · Frontier Intelligence</text>
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
<title>AI Strategic Radar · Discover</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<style>
  :root{
    --bg:#07090e; --panel:#0d121d; --panel-2:#131b2a; --panel-hover:#172235; --line:#1c2638; --line-2:#2a3850;
    --txt:#f1f5f9; --txt-dim:#cbd5e1; --dim:#8191a6; --dimmer:#4e5d73;
    --cyan:#38bdf8; --teal:#2dd4bf; --blue:#60a5fa; --amber:#fbbf24; --rose:#f43f5e; --violet:#c084fc; --green:#4ade80;
    --mono:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,monospace;
    --sans:'Outfit',Inter,system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
  }
  *{box-sizing:border-box}
  html{-webkit-text-size-adjust:100%}
  body{margin:0;background:var(--bg);color:var(--txt);font-family:var(--sans);line-height:1.5;
       background-image:radial-gradient(1000px 600px at 15% -5%,rgba(56,189,248,.07),transparent 60%),
                        radial-gradient(900px 500px at 85% 0%,rgba(192,132,252,.06),transparent 55%);
       background-attachment:fixed;}
  a{color:inherit;text-decoration:none}
  .wrap{max-width:1280px;margin:0 auto;padding:0 24px 80px}
  .lbl{font-family:var(--mono);font-size:10px;letter-spacing:.18em;text-transform:uppercase;
       color:var(--dim);font-weight:700}

  /* Top Bar */
  .bar{display:flex;justify-content:space-between;align-items:center;gap:16px;
       padding:18px 0;border-bottom:1px solid var(--line);margin-bottom:28px;flex-wrap:wrap}
  .bar-g{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
  .brand{font-family:var(--sans);font-size:17px;font-weight:900;letter-spacing:-.02em;
         background:linear-gradient(to right, #ffffff, var(--cyan));-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
  .date{font-family:var(--mono);font-size:11px;color:var(--dim);letter-spacing:.08em}
  .nav{display:flex;gap:6px}
  .nav a{font-family:var(--sans);font-size:12px;font-weight:600;letter-spacing:.02em;
         padding:6px 14px;border:1px solid var(--line);border-radius:20px;color:var(--dim);background:rgba(13,18,29,.6);
         transition:all .2s ease}
  .nav a.on{color:#fff;border-color:rgba(56,189,248,.5);background:rgba(56,189,248,.15)}
  .nav a:hover{color:var(--txt);border-color:var(--line-2);transform:translateY(-1px)}

  .state{display:inline-flex;align-items:center;gap:8px;font-family:var(--mono);font-size:10px;
         font-weight:700;letter-spacing:.16em;padding:5px 12px;border-radius:20px;border:1px solid}
  .state .dot{width:6px;height:6px;border-radius:50%;background:currentColor}
  .state.alert{color:var(--rose);border-color:rgba(244,63,94,.4);background:rgba(244,63,94,.1)}
  .state.active{color:var(--amber);border-color:rgba(251,191,36,.4);background:rgba(251,191,36,.1)}
  .state.quiet{color:var(--blue);border-color:rgba(96,165,250,.35);background:rgba(96,165,250,.08)}
  .state.alert .dot{animation:pulse 1.8s ease-in-out infinite}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}

  /* Top 3 Discover Cards (Perplexity Discover Style) */
  .discover-grid{display:grid;grid-template-columns:repeat(3, 1fr);gap:18px;margin-bottom:34px}
  @media(max-width:900px){.discover-grid{grid-template-columns:1fr}}
  .disc-card{background:var(--panel);border:1px solid var(--line);border-radius:14px;overflow:hidden;
             display:flex;flex-direction:column;transition:all .25s cubic-bezier(.2,0,0,1);box-shadow:0 8px 24px rgba(0,0,0,.25)}
  .disc-card:hover{border-color:var(--line-2);transform:translateY(-3px);box-shadow:0 14px 34px rgba(0,0,0,.4)}
  .disc-img-wrap{width:100%;height:180px;overflow:hidden;position:relative;background:#05080e}
  .disc-img{width:100%;height:100%;object-fit:cover;display:block;transition:transform .3s ease}
  .disc-card:hover .disc-img{transform:scale(1.05)}
  .disc-body{padding:16px 18px;display:flex;flex-direction:column;flex:1;justify-content:space-between}
  .disc-title{font-size:16px;font-weight:700;line-height:1.35;margin:0 0 10px;color:var(--txt);letter-spacing:-.01em}
  .disc-card:hover .disc-title{color:var(--cyan)}
  .disc-meta{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:auto;padding-top:10px}
  .disc-sources{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--dim);font-weight:600}
  .disc-sources img{width:16px;height:16px;border-radius:4px}
  .disc-tag{font-family:var(--mono);font-size:9px;text-transform:uppercase;padding:3px 8px;border-radius:4px;
            background:rgba(56,189,248,.1);color:var(--cyan);border:1px solid rgba(56,189,248,.25);font-weight:700}

  /* Main 2-Column Grid (70% Content / 30% Market & Radar Sidebar) */
  .main-discover-layout{display:grid;grid-template-columns:1fr 340px;gap:28px;align-items:start}
  @media(max-width:1080px){.main-discover-layout{grid-template-columns:1fr}}

  /* Hero Lead Story */
  .hero-card{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:24px;
             margin-bottom:28px;box-shadow:0 10px 30px rgba(0,0,0,.3);transition:border-color .2s}
  .hero-card:hover{border-color:rgba(56,189,248,.35)}
  .hero-grid{display:grid;grid-template-columns:1.1fr 1fr;gap:24px;align-items:center}
  @media(max-width:760px){.hero-grid{grid-template-columns:1fr}}
  .hero-img-wrap{width:100%;height:260px;border-radius:12px;overflow:hidden;border:1px solid var(--line-2);
                 background:#05080e;box-shadow:0 6px 20px rgba(0,0,0,.4)}
  .hero-img{width:100%;height:100%;object-fit:cover;display:block;transition:transform .3s ease}
  .hero-card:hover .hero-img{transform:scale(1.04)}
  .hero-title{font-size:24px;font-weight:800;line-height:1.25;margin:0 0 12px;letter-spacing:-.02em;color:#fff}
  .hero-title a:hover{color:var(--cyan)}
  .hero-time{font-family:var(--mono);font-size:11px;color:var(--dim);margin-bottom:12px;display:flex;align-items:center;gap:6px}
  .hero-summary{font-size:14.5px;color:var(--txt-dim);line-height:1.55;margin-bottom:16px}
  .hero-foot{display:grid;gap:10px;padding-top:14px;border-top:1px solid var(--line)}

  /* Feed Stream of Signals */
  .section-title{font-size:18px;font-weight:800;letter-spacing:-.01em;margin:0 0 16px;color:#fff;
                 display:flex;align-items:center;justify-content:space-between}
  .section-title .count{font-family:var(--mono);font-size:11px;color:var(--dim);font-weight:500}
  .stream-list{display:grid;gap:16px}
  .stream-card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:20px;
               display:grid;grid-template-columns:1fr 180px;gap:20px;align-items:start;
               transition:all .2s ease;box-shadow:0 6px 20px rgba(0,0,0,.2)}
  @media(max-width:680px){.stream-card{grid-template-columns:1fr}}
  .stream-card:hover{border-color:var(--line-2);background:var(--panel-2);transform:translateY(-2px)}
  .stream-content{min-width:0}
  .stream-top{display:flex;align-items:center;gap:10px;margin-bottom:10px;flex-wrap:wrap}
  .stream-title{font-size:18px;font-weight:700;line-height:1.35;margin:0 0 10px;letter-spacing:-.01em}
  .stream-title a:hover{color:var(--cyan)}
  .stream-sw{font-size:14px;color:var(--txt-dim);line-height:1.55;margin-bottom:12px;border-left:2px solid rgba(56,189,248,.4);padding-left:12px}
  .stream-img-wrap{width:180px;height:120px;border-radius:10px;overflow:hidden;border:1px solid var(--line-2);
                   flex-shrink:0;background:#05080e;box-shadow:0 4px 14px rgba(0,0,0,.3)}
  @media(max-width:680px){.stream-img-wrap{width:100%;height:180px;order:-1}}
  .stream-img{width:100%;height:100%;object-fit:cover;display:block;transition:transform .25s ease}
  .stream-card:hover .stream-img{transform:scale(1.05)}

  .ff{display:flex;gap:8px;align-items:flex-start;font-size:12.5px;line-height:1.45}
  .ff .k{font-family:var(--mono);font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;
         flex-shrink:0;padding-top:2px;font-weight:700}
  .ff.pw .k{color:var(--violet)} .ff.pw .v{color:#e2d9fc}
  .ff.wn .k{color:var(--amber)}  .ff.wn .v{color:#fef08a}
  .ents{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
  .ent{font-family:var(--mono);font-size:10px;padding:3px 8px;border-radius:4px;
       background:rgba(255,255,255,.04);color:var(--dim);border:1px solid var(--line)}

  /* Context Items */
  .ctx-card{background:rgba(13,18,29,.65);border:1px solid var(--line);border-radius:10px;padding:14px 16px;
            display:flex;gap:14px;align-items:center;transition:border-color .15s}
  .ctx-card:hover{border-color:var(--line-2)}
  .ctx-thumb{width:68px;height:48px;border-radius:6px;object-fit:cover;flex-shrink:0;border:1px solid var(--line-2)}
  .ctx-b{flex:1;min-width:0}
  .ctx-t{font-size:14px;font-weight:600;line-height:1.4}
  .ctx-t a:hover{color:var(--cyan)}
  .ctx-m{font-family:var(--mono);font-size:10px;color:var(--dim);margin-top:4px}

  /* Right Sidebar Widgets */
  .sidebar{display:grid;gap:20px}
  .widget{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px;box-shadow:0 8px 24px rgba(0,0,0,.25)}
  .widget-title{font-size:14.5px;font-weight:800;margin:0 0 14px;color:#fff;display:flex;align-items:center;justify-content:space-between}

  /* Market Perspective Widget */
  .market-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
  .m-box{background:var(--panel-2);border:1px solid var(--line);border-radius:8px;padding:10px 12px}
  .m-header{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:4px}
  .m-lbl{font-size:11.5px;font-weight:700;color:var(--dim)}
  .m-chg{font-family:var(--mono);font-size:11px;font-weight:700}
  .m-chg.pos{color:var(--green)}
  .m-chg.neg{color:var(--rose)}
  .m-price{font-size:13px;font-weight:800;color:#fff;margin-bottom:6px}
  .spark{width:100%;height:22px;display:block}

  /* Trending AI Companies Widget */
  .company-list{display:grid;gap:8px}
  .comp-item{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:7px 0;border-bottom:1px solid var(--line)}
  .comp-item:last-child{border-bottom:none}
  .comp-info{display:flex;align-items:center;gap:8px;min-width:0}
  .comp-logo{width:20px;height:20px;border-radius:4px;flex-shrink:0}
  .comp-name{font-size:12.5px;font-weight:700;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .comp-ticker{font-family:var(--mono);font-size:10px;color:var(--dim)}
  .comp-val{text-align:right}
  .comp-price{font-size:12px;font-weight:700;color:#fff}
  .comp-chg{font-family:var(--mono);font-size:10.5px;font-weight:700}
  .comp-chg.pos{color:var(--green)}
  .comp-chg.neg{color:var(--rose)}

  /* Watchlist & Continuity */
  .wr-item{padding:9px 0;border-bottom:1px solid var(--line);display:flex;gap:10px;font-size:12.5px;line-height:1.4}
  .wr-item:last-child{border-bottom:none}
  .wr-ic{font-family:var(--mono);font-weight:800;flex-shrink:0}
  .wr-item.hit .wr-ic{color:var(--green)}
  .wr-item.open .wr-ic{color:var(--dimmer)}
  .wr-item.hit .wr-txt{color:#e2e8f0}
  .wr-item.open .wr-txt{color:var(--dim)}

  .thr-item{padding:8px 0;border-bottom:1px solid var(--line);font-size:12.5px}
  .thr-item:last-child{border-bottom:none}
  .thr-badge{font-family:var(--mono);font-size:9.5px;font-weight:700;color:var(--violet);
             padding:2px 6px;border-radius:3px;background:rgba(192,132,252,.1);border:1px solid rgba(192,132,252,.3);margin-right:6px}

  footer{margin-top:64px;padding-top:20px;border-top:1px solid var(--line);
         display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;
         font-family:var(--mono);font-size:10.5px;color:var(--dimmer);letter-spacing:.05em}
</style>
</head>
<body>
<div class="wrap">

  <!-- Top Navigation Bar -->
  <div class="bar">
    <div class="bar-g">
      <span class="brand">AI Strategic Radar</span>
      <span class="date">{{ generated_at }}</span>
    </div>
    <div class="bar-g">
      <span class="state {{ activity.class }}"><span class="dot"></span>{{ activity.label }}</span>
      <nav class="nav">
        <a class="on" href="index.html">Diario</a>
        <a href="weekly.html">Semanal</a>
      </nav>
    </div>
  </div>

  {% if degraded %}
  <div style="margin-bottom:24px;padding:12px 16px;border-radius:8px;border:1px solid rgba(251,191,36,.4);background:rgba(251,191,36,.08);color:#fde047;font-size:13px">
    <b>Modo degradado.</b> El análisis del LLM no estuvo disponible para esta corrida. Lo que ves está ordenado por heurística.
  </div>
  {% endif %}

  <!-- Top 3 Featured Discover Cards (Perplexity Discover Style) -->
  {% if top_featured %}
  <div class="discover-grid">
    {% for it in top_featured %}
    <article class="disc-card">
      <a href="{{ (it.url or it.link)|safe_url }}" target="_blank" rel="noopener noreferrer" class="disc-img-wrap">
        <img src="{{ it.image_url }}" alt="" class="disc-img" loading="lazy" referrerpolicy="no-referrer"/>
      </a>
      <div class="disc-body">
        <h3 class="disc-title">
          <a href="{{ (it.url or it.link)|safe_url }}" target="_blank" rel="noopener noreferrer">{{ it.display_title }}</a>
        </h3>
        <div class="disc-meta">
          <span class="disc-sources">
            <img src="{{ it.logo }}" alt="" loading="lazy"/>
            {{ it.source_label }}
            {% if it.other_sources %}
            <span style="font-family:var(--mono);font-size:9.5px;color:var(--cyan);background:rgba(56,189,248,.1);padding:1px 6px;border-radius:10px;border:1px solid rgba(56,189,248,.25);margin-left:4px">{{ it.other_sources|length + 1 }} fuentes</span>
            {% endif %}
          </span>
          <span class="disc-tag">{{ it.theme_label }}</span>
        </div>
      </div>
    </article>
    {% endfor %}
  </div>
  {% endif %}

  <!-- Main 2-Column Grid: 70% Analysis & Stream / 30% Market & Continuity -->
  <div class="main-discover-layout">
    
    <!-- Left Column -->
    <div class="main-feed">
      
      <!-- Hero Lead Article -->
      {% if hero %}
      <article class="hero-card">
        <div class="hero-grid">
          <a href="{{ (hero.url or hero.link)|safe_url }}" target="_blank" rel="noopener noreferrer" class="hero-img-wrap">
            <img src="{{ hero.image_url }}" alt="" class="hero-img" loading="lazy" referrerpolicy="no-referrer"/>
          </a>
          <div class="hero-content">
            <div class="hero-time">
              <span class="disc-tag">{{ hero.theme_label }}</span>
              <span>• Noticia Principal</span>
            </div>
            <h2 class="hero-title">
              <a href="{{ (hero.url or hero.link)|safe_url }}" target="_blank" rel="noopener noreferrer">{{ hero.display_title }}</a>
            </h2>
            {% if hero.so_what %}
            <div class="hero-summary">{{ hero.so_what }}</div>
            {% endif %}
            <div class="disc-sources" style="margin-bottom:12px">
              <img src="{{ hero.logo }}" alt="" loading="lazy"/>
              <b>{{ hero.source_label }}</b>
              {% if hero.other_sources %}
              <span style="font-family:var(--mono);font-size:9.5px;color:var(--cyan);background:rgba(56,189,248,.1);padding:1px 6px;border-radius:10px;border:1px solid rgba(56,189,248,.25);margin-left:4px">{{ hero.other_sources|length + 1 }} fuentes</span>
              {% endif %}
            </div>
            {% if hero.power_shift or hero.watch_next %}
            <div class="hero-foot">
              {% if hero.power_shift %}
              <div class="ff pw"><span class="k">Poder</span><span class="v">{{ hero.power_shift }}</span></div>
              {% endif %}
              {% if hero.watch_next %}
              <div class="ff wn"><span class="k">Vigilar</span><span class="v">{{ hero.watch_next }}</span></div>
              {% endif %}
            </div>
            {% endif %}
          </div>
        </div>
      </article>
      {% endif %}

      <!-- Rest of Signals Stream -->
      {% if stream %}
      <div class="section-title">
        <span>Señales del Radar</span>
        <span class="count">{{ stream|length }} adicionales</span>
      </div>

      <div class="stream-list">
        {% for it in stream %}
        <article class="stream-card">
          <div class="stream-content">
            <div class="stream-top">
              <span class="disc-tag">{{ it.theme_label }}</span>
              <span class="disc-sources">
                <img src="{{ it.logo }}" alt="" loading="lazy"/>
                {{ it.source_label }}
                {% if it.other_sources %}
                <span style="font-family:var(--mono);font-size:9.5px;color:var(--cyan);background:rgba(56,189,248,.1);padding:1px 6px;border-radius:10px;border:1px solid rgba(56,189,248,.25);margin-left:4px">{{ it.other_sources|length + 1 }} fuentes</span>
                {% endif %}
              </span>
            </div>
            <h3 class="stream-title">
              <a href="{{ (it.url or it.link)|safe_url }}" target="_blank" rel="noopener noreferrer">{{ it.display_title }}</a>
            </h3>
            {% if it.so_what %}<div class="stream-sw">{{ it.so_what }}</div>{% endif %}
            {% if it.power_shift or it.watch_next %}
            <div style="display:grid;gap:6px;margin-top:10px">
              {% if it.power_shift %}
              <div class="ff pw"><span class="k">Poder</span><span class="v">{{ it.power_shift }}</span></div>
              {% endif %}
              {% if it.watch_next %}
              <div class="ff wn"><span class="k">Vigilar</span><span class="v">{{ it.watch_next }}</span></div>
              {% endif %}
            </div>
            {% endif %}
            {% if it.ents %}
            <div class="ents">{% for e in it.ents %}<span class="ent">{{ e }}</span>{% endfor %}</div>
            {% endif %}
          </div>
          <a href="{{ (it.url or it.link)|safe_url }}" target="_blank" rel="noopener noreferrer" class="stream-img-wrap">
            <img src="{{ it.image_url }}" alt="" class="stream-img" loading="lazy" referrerpolicy="no-referrer"/>
          </a>
        </article>
        {% endfor %}
      </div>
      {% endif %}

      <!-- Context Section -->
      {% if context %}
      <div class="section-title" style="margin-top:40px">
        <span>Contexto y Desarrollos de Fondo</span>
        <span class="count">{{ n_context }} items</span>
      </div>
      <div style="display:grid;gap:10px">
        {% for it in context %}
        <div class="ctx-card">
          <img src="{{ it.image_url }}" alt="" class="ctx-thumb" loading="lazy" referrerpolicy="no-referrer"/>
          <div class="ctx-b">
            <div class="ctx-t">
              <a href="{{ (it.url or it.link)|safe_url }}" target="_blank" rel="noopener noreferrer">{{ it.display_title }}</a>
            </div>
            {% if it.so_what %}<div style="font-size:12.5px;color:var(--dim);margin-top:3px">{{ it.so_what }}</div>{% endif %}
            <div class="ctx-m">{{ it.theme_label }} · {{ it.source_label }}</div>
          </div>
        </div>
        {% endfor %}
      </div>
      {% endif %}

    </div>

    <!-- Right Column Sidebar -->
    <aside class="sidebar">
      
      <!-- Market Perspective Widget -->
      {% if market and market.macro %}
      <div class="widget">
        <div class="widget-title">
          <span>Perspectiva del mercado</span>
          <span class="lbl">ÚLTIMO CIERRE</span>
        </div>
        <div class="market-grid">
          {% for m in market.macro %}
          <div class="m-box">
            <div class="m-header">
              <span class="m-lbl">{{ m.label }}</span>
              <span class="m-chg {% if m.positive %}pos{% else %}neg{% endif %}">{{ m.change_str }}</span>
            </div>
            <div class="m-price">{{ m.price_str }}</div>
            {{ m.sparkline_svg|safe }}
          </div>
          {% endfor %}
        </div>
      </div>
      {% endif %}

      <!-- Trending AI Companies Widget -->
      {% if market and market.companies %}
      <div class="widget">
        <div class="widget-title">
          <span>Empresas en tendencia (AI & Semis)</span>
          <span class="lbl">ÚLTIMO CIERRE</span>
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
              <div class="comp-price">{{ c.price_str }}</div>
              <div class="comp-chg {% if c.positive %}pos{% else %}neg{% endif %}">{{ c.change_str }}</div>
            </div>
          </div>
          {% endfor %}
        </div>
      </div>
      {% endif %}

      <!-- Watchlist Resolution Widget -->
      {% if watch_resolved %}
      <div class="widget">
        <div class="widget-title">
          <span>Lo que ayer dijimos que vigilaras</span>
          <span class="lbl">{{ n_hits }}/{{ watch_resolved|length }} HIT</span>
        </div>
        <div>
          {% for w in watch_resolved %}
          <div class="wr-item {{ w.status }}">
            <span class="wr-ic">{% if w.status == 'hit' %}✓{% else %}○{% endif %}</span>
            <div>
              <div class="wr-txt">{{ w.text }}</div>
              {% if w.evidence %}<div style="font-size:11px;color:var(--green);margin-top:3px">→ {{ w.evidence }}</div>{% endif %}
            </div>
          </div>
          {% endfor %}
        </div>
      </div>
      {% endif %}

      <!-- Memory Threads Widget -->
      {% if threads or has_moves %}
      <div class="widget">
        <div class="widget-title">
          <span>Memoria del radar</span>
          <span class="lbl">CONTINUIDAD</span>
        </div>
        <div>
          {% for t in threads %}
          <div class="thr-item">
            <span class="thr-badge">DÍA {{ t.days }}</span>
            <b>{{ t.label }}</b>
            {% if t.lead %}<div style="font-size:11.5px;color:var(--dim);margin-top:2px">{{ t.lead }}</div>{% endif %}
          </div>
          {% endfor %}
          {% if not threads %}
          <div style="font-size:12px;color:var(--dim);font-style:italic">Sin narrativas prolongadas (>3d).</div>
          {% endif %}
        </div>
      </div>
      {% endif %}

      <!-- Risks & Watchlist -->
      {% if risks or watch_list %}
      <div class="widget">
        <div class="widget-title">
          <span>Próximos Días</span>
          <span class="lbl">A VIGILAR</span>
        </div>
        <div>
          {% for r in risks %}
          <div style="font-size:12px;color:#fde047;padding:6px 0;border-bottom:1px solid var(--line)">⚠️ {{ r }}</div>
          {% endfor %}
          {% for w in watch_list %}
          <div style="font-size:12px;color:#e2d9fc;padding:6px 0;border-bottom:1px solid var(--line)">👁️ {{ w }}</div>
          {% endfor %}
        </div>
      </div>
      {% endif %}

    </aside>

  </div>

  <!-- Footer -->
  <footer>
    <span>{{ n_dropped }} items descartados por el filtro de relevancia</span>
    <span>{{ sources_alive }}/{{ sources_total }} fuentes activas{% if sources_dead %} · sin items: {{ sources_dead }}{% endif %}</span>
  </footer>

</div>
</body>
</html>
""")


def render_index(items, briefing=None, snapshot=None, market=None):
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
        it["theme_label"] = human_theme(it.get("strategic_theme") or it.get("primary") or "other")
        it["display_title"] = display_title(it)
        it["so_what"] = truncate_text(clean_text(it.get("so_what") or it.get("why") or ""), 230)
        it["power_shift"] = truncate_text(it.get("power_shift") or "", 120)
        it["watch_next"] = truncate_text(it.get("watch_next") or "", 120)
        it["ents"] = item_entities(it)
        it["source_label"] = source_label(it.get("source", ""))
        it["logo"] = source_logo_url(it.get("source", ""), it.get("url") or it.get("link") or "")
        
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

    # Partición estricta sin duplicados visuales
    if len(signals) >= 4:
        top_featured = signals[0:3]
        hero = signals[3]
        stream = signals[4:]
    elif len(signals) == 3:
        top_featured = signals[0:2]
        hero = signals[2]
        stream = []
    elif len(signals) == 2:
        top_featured = [signals[1]]
        hero = signals[0]
        stream = []
    elif len(signals) == 1:
        top_featured = []
        hero = signals[0]
        stream = []
    else:
        top_featured = []
        hero = None
        stream = []

    memory = snapshot.get("memory") or {}
    deltas = memory.get("entity_deltas") or {}
    watch_resolved = memory.get("watch_resolved") or []
    threads = memory.get("threads") or []
    has_moves = bool(deltas.get("new_entrants") or deltas.get("returning") or deltas.get("streaks"))

    theme_counter = Counter(it.get("theme_label") for it in signals if it.get("theme_label"))
    dominant = theme_counter.most_common(1)[0][0] if theme_counter else ""

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
        top_featured=top_featured,
        hero=hero,
        stream=stream,
        context=context,
        n_signals=len(signals),
        n_context=len(context),
        n_dropped=snapshot.get("dropped_noise", 0),
        dominant=dominant,
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
    )
