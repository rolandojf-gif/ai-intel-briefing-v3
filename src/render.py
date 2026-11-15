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
from markupsafe import Markup

from src.brand import BASE_CSS as BRAND_CSS, HEAD as BRAND_HEAD, THEME_JS, header as brand_header


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


def item_fallback_image(item: dict) -> str:
    """Portada generada (data URI) para un item sin imagen o con la imagen caida.

    Solo tema y fuente: el titular ya va justo debajo, en la card. El dibujo lo
    hace src/cover.py, con un motivo por tema sembrado con el propio item.
    """
    from src.cover import cover_data_uri

    theme_key = (item.get("strategic_theme") or item.get("primary") or "other").strip() or "other"
    seed = f"{item.get('title') or item.get('title_es') or ''}|{item.get('url') or item.get('link') or ''}"
    return cover_data_uri(theme_key, human_theme(theme_key), source_label(item.get("source", "")), seed)


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
<meta name="description" content="Radar diario de la carrera AGI: modelos frontier, compute, China y agentes. Solo lo que mueve la aguja."/>
{{ brand_head }}<script>
  // Va en <head> para estar escuchando antes de que se pinte la primera imagen.
  // Una imagen remota caida (hotlink bloqueado, 404, caducada) se cambia por la
  // portada generada del item; un logo caido se oculta en vez de dejar el icono roto.
  document.addEventListener('error', function(ev){
    var t = ev.target;
    if (!t || t.tagName !== 'IMG') return;
    var fb = t.getAttribute('data-fb');
    if (fb) { t.removeAttribute('data-fb'); t.src = fb; }
    else { t.style.visibility = 'hidden'; }
  }, true);
