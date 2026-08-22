"""Render del radar diario.

Dirección visual: terminal de inteligencia. Oscuro, jerarquía brutal — una tesis,
pocas señales grandes, y la capa de memoria (qué cambió respecto a ayer) como
parte estructural, no como adorno.

Principio de diseño: el número de items lo decide el día, no la plantilla.
Un día con 2 señales muestra 2 señales y lo dice.
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
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root{
    --bg:#05070c; --panel:#0a0f18; --panel-2:#0d1420; --line:#1a2435; --line-2:#243044;
    --txt:#e6eefc; --dim:#7c8ba3; --dimmer:#4a5768;
    --cyan:#5eead4; --blue:#60a5fa; --amber:#fbbf24; --rose:#fb7185; --violet:#a78bfa; --green:#4ade80;
    --mono:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,monospace;
    --sans:'Inter',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
  }
  *{box-sizing:border-box}
  html{-webkit-text-size-adjust:100%}
  body{margin:0;background:var(--bg);color:var(--txt);font-family:var(--sans);line-height:1.5;
       background-image:radial-gradient(900px 500px at 15% -5%,rgba(94,234,212,.05),transparent 60%),
                        radial-gradient(800px 400px at 85% 0%,rgba(167,139,250,.05),transparent 55%);
       background-attachment:fixed;}
  a{color:inherit;text-decoration:none}
  .wrap{max-width:1180px;margin:0 auto;padding:0 20px 72px}
  .lbl{font-family:var(--mono);font-size:10px;letter-spacing:.18em;text-transform:uppercase;
       color:var(--dim);font-weight:500}

  .bar{display:flex;justify-content:space-between;align-items:center;gap:16px;
       padding:16px 0;border-bottom:1px solid var(--line);margin-bottom:34px;flex-wrap:wrap}
  .bar-g{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
  .brand{font-family:var(--mono);font-size:11px;letter-spacing:.24em;text-transform:uppercase;
         color:var(--cyan);font-weight:700}
  .date{font-family:var(--mono);font-size:11px;color:var(--dimmer);letter-spacing:.08em}
  .nav{display:flex;gap:4px}
  .nav a{font-family:var(--mono);font-size:10px;letter-spacing:.12em;text-transform:uppercase;
         padding:6px 13px;border:1px solid var(--line);border-radius:2px;color:var(--dim)}
  .nav a.on{color:var(--cyan);border-color:rgba(94,234,212,.4);background:rgba(94,234,212,.06)}
  .nav a:hover{color:var(--txt);border-color:var(--line-2)}

  .state{display:inline-flex;align-items:center;gap:8px;font-family:var(--mono);font-size:10px;
         font-weight:700;letter-spacing:.18em;padding:6px 12px;border-radius:2px;border:1px solid}
  .state .dot{width:5px;height:5px;border-radius:50%;background:currentColor}
  .state.alert{color:var(--rose);border-color:rgba(251,113,133,.42);background:rgba(251,113,133,.08)}
  .state.active{color:var(--amber);border-color:rgba(251,191,36,.42);background:rgba(251,191,36,.08)}
  .state.quiet{color:var(--blue);border-color:rgba(96,165,250,.38);background:rgba(96,165,250,.07)}
  .state.alert .dot{animation:pulse 1.8s ease-in-out infinite}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}

  .thesis .lbl{display:block;margin-bottom:14px}
  .thesis h1{margin:0;font-size:clamp(26px,4vw,46px);line-height:1.17;font-weight:700;
             letter-spacing:-.02em;max-width:20ch}
  .meta-row{display:flex;gap:22px;flex-wrap:wrap;margin-top:20px;padding-top:16px;border-top:1px solid var(--line)}
  .meta-row .m{font-family:var(--mono);font-size:11px;color:var(--dimmer)}
  .meta-row .m b{color:var(--txt);font-weight:700}

  .degraded{margin:24px 0;padding:13px 16px;border:1px solid rgba(251,191,36,.35);
            border-left:2px solid var(--amber);background:rgba(251,191,36,.05);border-radius:2px;
            font-size:13px;color:#fcd34d;line-height:1.55}

  section{margin-top:52px}
  .head{display:flex;align-items:baseline;justify-content:space-between;gap:14px;
        padding-bottom:11px;border-bottom:1px solid var(--line);margin-bottom:24px}
  .head h2{margin:0;font-size:14px;font-weight:700;letter-spacing:.02em}
  .head .n{font-family:var(--mono);font-size:11px;color:var(--dimmer)}

  .wgrid{display:grid;gap:9px}
  .wr{display:flex;gap:13px;align-items:flex-start;padding:13px 15px;border:1px solid var(--line);
      border-radius:3px;background:var(--panel)}
  .wr.hit{border-color:rgba(74,222,128,.32);background:rgba(74,222,128,.045)}
  .wr-ic{font-family:var(--mono);font-size:13px;font-weight:700;flex-shrink:0;line-height:1.45}
  .wr.hit .wr-ic{color:var(--green)}
  .wr.open .wr-ic{color:var(--dimmer)}
  .wr-b{flex:1;min-width:0}
  .wr-t{font-size:13.5px;line-height:1.45}
  .wr.open .wr-t{color:var(--dim)}
  .wr-ev{margin-top:6px;font-family:var(--mono);font-size:11px;color:var(--green);line-height:1.4}

  .sigs{display:grid;gap:2px}
  .sig{display:grid;grid-template-columns:50px 1fr;border:1px solid var(--line);
       background:var(--panel);border-radius:3px;overflow:hidden;transition:border-color .16s,background .16s}
  .sig:hover{border-color:var(--line-2);background:var(--panel-2)}
  .sig-n{display:flex;flex-direction:column;align-items:center;padding:20px 0;gap:9px;
         border-right:1px solid var(--line);background:rgba(0,0,0,.22)}
  .sig-n .num{font-family:var(--mono);font-size:15px;font-weight:700;color:var(--cyan)}
  .sig-n .sc{font-family:var(--mono);font-size:9.5px;color:var(--dimmer)}
  .sig-b{padding:19px 22px;min-width:0}
  .sig-top{display:flex;gap:9px;align-items:center;flex-wrap:wrap;margin-bottom:11px}
  .tag{font-family:var(--mono);font-size:9.5px;letter-spacing:.11em;text-transform:uppercase;
       padding:3px 8px;border-radius:2px;border:1px solid var(--line-2);color:var(--dim)}
  .tag.th{color:var(--cyan);border-color:rgba(94,234,212,.3);background:rgba(94,234,212,.05)}
  .src{display:inline-flex;align-items:center;gap:6px;font-family:var(--mono);font-size:10px;color:var(--dimmer)}
  .src img{width:13px;height:13px;border-radius:2px;opacity:.75;flex-shrink:0}
  .sig-t{font-size:19px;font-weight:650;line-height:1.32;letter-spacing:-.008em;margin:0 0 12px}
  .sig-t a:hover{color:var(--cyan)}
  .sw{font-size:14.5px;line-height:1.58;color:#c3d3ec;border-left:2px solid rgba(94,234,212,.42);padding-left:14px}
  .sig-foot{display:grid;gap:9px;margin-top:15px;padding-top:14px;border-top:1px solid var(--line)}
  @media(min-width:760px){.sig-foot.two{grid-template-columns:1fr 1fr;gap:22px}}
  .ff{display:flex;gap:9px;align-items:flex-start;font-size:12.5px;line-height:1.45}
  .ff .k{font-family:var(--mono);font-size:9.5px;letter-spacing:.11em;text-transform:uppercase;
         flex-shrink:0;padding-top:2px;font-weight:700}
  .ff.pw .k{color:var(--violet)} .ff.pw .v{color:#cdbdf8}
  .ff.wn .k{color:var(--amber)}  .ff.wn .v{color:#f5d78e}
  .ents{display:flex;gap:6px;flex-wrap:wrap;margin-top:13px}
  .ent{font-family:var(--mono);font-size:10px;padding:3px 8px;border-radius:2px;
       background:rgba(255,255,255,.035);color:var(--dim);border:1px solid var(--line)}

  .empty{padding:46px 26px;text-align:center;border:1px dashed var(--line-2);border-radius:3px;background:var(--panel)}
  .empty .big{font-size:17px;font-weight:650;margin-bottom:9px}
  .empty .sub{font-size:13.5px;color:var(--dim);max-width:52ch;margin:0 auto;line-height:1.6}

  .grid2{display:grid;gap:14px}
  @media(min-width:820px){.grid2{grid-template-columns:1fr 1fr}}
  .card{border:1px solid var(--line);border-radius:3px;background:var(--panel);padding:17px 19px}
  .card .lbl{display:block;margin-bottom:14px}
  .thr{display:flex;gap:13px;align-items:baseline;padding:10px 0;border-bottom:1px solid var(--line)}
  .thr:last-child{border-bottom:none;padding-bottom:0}
  .thr-d{font-family:var(--mono);font-size:10px;font-weight:700;color:var(--violet);flex-shrink:0;
         padding:2px 7px;border:1px solid rgba(167,139,250,.32);border-radius:2px;background:rgba(167,139,250,.07)}
  .thr-t{font-size:13.5px;font-weight:600}
  .thr-l{font-size:12px;color:var(--dim);margin-top:3px;line-height:1.4}
  .mv{display:flex;gap:9px;align-items:center;padding:9px 0;border-bottom:1px solid var(--line);
      font-size:13px;flex-wrap:wrap}
  .mv:last-child{border-bottom:none;padding-bottom:0}
  .mv-b{font-family:var(--mono);font-size:9px;letter-spacing:.09em;text-transform:uppercase;
        padding:2px 7px;border-radius:2px;flex-shrink:0;font-weight:700}
  .mv-b.new{color:var(--green);background:rgba(74,222,128,.1);border:1px solid rgba(74,222,128,.3)}
  .mv-b.ret{color:var(--amber);background:rgba(251,191,36,.1);border:1px solid rgba(251,191,36,.3)}
  .mv-b.str{color:var(--blue);background:rgba(96,165,250,.1);border:1px solid rgba(96,165,250,.3)}
  .mv .nm{font-weight:600}
  .mv .dt{color:var(--dimmer);font-family:var(--mono);font-size:11px}
  .none{font-size:12.5px;color:var(--dimmer);font-style:italic}
  .rk{padding:11px 0;border-bottom:1px solid var(--line);font-size:13.5px;line-height:1.5;color:#f3d99b}
  .rk:last-child{border-bottom:none;padding-bottom:0}
  .rk.w{color:#cdbdf8}

  .ctx{display:grid;gap:2px}
  .cx{display:flex;gap:14px;align-items:baseline;padding:13px 15px;border:1px solid var(--line);
      border-radius:3px;background:rgba(10,15,24,.55)}
  .cx:hover{border-color:var(--line-2)}
  .cx-s{font-family:var(--mono);font-size:10.5px;color:var(--dimmer);flex-shrink:0;width:26px}
  .cx-b{min-width:0;flex:1}
  .cx-t{font-size:14px;line-height:1.4;font-weight:500}
  .cx-t a:hover{color:var(--cyan)}
  .cx-w{font-size:12.5px;color:var(--dim);margin-top:5px;line-height:1.45}
  .cx-m{font-family:var(--mono);font-size:9.5px;color:var(--dimmer);margin-top:6px;letter-spacing:.06em}

  footer{margin-top:64px;padding-top:20px;border-top:1px solid var(--line);
         display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;
         font-family:var(--mono);font-size:10px;color:var(--dimmer);letter-spacing:.06em}
</style>
</head>
<body>
<div class="wrap">

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

  <div class="thesis">
    <span class="lbl">Tesis del día</span>
    <h1>{{ thesis }}</h1>
    <div class="meta-row">
      <span class="m"><b>{{ n_signals }}</b> señales</span>
      <span class="m"><b>{{ n_context }}</b> contexto</span>
      {% if dominant %}<span class="m">Dominante: <b>{{ dominant }}</b></span>{% endif %}
    </div>
  </div>

  {% if degraded %}
  <div class="degraded">
    <b>Modo degradado.</b> El análisis del LLM no está disponible hoy, así que el filtro de
    relevancia no se ha aplicado. Lo que ves está ordenado por heurística y puede contener ruido.
  </div>
  {% endif %}

  {% if watch_resolved %}
  <section>
    <div class="head">
      <h2>Lo que ayer dijimos que vigilaras</h2>
      <span class="n">{{ n_hits }}/{{ watch_resolved|length }} confirmadas</span>
    </div>
    <div class="wgrid">
      {% for w in watch_resolved %}
      <div class="wr {{ w.status }}">
        <span class="wr-ic">{% if w.status == 'hit' %}✓{% else %}○{% endif %}</span>
        <div class="wr-b">
          <div class="wr-t">{{ w.text }}</div>
          {% if w.evidence %}<div class="wr-ev">→ {{ w.evidence }}</div>{% endif %}
        </div>
      </div>
      {% endfor %}
    </div>
  </section>
  {% endif %}

  <section>
    <div class="head">
      <h2>Señales</h2>
      <span class="n">{{ n_signals }} hoy</span>
    </div>
    {% if signals %}
    <div class="sigs">
      {% for it in signals %}
      <article class="sig">
        <div class="sig-n">
          <span class="num">{{ '%02d'|format(loop.index) }}</span>
          <span class="sc">{{ it.score }}</span>
        </div>
        <div class="sig-b">
          <div class="sig-top">
            <span class="tag th">{{ it.theme_label }}</span>
            <span class="src"><img src="{{ it.logo }}" alt="" loading="lazy"/>{{ it.source_label }}</span>
          </div>
          <h3 class="sig-t">
            <a href="{{ (it.url or it.link)|safe_url }}" target="_blank" rel="noopener noreferrer">{{ it.display_title }}</a>
          </h3>
          {% if it.so_what %}<div class="sw">{{ it.so_what }}</div>{% endif %}
          {% if it.power_shift or it.watch_next %}
          <div class="sig-foot {% if it.power_shift and it.watch_next %}two{% endif %}">
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
      </article>
      {% endfor %}
    </div>
    {% else %}
    <div class="empty">
      <div class="big">Hoy no ha pasado nada que mueva la aguja.</div>
      <div class="sub">
        El filtro de relevancia descartó todo lo ingerido por irrelevante. Un día sin señal
        también es información: significa que la carrera frontier no se movió.
      </div>
    </div>
    {% endif %}
  </section>

  {% if threads or has_moves %}
  <section>
    <div class="head"><h2>Memoria del radar</h2><span class="n">continuidad</span></div>
    <div class="grid2">
      <div class="card">
        <span class="lbl">Narrativas en curso</span>
        {% if threads %}
          {% for t in threads %}
          <div class="thr">
            <span class="thr-d">DÍA {{ t.days }}</span>
            <div>
              <div class="thr-t">{{ t.label }}</div>
              {% if t.lead %}<div class="thr-l">{{ t.lead }}</div>{% endif %}
            </div>
          </div>
          {% endfor %}
        {% else %}
          <div class="none">Ninguna narrativa encadena 3 o más días.</div>
        {% endif %}
      </div>
      <div class="card">
        <span class="lbl">Movimiento de actores</span>
        {% if has_moves %}
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
        {% else %}
          <div class="none">Sin cambios de actores respecto a días previos.</div>
        {% endif %}
      </div>
    </div>
  </section>
  {% endif %}

  {% if risks or watch_list %}
  <section>
    <div class="head"><h2>Riesgos y vigilancia</h2><span class="n">próximos días</span></div>
    <div class="grid2">
      {% if risks %}
      <div class="card">
        <span class="lbl">Riesgos</span>
        {% for r in risks %}<div class="rk">{{ r }}</div>{% endfor %}
      </div>
      {% endif %}
      {% if watch_list %}
      <div class="card">
        <span class="lbl">A vigilar</span>
        {% for w in watch_list %}<div class="rk w">{{ w }}</div>{% endfor %}
      </div>
      {% endif %}
    </div>
  </section>
  {% endif %}

  {% if context %}
  <section>
    <div class="head">
      <h2>Contexto</h2>
      <span class="n">de fondo, no cambia nada hoy</span>
    </div>
    <div class="ctx">
      {% for it in context %}
      <div class="cx">
        <span class="cx-s">{{ it.score }}</span>
        <div class="cx-b">
          <div class="cx-t">
            <a href="{{ (it.url or it.link)|safe_url }}" target="_blank" rel="noopener noreferrer">{{ it.display_title }}</a>
          </div>
          {% if it.so_what %}<div class="cx-w">{{ it.so_what }}</div>{% endif %}
          <div class="cx-m">{{ it.theme_label }} · {{ it.source_label }}</div>
        </div>
      </div>
      {% endfor %}
    </div>
  </section>
  {% endif %}

  <footer>
    <span>{{ n_dropped }} items descartados por el filtro de relevancia</span>
    <span>{{ sources_alive }}/{{ sources_total }} fuentes activas{% if sources_dead %} · sin items: {{ sources_dead }}{% endif %}</span>
  </footer>

</div>
</body>
</html>
""")


def render_index(items, briefing=None, snapshot=None):
    briefing = briefing or {}
    snapshot = snapshot or {}

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
        enriched.append(it)

    enriched.sort(key=lambda x: x.get("score", 0), reverse=True)

    signals = [it for it in enriched if it.get("layer") == "signal"]
    context = [it for it in enriched if it.get("layer") == "context"]
    if not signals and not context:
        signals = enriched  # modo degradado: sin veredictos, todo a la capa principal

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
    )