</script>
<style>{{ brand_css }}
  .wrap{max-width:1280px;margin:0 auto;padding:28px 24px 80px}
  .stale{font:700 10.5px/1 var(--f-mono);text-transform:uppercase;color:#121211;background:#FBBF24;
         border:1px solid var(--ink);padding:3px 7px}
  .arch-bar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:0 0 22px;padding:10px 14px;
            background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow-sm);font:600 12.5px var(--f-mono);text-transform:uppercase}
  .arch-bar a{color:var(--orange-ink);text-decoration:underline;text-underline-offset:3px}
  .arch-bar .here{background:var(--lime);color:#121211;padding:2px 6px;border:1px solid var(--ink)}

  /* -- Tesis -- */
  .thesis{padding:0 0 22px}
  .thesis .page-h1{margin-top:8px}
  .thesis .tz{font:700 clamp(19px,2.2vw,26px)/1.3 var(--f-head);letter-spacing:-.015em;max-width:64ch;margin:0}
  .notice{margin:0 0 18px;padding:14px 18px;border:2px dashed var(--ink);background:var(--card);font-size:14.5px;line-height:1.55}
  .notice.warn{border-style:solid;box-shadow:inset 6px 0 0 #FBBF24}

  /* -- Tabs de tema -- */
  .tabs{display:flex;gap:10px;flex-wrap:wrap;padding:0 0 24px}
  .tab{font:600 12px/1.2 var(--f-mono);text-transform:uppercase;padding:8px 12px;cursor:pointer;user-select:none;
       border:2px solid var(--ink);background:var(--card);box-shadow:var(--shadow-sm);transition:transform .08s,box-shadow .08s}
  .tab:hover{background:rgba(204,255,0,.3)}
  .tab:active{transform:translate(2px,2px);box-shadow:none}
  .tab.on{background:var(--lime);color:#121211}
  .tab-new.on{background:#34D399;color:#121211}
  .tab .n{font-weight:700;color:var(--orange-ink);margin-left:6px}
  .tab.on .n{color:#121211}

  .layout{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:28px;align-items:start}

  /* -- Hero y cards: bordes de tinta y sombra dura -- */
  .hero,.card{background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow);transition:transform .1s,box-shadow .1s}
  .hero{margin-bottom:22px}
  .hero:hover,.card:hover{transform:translate(-2px,-2px);box-shadow:6px 6px 0 var(--ink)}
  .hero-img,.card-img{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;background:var(--asphalt);border-bottom:2px solid var(--ink)}
  .hero-body{padding:18px 20px 20px}
  .meta-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px}
  .src{display:inline-flex;align-items:center;gap:7px;font:600 11.5px var(--f-mono);color:var(--muted);text-transform:uppercase}
  .src img{width:18px;height:18px;padding:1px;background:var(--logo-bg);border:1px solid var(--line);flex-shrink:0}
  .tag,.badge-new,.multi{display:inline-block;font:700 10.5px/1 var(--f-mono);text-transform:uppercase;padding:4px 6px;
       border:2px solid var(--ink);background:var(--card-2);flex-shrink:0}
  .tag{background:var(--orange);color:#121211}
  .badge-new{background:var(--lime);color:#121211}
  .score{font:700 11px var(--f-mono);color:var(--muted);margin-left:auto}
  .copy-btn{font:700 10.5px/1 var(--f-mono);text-transform:uppercase;padding:5px 8px;cursor:pointer;
            border:2px solid var(--ink);background:var(--card);color:var(--text);flex-shrink:0}
  .copy-btn:hover{background:rgba(204,255,0,.3)}
  .copy-btn.ok{background:#34D399;color:#121211}
  .hero-title{margin:0 0 10px;font:700 clamp(21px,2.4vw,30px)/1.15 var(--f-head);letter-spacing:-.02em}
  .hero-title a:hover,.card-title a:hover,.cx-t a:hover{text-decoration:underline;text-decoration-thickness:2px;text-underline-offset:3px}
  .sw{font-size:15px;line-height:1.6}
  .facts{display:grid;gap:8px;margin-top:14px;padding-top:12px;border-top:1px dashed var(--line)}
  @media(min-width:860px){.facts.two{grid-template-columns:1fr 1fr;gap:18px}}
  .fact{display:flex;gap:9px;align-items:flex-start;font-size:13px;line-height:1.5}
  .fact .k{font:700 10.5px var(--f-mono);text-transform:uppercase;flex-shrink:0;padding:2px 5px;border:1px solid var(--ink)}
  .fact.pw .k{background:var(--orange);color:#121211}
  .fact.wn .k{background:var(--lime);color:#121211}
  .also{font:400 12px/1.7 var(--f-mono);color:var(--muted);margin-top:10px}
  .also a,.also span{color:var(--text)}
  .also a{text-decoration:underline;text-underline-offset:2px}
  .also a:hover{background:rgba(204,255,0,.3)}
  .ents{display:flex;gap:6px;flex-wrap:wrap;margin-top:12px}
  .ent{font:600 10.5px var(--f-mono);padding:3px 6px;border:1px solid var(--ink);background:var(--card-2)}

  .grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:22px}
  .card{display:flex;flex-direction:column}
  .card-body{padding:14px 16px 16px;display:flex;flex-direction:column;gap:8px;flex:1}
  .card .meta-row{margin-bottom:0}
  .card-title{margin:0;font:700 19px/1.2 var(--f-head);letter-spacing:-.01em}
  .card .sw{font-size:14px;line-height:1.55;color:var(--muted);
            display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
  .card-foot{margin-top:auto;padding-top:10px;border-top:1px dashed var(--line);display:grid;gap:6px}
  .card-foot .fact{font-size:12px}

  /* -- Contexto -- */
  .section-h{margin:34px 0 14px}
  .section-h h2{margin:0}
  .ctx{display:grid;gap:10px}
  .cx{display:flex;gap:12px;align-items:flex-start;padding:12px 14px;background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow-sm)}
  .cx img{width:20px;height:20px;padding:2px;background:var(--logo-bg);border:1px solid var(--line);flex-shrink:0;margin-top:2px}
  .cx-b{min-width:0;flex:1}
  .cx-t{font:700 15.5px/1.3 var(--f-head)}
  .cx-w{font-size:13.5px;color:var(--muted);margin-top:3px;line-height:1.5}
  .cx-m{font:400 11px var(--f-mono);color:var(--muted);margin-top:6px;text-transform:uppercase}

  .empty{padding:40px 26px;text-align:center;border:2px dashed var(--ink);background:var(--card)}
  .empty .big{font:700 20px var(--f-head);margin-bottom:8px;text-transform:uppercase}
  .empty .sub{font-size:14px;color:var(--muted);max-width:52ch;margin:0 auto;line-height:1.6}

  /* -- Sidebar -- */
  .sidebar{display:grid;gap:22px;position:sticky;top:16px}
  .widget{background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow);padding:14px 16px}
  .widget-title{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:-14px -16px 12px;
                padding:10px 16px;border-bottom:2px solid var(--ink);background:var(--card-2)}
  .widget-title span:first-child{display:flex;align-items:center;gap:9px;font:700 12px/1.2 var(--f-mono);text-transform:uppercase;letter-spacing:.06em}
  .widget-title span:first-child::before{content:"";width:10px;height:10px;background:var(--orange);border:2px solid var(--ink)}
  .widget-title .lbl{font:400 10px var(--f-mono);color:var(--muted);text-transform:uppercase}

  .market-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
  .m-box{background:var(--card-2);border:1px solid var(--ink);padding:9px 10px}
  .m-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px}
  .m-lbl{font:600 11px var(--f-mono);text-transform:uppercase;color:var(--muted)}
  .m-chg{font:700 11px var(--f-mono)}
  .m-chg.pos,.comp-chg.pos{color:var(--open)} .m-chg.neg,.comp-chg.neg{color:var(--bad)}
  .m-chg.na,.comp-chg.na,.comp-price.na{color:var(--muted);font-weight:400}
  .m-price{font:700 14px var(--f-mono);margin-bottom:4px;font-variant-numeric:tabular-nums}
  .m-nodata{opacity:.55}
  .spark{width:100%;height:22px;display:block}
  .spark.pos polyline{stroke:var(--open)} .spark.neg polyline{stroke:var(--bad)}

  .comp-item{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:8px 0;border-bottom:1px dashed var(--line)}
  .comp-item:last-child{border-bottom:none;padding-bottom:0}
  .comp-info{display:flex;align-items:center;gap:9px;min-width:0}
  .comp-logo{width:24px;height:24px;padding:2px;flex-shrink:0;background:var(--logo-bg);border:1px solid var(--line)}
  .comp-name{font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .comp-ticker{font:400 10px var(--f-mono);color:var(--muted)}
  .comp-val{text-align:right;flex-shrink:0}
  .comp-price{font:700 12px var(--f-mono);font-variant-numeric:tabular-nums}
  .comp-chg{font:700 10.5px var(--f-mono)}

  .wr,.thr,.mv,.rk{padding:8px 0;border-bottom:1px dashed var(--line)}
  .wr:last-child,.thr:last-child,.mv:last-child,.rk:last-child{border-bottom:none;padding-bottom:0}
  .wr{display:flex;gap:10px;align-items:flex-start}
  .wr-ic{font:700 12px/1.5 var(--f-mono);flex-shrink:0}
  .wr.hit .wr-ic{color:var(--open)} .wr.open .wr-ic{color:var(--muted)}
  .wr-t{font-size:13px;line-height:1.5}
  .wr.open .wr-t{color:var(--muted)}
  .wr-ev{font-size:12px;color:var(--open);margin-top:3px;line-height:1.4}
  .thr{display:flex;gap:11px;align-items:baseline}
  .thr-d{font:700 10px var(--f-mono);flex-shrink:0;padding:3px 5px;border:2px solid var(--ink);background:var(--ink);color:var(--paper)}
  .thr-t{font-size:13px;font-weight:600}
  .thr-l{font-size:12px;color:var(--muted);margin-top:2px;line-height:1.4}
  .mv{display:flex;gap:8px;align-items:center;font-size:12.5px;flex-wrap:wrap}
  .mv-b{font:700 9.5px/1 var(--f-mono);text-transform:uppercase;padding:3px 5px;border:1px solid var(--ink);flex-shrink:0}
  .mv-b.new{background:var(--lime);color:#121211}
  .mv-b.ret{background:#FBBF24;color:#121211}
  .mv-b.str{background:var(--orange);color:#121211}
  .mv .nm{font-weight:600}
  .mv .dt{color:var(--muted);font:400 10.5px var(--f-mono)}
  .none{font-size:12.5px;color:var(--muted);font-style:italic}
  .rk{font-size:13px;line-height:1.5}
  .rk::before{content:"!";display:inline-grid;place-content:center;width:16px;height:16px;margin-right:7px;
              font:700 10px var(--f-mono);background:#FBBF24;color:#121211;border:1px solid var(--ink);vertical-align:1px}
  .rk.w::before{content:"→";background:var(--lime)}

  footer{margin-top:56px;padding-top:14px;border-top:3px solid var(--ink);display:flex;justify-content:space-between;
         gap:16px;flex-wrap:wrap;font:400 12px var(--f-mono);color:var(--muted)}

  @media(max-width:1080px){.layout{grid-template-columns:1fr}.sidebar{position:static}}
  @media(max-width:720px){
    .grid{grid-template-columns:1fr}
    .wrap{padding:20px 16px 60px}
    .tabs{flex-wrap:nowrap;overflow-x:auto;margin:0 -16px;padding:2px 16px 20px;scrollbar-width:none}
    .tabs::-webkit-scrollbar{display:none}
    .tab{flex:0 0 auto;white-space:nowrap}
  }
</style>
</head>
<body>
{{ brand_header }}
<div class="strip">
  <span>Edición <b class="hl">{{ generated_at }}</b>{% if nav == 'daily' and not archive %} <span class="stale" id="stale" data-date="{{ generated_at }}" hidden></span>{% endif %}</span>
  <span class="it {{ 'bad' if activity.class == 'alert' else ('warn' if activity.class == 'active' else '') }}">{{ activity.label }}</span>
  <span class="it">{{ n_signals }} señales{% if n_context %} · {{ n_context }} de contexto{% endif %}</span>
  <span class="it{% if sources_dead %} warn{% endif %}">{{ sources_alive }}/{{ sources_total }} fuentes</span>
  {% if x_layer and x_layer.status == 'ok' and x_layer.posts %}<span class="it">X: {{ x_layer.posts }} posts</span>{% elif x_layer and x_layer.status in ['killed','disabled'] %}<span class="it bad">X apagada</span>{% endif %}
  <a class="r" href="{{ root }}archivo.html">Archivo ↗</a>
</div>
<div class="wrap">

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
    <span class="kicker">{{ generated_at }} · lectura del día</span>
    <h1 class="page-h1">Tesis del día</h1>
    <p class="tz">{{ thesis }}</p>
  </div>

  {% if degraded %}
  <div class="notice warn">
    <b>Modo degradado.</b> El análisis del LLM no está disponible hoy, así que el filtro de
    relevancia no se ha aplicado. Lo que ves está ordenado por heurística y puede contener ruido.
  </div>
  {% endif %}
  {% if x_layer and x_layer.status in ['killed', 'disabled'] %}
  <div class="notice">
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
          <img class="hero-img" src="{{ hero.image_url }}"{% if hero.fallback_image %} data-fb="{{ hero.fallback_image }}"{% endif %} alt="" referrerpolicy="no-referrer"/>
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
          {% if hero.also %}
          <div class="also">También en:
            {% for a in hero.also %}{% if a.url %}<a href="{{ a.url }}" target="_blank" rel="noopener noreferrer">{{ a.label }}</a>{% else %}<span>{{ a.label }}</span>{% endif %}{% if not loop.last %} · {% endif %}{% endfor %}{% if hero.also_more %} · +{{ hero.also_more }}{% endif %}
          </div>
          {% endif %}
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
            <img class="card-img" src="{{ it.image_url }}"{% if it.fallback_image %} data-fb="{{ it.fallback_image }}"{% endif %} alt="" loading="lazy" referrerpolicy="no-referrer"/>
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
            {% if it.also %}
            <div class="also">También en:
              {% for a in it.also %}{% if a.url %}<a href="{{ a.url }}" target="_blank" rel="noopener noreferrer">{{ a.label }}</a>{% else %}<span>{{ a.label }}</span>{% endif %}{% if not loop.last %} · {% endif %}{% endfor %}{% if it.also_more %} · +{{ it.also_more }}{% endif %}
            </div>
            {% endif %}
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
        <h2 class="sec">Contexto</h2>
        <p class="sec-sub">De fondo: no cambia nada hoy</p>
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
  // El radar se regenera en dias alternos. Si la edicion no es de hoy, se dice:
  // sin esto la portada de ayer se lee como si fuera la de hoy.
  (function(){
    var el = document.getElementById('stale');
    if (!el) return;
    var p = (el.getAttribute('data-date') || '').split('-');
    if (p.length !== 3) return;
    var edition = new Date(+p[0], +p[1] - 1, +p[2]);
    var now = new Date();
    var today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    var days = Math.round((today - edition) / 86400000);
    if (!(days >= 1)) return;
    el.textContent = days === 1 ? 'edición de ayer' : 'edición de hace ' + days + ' días';
    el.hidden = false;
  })();
</script>
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
{{ theme_js }}
</body>
</html>
""")


ALSO_MAX = 6  # medios listados en "Tambien en" antes de resumir con +N


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

        # "Tambien en": el resto de medios que cuentan el mismo suceso. Los
        # fusionados tras el LLM traen enlace; los del dedup de ingest, solo nombre.
        also, seen_also = [], set()
        for rel in (it.get("related") or []):
            label = source_label(rel.get("source", "")) if isinstance(rel, dict) else ""
            url = _safe_url(rel.get("url", "")) if isinstance(rel, dict) else "#"
            if label and label not in seen_also:
                seen_also.add(label)
                also.append({"label": label, "url": "" if url == "#" else url})
        for src in (it.get("other_sources") or []):
            label = source_label(src) if isinstance(src, str) else ""
            if label and label not in seen_also:
                seen_also.add(label)
                also.append({"label": label, "url": ""})
        it["also"] = also[:ALSO_MAX]
        it["also_more"] = max(0, len(also) - ALSO_MAX)

        # La portada generada sirve dos veces: como imagen si el item no trae
        # ninguna, y como respaldo en cliente (data-fb) si la remota no carga.
        fallback = item_fallback_image(it)
        img = (it.get("image_url") or "").strip()
        if not img or not img.startswith(("http://", "https://")):
            img, fallback = fallback, ""
        it["image_url"] = img
        it["fallback_image"] = fallback
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
        brand_head=Markup(BRAND_HEAD),
        brand_css=Markup(BRAND_CSS),
        brand_header=brand_header(nav or "daily", root or ""),
        theme_js=Markup(THEME_JS),
        x_layer=snapshot.get("x_layer") or (snapshot.get("source_health") or {}).get("x") or {},
    )
