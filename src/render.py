from __future__ import annotations

from collections import Counter
from datetime import datetime
import re
from urllib.parse import urlparse

from jinja2 import Environment, select_autoescape


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
    return raw[: max(0, limit - 1)].rstrip() + "..."


def clean_briefing_text(text: str) -> str:
    raw = re.sub(r"\s+", " ", (text or "").strip())
    replacements = {
        "Misc": "otros temas",
        "misc": "otros temas",
        "Watch": "Vigilar",
        "watch": "vigilar",
        "Lead": "Señal principal",
        "Follow-up": "Continuación",
        "Modelos": "modelos",
        "Infraestructura/HW": "infraestructura y hardware",
        "Economía/mercado": "economía y mercado",
    }
    for src, dst in replacements.items():
        raw = raw.replace(src, dst)
    raw = re.sub(r"\b(Paul|You)\b,?\s*", "", raw)
    return re.sub(r"\s+", " ", raw).strip()


def translate_headline_es(title: str) -> str:
    raw = re.sub(r"\s+", " ", (title or "").strip())
    if not raw:
        return ""

    patterns = [
        (r"Today, we share a breakthrough on the planar unit distance problem", "OpenAI anuncia un avance en el problema plano de la distancia unidad"),
        (r"You can now use your .*X Premium subscription", "Ya puedes usar tu suscripción de X Premium con Grok"),
        (r"In the EU, the online world serves people", "En la UE, el mundo online debe servir a las personas, no al revés"),
        (r"Simulate real-world places with Project Genie and Street View", "Simula lugares reales con Project Genie y Street View"),
        (r"Gemini for Science: AI experiments and tools for a new era of discovery", "Gemini para la ciencia: experimentos y herramientas de IA para una nueva era de descubrimientos"),
        (r"100 things we announced at I/O 2026", "Las 100 novedades anunciadas en Google I/O 2026"),
        (r"Introducing Gemini Omni", "Presentamos Gemini Omni"),
        (r"Making it easier to understand how content was created and edited", "Más fácil entender cómo se creó y editó un contenido"),
        (r"ASML High-NA EUV is Not Ready for High-Volume Production", "La tecnología High-NA EUV de ASML aún no está lista para la producción a gran escala"),
        (r"What Winemakers and Chip Designers Have in Common", "Qué tienen en común los bodegueros y los diseñadores de chips"),
        (r"Highlights from today’s Codex Thursday launches", "Lo más destacado de los lanzamientos de Codex Thursday"),
        (r"Highlights from today's Codex Thursday launches", "Lo más destacado de los lanzamientos de Codex Thursday"),
        (r"Last month we launched Project Glasswing", "Anthropic amplía Project Glasswing, su iniciativa colaborativa de ciberseguridad con IA"),
        (r"From 8 hours to 80 seconds", "De 8 horas a 80 segundos: NVIDIA acelera el despliegue de infraestructura DGX SuperPOD"),
        (r"In order to understand the universe, you must explore the universe", "Para entender el universo, hay que explorarlo"),
        (r"Finding the molecular switches behind new infectious diseases", "Identifican los interruptores moleculares detrás de nuevas enfermedades infecciosas"),
        (r"Gemini 3\.5: frontier intelligence with action", "Gemini 3.5: inteligencia de frontera con capacidad de acción"),
        (r"New ways to balance cost and reliability in the Gemini API", "Nuevas formas de equilibrar coste y fiabilidad en la API de Gemini"),
        (r"Update: GPT-5\.5 and GPT-5\.5 Pro are now available in the API", "Actualización: GPT-5.5 y GPT-5.5 Pro ya están disponibles en la API"),
        (r"New ways to create personalized images in the Gemini app", "Nuevas formas de crear imágenes personalizadas en la aplicación Gemini"),
        (r"NVIDIA GauGAN2", "NVIDIA GauGAN2 permite crear escenas a partir de frases simples"),
    ]
    for pattern, translated in patterns:
        if re.search(pattern, raw, flags=re.IGNORECASE):
            return translated

    simple_prefixes = {
        "Introducing ": "Presentamos ",
        "Update: ": "Actualización: ",
        "New ways to ": "Nuevas formas de ",
        "Everything new in ": "Todas las novedades de ",
    }
    for src, dst in simple_prefixes.items():
        if raw.startswith(src):
            return dst + raw[len(src):]
    return raw


def human_theme(theme: str) -> str:
    mapping = {
        "agents_automation": "Agentes y automatización",
        "compute_chips_dc": "Computación y chips",
        "frontier_capability": "Modelos frontera",
        "model_economics_pricing": "Economía de modelos",
        "geopolitics_power": "Geopolítica",
        "china_stack": "Stack chino",
        "other": "Otros",
        "misc": "Otros",
    }
    key = (theme or "other").strip()
    return mapping.get(key, mapping.get(key.lower(), key.replace("_", " ").title()))


def score_value(item: dict) -> int:
    for key in ("final_score", "score", "adjusted_score", "heuristic_score"):
        val = item.get(key)
        if isinstance(val, (int, float)):
            return max(0, min(100, int(round(val))))
        if isinstance(val, str):
            try:
                return max(0, min(100, int(round(float(val)))))
            except ValueError:
                continue
    return 0


def conviction(score: int) -> tuple[str, str]:
    if score >= 80:
        return "Extrema", "extreme"
    if score >= 65:
        return "Alta", "high"
    if score >= 45:
        return "Media", "medium"
    return "Baja", "low"


def item_reason(item: dict, limit: int = 180) -> str:
    txt = (item.get("why") or item.get("summary") or "").strip()
    return truncate_text(txt, limit) if txt else "No analysis available."


def item_entities(item: dict, limit: int = 6) -> list[str]:
    raw = item.get("entities") or []
    out: list[str] = []
    seen = set()
    blocked = {
        "image", "thread", "post", "tweet", "update", "quote", "apr", "may",
        "jun", "jul", "aug", "sep", "oct", "nov", "dec", "our", "the",
        "project", "research", "developers", "pro", "his", "her", "their",
        "introducing", "interview",
    }
    has_specific_gpt = any(isinstance(e, str) and re.search(r"\bGPT[- ]\d", e, re.IGNORECASE) for e in raw)
    for e in raw:
        if not isinstance(e, str):
            continue
        name = re.sub(r"\s+", " ", e.strip())
        if has_specific_gpt and name.upper() == "GPT":
            continue
        if not name or len(name) < 3 or len(name) > 28:
            continue
        if name.lower() in blocked or len(name.split()) > 3:
            continue
        k = name.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(name)
        if len(out) >= limit:
            break
    return out


def signal_level(top_items: list[dict]) -> tuple[str, str, float]:
    if not top_items:
        return "Low", "low", 0.0
    scores = [score_value(x) for x in top_items]
    avg = sum(scores) / len(scores)
    max_score = max(scores)
    if max_score >= 82 and avg >= 64:
        return "Extreme", "extreme", avg
    if max_score >= 68 and avg >= 50:
        return "High", "high", avg
    if max_score >= 45 or avg >= 38:
        return "Medium", "medium", avg
    return "Low", "low", avg


def source_domain(url: str) -> str:
    parsed = urlparse(url or "")
    host = parsed.netloc.replace("www.", "")
    return host or "source"


SOURCE_DOMAIN_HINTS = {
    "arxiv": "arxiv.org",
    "deepmind": "deepmind.google",
    "google ai": "blog.google",
    "nvidia": "nvidia.com",
    "semiwiki": "semiwiki.com",
    "openai": "openai.com",
    "anthropic": "anthropic.com",
    "x @googledeepmind": "deepmind.google",
    "x @deepseek": "deepseek.com",
    "x @xai": "x.ai",
    "x @karpathy": "x.com",
    "x @sama": "openai.com",
    "x ai policy": "commission.europa.eu",
}


def source_logo_domain(source: str, url: str = "") -> str:
    src = (source or "").strip().lower()
    for key, domain in SOURCE_DOMAIN_HINTS.items():
        if key in src:
            return domain
    domain = source_domain(url)
    if domain != "source":
        return domain
    return "x.com" if src.startswith("x ") else "github.com"


def source_logo_url(source: str, url: str = "") -> str:
    domain = source_logo_domain(source, url)
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=64"


def source_label(source: str) -> str:
    raw = (source or "Fuente").strip()
    if raw.startswith("X @"):
        return raw.replace("X @", "@", 1)
    return raw.replace(" (AI)", "")


def source_initial(source: str) -> str:
    label = source_label(source).lstrip("@").strip()
    return (label[:1] or "S").upper()


def one_line_takeaway(item: dict) -> str:
    title = (item.get("display_title") or item.get("title_es") or item.get("title") or "").strip()
    reason = (item.get("reason") or item_reason(item, limit=120)).strip()
    if reason and reason.lower() not in title.lower():
        return truncate_text(reason, 118)
    return truncate_text(title, 118)


ENV = Environment(autoescape=select_autoescape(["html", "xml"]))
ENV.filters["safe_url"] = _safe_url

TEMPLATE = ENV.from_string("""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Radar Estratégico de IA</title>
  <style>
    :root{
      --bg:#090a0c; --surface:#11151b; --surface2:#161b22; --line:#27313d;
      --text:#edf2f7; --muted:#9aa8b7; --cyan:#67e8f9; --green:#74d99f;
      --amber:#f4bd50; --red:#fb7185; --violet:#c4b5fd; --blue:#93c5fd;
      --shadow:0 18px 55px rgba(0,0,0,.34);
    }
    *{box-sizing:border-box}
    html{scroll-behavior:smooth}
    body{margin:0;background:#090a0c;color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif}
    body:before{content:"";position:fixed;inset:0;pointer-events:none;background:linear-gradient(145deg,rgba(103,232,249,.10),transparent 32%),linear-gradient(30deg,rgba(116,217,159,.08),transparent 40%);z-index:-1}
    a{color:#cfe6ff;text-decoration:none} a:hover{text-decoration:underline}
    .wrap{max-width:1180px;margin:0 auto;padding:18px}
    .topbar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px}
    .brand{font-weight:800;letter-spacing:.2px}.nav{display:flex;gap:8px;flex-wrap:wrap}
    .nav a{border:1px solid var(--line);border-radius:8px;padding:8px 10px;color:var(--muted);background:rgba(17,21,27,.72);font-size:13px}.nav a.active{color:var(--text);border-color:rgba(103,232,249,.55)}
    .hero{position:relative;overflow:hidden;border:1px solid var(--line);background:linear-gradient(135deg,rgba(24,35,42,.98),rgba(13,16,21,.96) 62%,rgba(17,24,39,.98));border-radius:10px;padding:24px;box-shadow:var(--shadow)}
    .hero:after{content:"";position:absolute;right:-160px;top:-160px;width:360px;height:360px;border-radius:999px;background:radial-gradient(circle,rgba(103,232,249,.16),transparent 62%);pointer-events:none}
    .eyebrow{font-size:11px;color:var(--cyan);font-weight:800;text-transform:uppercase;letter-spacing:.8px}
    h1{margin:6px 0 0;font-size:clamp(34px,6vw,68px);line-height:1;font-weight:850}
    .subtitle{margin-top:10px;color:var(--muted);font-size:15px;max-width:820px}
    .thesis{margin-top:16px;font-size:clamp(21px,3.4vw,40px);line-height:1.12;font-weight:820;max-width:980px}
    .quick-strip{display:grid;grid-template-columns:1fr;gap:8px;margin-top:18px}
    @media (min-width:860px){.quick-strip{grid-template-columns:repeat(3,minmax(0,1fr))}}
    .quick{border:1px solid rgba(103,232,249,.26);background:rgba(13,17,23,.72);border-radius:10px;padding:12px;min-height:98px}
    .quick .label{font-size:11px;color:var(--cyan);text-transform:uppercase;font-weight:850;letter-spacing:.6px}.quick .txt{margin-top:7px;font-size:15px;line-height:1.28;font-weight:720}
    .source-strip{display:flex;gap:9px;flex-wrap:wrap;margin-top:16px}
    .source-chip{display:inline-flex;align-items:center;gap:8px;border:1px solid var(--line);border-radius:999px;background:#0d1117;padding:6px 9px;color:#dbe7f3;font-size:12px;font-weight:750}
    .logo{width:26px;height:26px;border-radius:8px;background:#111820;border:1px solid var(--line);object-fit:contain;padding:3px;flex:0 0 auto}
    .logo.big{width:46px;height:46px;border-radius:12px;padding:5px}
    .metrics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:14px}
    @media (min-width:820px){.metrics{grid-template-columns:repeat(5,minmax(0,1fr))}}
    .metric{border:1px solid var(--line);background:#0d1117;border-radius:8px;padding:10px;min-height:78px}
    .metric .k{font-size:11px;color:var(--muted);text-transform:uppercase;font-weight:750}.metric .v{margin-top:7px;font-size:22px;font-weight:820;line-height:1.05}
    .signal{display:inline-flex;border:1px solid transparent;border-radius:999px;padding:5px 9px;font-size:12px;font-weight:850}
    .low{color:var(--blue);background:rgba(147,197,253,.10);border-color:rgba(147,197,253,.35)}
    .medium{color:var(--amber);background:rgba(244,189,80,.12);border-color:rgba(244,189,80,.38)}
    .high{color:var(--green);background:rgba(116,217,159,.12);border-color:rgba(116,217,159,.38)}
    .extreme{color:var(--red);background:rgba(251,113,133,.13);border-color:rgba(251,113,133,.42)}
    .grid{display:grid;grid-template-columns:1fr;gap:12px;margin-top:12px;align-items:start}@media (min-width:980px){.grid.two{grid-template-columns:1.18fr .82fr}.grid.three{grid-template-columns:1.25fr .9fr .85fr}}
    .panel,.lead,.mini,.feed-card{border:1px solid var(--line);border-radius:8px;background:rgba(17,21,27,.90)}
    .panel{padding:14px}.panel h2,.feed h2{margin:0 0 10px;font-size:17px}.lead{padding:18px;background:linear-gradient(180deg,#18202a,#111820)}
    .lead-head{display:flex;gap:12px;align-items:flex-start}.lead h2{font-size:clamp(24px,3.2vw,38px);line-height:1.09;margin:8px 0 0}
    .meta{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}.badge{display:inline-flex;align-items:center;border:1px solid var(--line);border-radius:999px;background:#0d1117;color:#dbe7f3;font-size:12px;padding:5px 9px}.badge.score{color:var(--red);border-color:rgba(251,113,133,.42)}.badge.theme{color:var(--cyan);border-color:rgba(103,232,249,.38)}.badge.repeat{color:var(--amber);border-color:rgba(244,189,80,.38)}
    .why{margin-top:13px;color:#d8e4ef;line-height:1.42;border-left:3px solid var(--cyan);padding-left:10px}
    .entities{display:flex;gap:7px;flex-wrap:wrap;margin-top:12px}.entity{border:1px solid var(--line);background:#0b0f14;border-radius:999px;padding:6px 9px;font-size:12px;color:#dfe8f2}
    .actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:15px}.btn{border:1px solid var(--line);background:#0d1117;color:var(--text);border-radius:8px;padding:9px 11px;font-weight:750;cursor:pointer;font-size:13px}.btn.primary{border-color:rgba(103,232,249,.5);background:rgba(103,232,249,.10)}.btn.fav.active{border-color:rgba(244,189,80,.6);color:var(--amber)}
    .mini{padding:13px}.mini h3{font-size:17px;line-height:1.18;margin:8px 0 0}.mini .why{font-size:13px}
    .mini-head{display:flex;gap:10px;align-items:flex-start}
    .brief-list{display:grid;gap:8px}.brief-row{display:grid;grid-template-columns:26px 1fr;gap:8px;align-items:start;font-size:14px;line-height:1.35}.num{width:24px;height:24px;border-radius:999px;border:1px solid rgba(103,232,249,.5);display:flex;align-items:center;justify-content:center;color:var(--cyan);font-size:12px;font-weight:800}
    .risk{color:#ffe0a3}.watch-text{color:#dcd4ff}.bar-row{margin:10px 0}.bar-top{display:flex;justify-content:space-between;gap:10px;font-size:13px}.bar{height:10px;border:1px solid var(--line);border-radius:999px;overflow:hidden;background:#0b0f14;margin-top:6px}.fill{height:100%;background:linear-gradient(90deg,var(--green),var(--cyan),var(--amber))}
    .controls{position:sticky;top:0;z-index:5;margin-top:14px;border:1px solid var(--line);border-radius:8px;background:rgba(9,10,12,.92);backdrop-filter:blur(10px);padding:10px;display:grid;gap:8px}
    @media (min-width:900px){.controls{grid-template-columns:1fr 180px 180px 170px}}
    input,select{width:100%;border:1px solid var(--line);border-radius:8px;background:#0d1117;color:var(--text);padding:10px;font:inherit}
    .feed{margin-top:14px}.feed-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px}.count{color:var(--muted);font-size:13px}
    .feed-grid{display:grid;grid-template-columns:1fr;gap:10px}@media (min-width:820px){.feed-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}.feed-card{padding:13px;min-height:210px;display:flex;flex-direction:column}.feed-card.hidden{display:none}.feed-card.favorited{border-color:rgba(244,189,80,.58)}
    .feed-top{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}.source-line{display:flex;align-items:center;gap:9px}.feed-title{font-size:18px;font-weight:820;line-height:1.18;margin-top:10px}.feed-reason{margin-top:9px;color:#cbd6e2;font-size:13px;line-height:1.36}.tiny{font-size:12px;color:var(--muted)}
    .takeaway{margin-top:10px;border-left:3px solid var(--green);padding-left:9px;font-size:14px;line-height:1.35;color:#eef6ff;font-weight:650}
    .empty{display:none;color:var(--muted);border:1px dashed var(--line);border-radius:8px;padding:18px;text-align:center}.empty.show{display:block}
    @media (max-width:700px){.wrap{padding:12px}.hero,.lead,.panel{padding:13px}.feed-top{display:block}.metric .v{font-size:19px}.lead-head{display:block}.logo.big{margin-bottom:10px}}
  </style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div class="brand">Radar Estratégico de IA</div>
    <nav class="nav">
      <a class="active" href="./index.html">Diario</a>
      <a href="./weekly.html">Semanal</a>
      <a href="#feed">Noticias</a>
    </nav>
  </div>

  <section class="hero">
    <div class="eyebrow">Briefing de inteligencia</div>
    <h1>Señal {{ signal_label|lower }}</h1>
    <div class="subtitle">Laboratorios frontera, agentes, computación, stack chino, economía de modelos y cambios de poder.</div>
    <div class="thesis">{{ todays_thesis }}</div>
    <div class="quick-strip">
      {% for item in briefing_cards %}
      <div class="quick">
        <div class="label">{{ item.label }}</div>
        <div class="txt">{{ item.text }}</div>
      </div>
      {% endfor %}
    </div>
    <div class="source-strip">
      {% for src in top_sources %}
      <span class="source-chip"><img class="logo" src="{{ src.logo }}" alt=""/>{{ src.label }}</span>
      {% endfor %}
    </div>
    <div class="metrics">
      <div class="metric"><div class="k">Fecha</div><div class="v">{{ generated_at }}</div></div>
      <div class="metric"><div class="k">Convicción</div><div class="v"><span class="signal {{ signal_class }}">{{ signal_label }}</span></div></div>
      <div class="metric"><div class="k">Score líder</div><div class="v">{{ lead.score }}</div></div>
      <div class="metric"><div class="k">Media top 3</div><div class="v">{{ avg_top }}</div></div>
      <div class="metric"><div class="k">Fuertes</div><div class="v">{{ strong_signals_count }}</div></div>
    </div>
  </section>

  <section class="grid two">
    <article class="lead" data-id="{{ lead.id }}">
      <div class="lead-head">
        <img class="logo big" src="{{ lead.logo }}" alt=""/>
        <div>
          <div class="eyebrow">Señal principal</div>
          <h2>{{ lead.display_title }}</h2>
        </div>
      </div>
      <div class="meta">
        <span class="badge">{{ lead.source_label }}</span>
        <span class="badge theme">{{ lead.theme_label }}</span>
        <span class="badge score">Score {{ lead.score }}</span>
        <span class="badge {{ lead.conviction_class }}">{{ lead.conviction_label }}</span>
        {% if lead.is_repeat %}<span class="badge repeat">Repetida</span>{% endif %}
      </div>
      <div class="takeaway">{{ lead.takeaway }}</div>
      <div class="why">{{ lead.reason }}</div>
      <div class="entities">{% for e in lead.entities %}<span class="entity">{{ e }}</span>{% endfor %}</div>
      <div class="actions">
        <a class="btn primary" href="{{ (lead.url or lead.link)|safe_url }}" target="_blank" rel="noopener noreferrer">Leer fuente</a>
        <button class="btn fav" data-fav="{{ lead.id }}" type="button">Guardar</button>
        <button class="btn" data-copy="{{ lead.display_title }} - {{ (lead.url or lead.link)|safe_url }}" type="button">Copiar</button>
      </div>
    </article>
    <aside class="grid">
      {% for item in secondary_signals %}
      <article class="mini" data-id="{{ item.id }}">
        <div class="mini-head">
          <img class="logo" src="{{ item.logo }}" alt=""/>
          <div class="tiny">{{ item.source_label }}</div>
        </div>
        <div class="meta">
          <span class="badge theme">{{ item.theme_label }}</span>
          <span class="badge score">{{ item.score }}</span>
        </div>
        <h3><a href="{{ (item.url or item.link)|safe_url }}" target="_blank" rel="noopener noreferrer">{{ item.display_title }}</a></h3>
        <div class="why">{{ item.reason }}</div>
      </article>
      {% endfor %}
    </aside>
  </section>

  <section class="grid three">
    <article class="panel">
      <h2>Captura rápida</h2>
      <div class="brief-list">
        {% for s in brief_signals %}
        <div class="brief-row"><span class="num">{{ loop.index }}</span><span>{{ s }}</span></div>
        {% endfor %}
      </div>
    </article>
    <article class="panel">
      <h2>Riesgos</h2>
      {% for r in brief_risks %}<p class="risk">{{ r }}</p>{% endfor %}
      <h2>Qué vigilar</h2>
      {% for w in brief_watch %}<p class="watch-text">{{ w }}</p>{% endfor %}
    </article>
    <article class="panel">
      <h2>Actores en foco</h2>
      <div class="entities">{% for ent in momentum_entities %}<span class="entity">{{ ent }}</span>{% endfor %}</div>
      <p class="tiny">Tema dominante: {{ dominant_theme_label }}. Repetidas: {{ repeat_count }} noticias.</p>
    </article>
  </section>

  <section class="panel">
    <h2>Radar temático</h2>
    {% for t in theme_rows %}
    <div class="bar-row">
      <div class="bar-top"><span>{{ t.label }}</span><strong>{{ t.count }} / {{ t.pct }}%</strong></div>
      <div class="bar"><div class="fill" style="width: {{ t.pct }}%;"></div></div>
    </div>
    {% endfor %}
  </section>

  <section class="controls" aria-label="Signal controls">
    <input id="searchBox" type="search" placeholder="Buscar titular, fuente o entidad"/>
    <select id="themeFilter">
      <option value="all">Todos los temas</option>
      {% for t in theme_options %}<option value="{{ t }}">{{ t }}</option>{% endfor %}
    </select>
    <select id="viewFilter">
      <option value="all">Todas las noticias</option>
      <option value="new">Solo nuevas</option>
      <option value="repeat">Solo repetidas</option>
      <option value="fav">Guardadas</option>
    </select>
    <select id="sortMode">
      <option value="score">Ordenar por score</option>
      <option value="theme">Ordenar por tema</option>
      <option value="source">Ordenar por fuente</option>
    </select>
  </section>

  <section class="feed" id="feed">
    <div class="feed-head"><h2>Todas las noticias</h2><span class="count" id="visibleCount">{{ items|length }} visibles</span></div>
    <div class="feed-grid" id="itemsGrid">
      {% for item in items %}
      <article class="feed-card"
        data-id="{{ item.id }}"
        data-score="{{ item.score }}"
        data-theme="{{ item.theme_label }}"
        data-source="{{ item.source }}"
        data-repeat="{{ '1' if item.is_repeat else '0' }}"
        data-search="{{ item.search_blob }}">
        <div class="feed-top">
          <div>
            <div class="source-line"><img class="logo" src="{{ item.logo }}" alt=""/><div><strong>{{ item.source_label }}</strong><div class="tiny">{{ item.domain }}</div></div></div>
            <div class="feed-title"><a href="{{ (item.url or item.link)|safe_url }}" target="_blank" rel="noopener noreferrer">{{ item.display_title }}</a></div>
          </div>
          <div class="meta">
            <span class="badge score">{{ item.score }}</span>
            <span class="badge theme">{{ item.theme_label }}</span>
            {% if item.is_repeat %}<span class="badge repeat">Repetida</span>{% endif %}
          </div>
        </div>
        <div class="takeaway">{{ item.takeaway }}</div>
        <div class="feed-reason">{{ item.reason }}</div>
        <div class="entities">{% for e in item.entities %}<span class="entity">{{ e }}</span>{% endfor %}</div>
        <div class="actions">
          <button class="btn fav" data-fav="{{ item.id }}" type="button">Guardar</button>
          <button class="btn" data-copy="{{ item.display_title }} - {{ (item.url or item.link)|safe_url }}" type="button">Copiar</button>
        </div>
      </article>
      {% endfor %}
    </div>
    <div class="empty" id="emptyState">No hay noticias para esta vista.</div>
  </section>
</div>
<script>
const favKey = 'ai-radar-favorites';
const saved = new Set(JSON.parse(localStorage.getItem(favKey) || '[]'));
const cards = Array.from(document.querySelectorAll('.feed-card'));
function persist(){ localStorage.setItem(favKey, JSON.stringify(Array.from(saved))); }
function paintFavs(){
  document.querySelectorAll('[data-fav]').forEach((btn)=>{
    const id = btn.dataset.fav;
    const active = saved.has(id);
    btn.classList.toggle('active', active);
    btn.textContent = active ? 'Guardada' : 'Guardar';
  });
  cards.forEach((card)=>card.classList.toggle('favorited', saved.has(card.dataset.id)));
}
function applyView(){
  const q = document.getElementById('searchBox').value.trim().toLowerCase();
  const theme = document.getElementById('themeFilter').value;
  const view = document.getElementById('viewFilter').value;
  const mode = document.getElementById('sortMode').value;
  const grid = document.getElementById('itemsGrid');
  cards.sort((a,b)=>{
    if(mode === 'theme') return a.dataset.theme.localeCompare(b.dataset.theme) || Number(b.dataset.score)-Number(a.dataset.score);
    if(mode === 'source') return a.dataset.source.localeCompare(b.dataset.source) || Number(b.dataset.score)-Number(a.dataset.score);
    return Number(b.dataset.score)-Number(a.dataset.score);
  }).forEach((card)=>grid.appendChild(card));
  let visible = 0;
  cards.forEach((card)=>{
    const repeat = card.dataset.repeat === '1';
    const fav = saved.has(card.dataset.id);
    const matchesSearch = !q || card.dataset.search.includes(q);
    const matchesTheme = theme === 'all' || card.dataset.theme === theme;
    const matchesView = view === 'all' || (view === 'new' && !repeat) || (view === 'repeat' && repeat) || (view === 'fav' && fav);
    const show = matchesSearch && matchesTheme && matchesView;
    card.classList.toggle('hidden', !show);
    if(show) visible += 1;
  });
  document.getElementById('visibleCount').textContent = visible + ' visibles';
  document.getElementById('emptyState').classList.toggle('show', visible === 0);
}
document.querySelectorAll('input,select').forEach((el)=>el.addEventListener('input', applyView));
document.addEventListener('click', async (event)=>{
  const fav = event.target.closest('[data-fav]');
  if(fav){
    const id = fav.dataset.fav;
    saved.has(id) ? saved.delete(id) : saved.add(id);
    persist(); paintFavs(); applyView();
  }
  const copy = event.target.closest('[data-copy]');
  if(copy && navigator.clipboard){ await navigator.clipboard.writeText(copy.dataset.copy); copy.textContent = 'Copiado'; setTimeout(()=>copy.textContent='Copiar', 900); }
});
paintFavs();
applyView();
</script>
</body>
</html>
""")


def render_index(items, briefing=None):
    enriched = []
    for idx, raw in enumerate(items or [], start=1):
        it = dict(raw)
        score = score_value(it)
        label, css = conviction(score)
        theme = (it.get("strategic_theme") or it.get("primary") or "other").strip() or "other"
        theme_label = human_theme(theme)
        url = it.get("url") or it.get("link") or ""
        entities = item_entities(it, limit=6)
        src_label = source_label(it.get("source", ""))
        title_original = (it.get("title") or "").strip()
        llm_title_es = (it.get("title_es") or "").strip()
        display_title = llm_title_es or translate_headline_es(title_original)
        reason_text = clean_briefing_text(item_reason(it))
        if not llm_title_es:
            reason_text = f"Fuente: {src_label}. Señal clasificada como {theme_label.lower()}."
        it.update(
            {
                "id": f"sig-{idx}",
                "score": score,
                "theme": theme,
                "theme_label": theme_label,
                "reason": reason_text,
                "entities": entities,
                "noise_penalty": int(it.get("noise_penalty", 0) or 0),
                "conviction_label": label,
                "conviction_class": css,
                "domain": source_domain(url),
                "logo": source_logo_url(it.get("source", ""), url),
                "source_label": src_label,
                "source_initial": source_initial(it.get("source", "")),
                "title_original": title_original,
                "display_title": display_title,
                "title_es": display_title,
                "has_llm_title_es": bool(llm_title_es),
                "search_blob": " ".join(
                    [
                        display_title,
                        title_original,
                        str(it.get("source", "")),
                        src_label,
                        theme_label,
                        " ".join(entities),
                        str(it.get("reason", "")),
                    ]
                ).lower(),
            }
        )
        it["takeaway"] = one_line_takeaway(it)
        enriched.append(it)

    enriched.sort(key=lambda x: x.get("score", 0), reverse=True)
    lead = enriched[0] if enriched else {
        "id": "sig-empty",
        "title": "No strong lead signal detected today.",
        "display_title": "No se ha detectado una señal principal clara.",
        "title_original": "",
        "source": "Radar",
        "theme_label": human_theme("other"),
        "score": 0,
        "reason": "No hay datos suficientes para producir una señal dominante.",
        "entities": [],
        "noise_penalty": 0,
        "url": "#",
        "link": "#",
        "conviction_label": "Baja",
        "conviction_class": "low",
        "is_repeat": False,
        "logo": source_logo_url("Radar", ""),
        "source_label": "Radar",
        "takeaway": "No hay suficiente evidencia fresca para una señal clara.",
    }

    top3 = enriched[:3]
    signal_label, signal_class, avg_top = signal_level(top3)
    strong_signals_count = sum(1 for x in enriched if x.get("score", 0) >= 50)
    noise_suppressed_count = sum(1 for x in enriched if x.get("noise_penalty", 0) >= 8)
    repeat_count = sum(1 for x in enriched if x.get("is_repeat"))

    theme_counter = Counter(x.get("theme", "other") for x in enriched if x.get("theme"))
    dominant_theme = theme_counter.most_common(1)[0][0] if theme_counter else "other"
    dominant_theme_label = human_theme(dominant_theme)
    total = max(1, len(enriched))
    theme_rows = [
        {"label": human_theme(t), "count": c, "pct": round((c / total) * 100, 1)}
        for t, c in theme_counter.most_common(6)
    ] or [{"label": "Otros", "count": 0, "pct": 0}]
    theme_options = sorted({x["label"] for x in theme_rows})

    briefing_obj = briefing or {}
    brief_signals = (briefing_obj.get("signals") or [])[:5]
    brief_risks = (briefing_obj.get("risks") or [])[:3]
    brief_watch = (briefing_obj.get("watch") or [])[:3]
    has_llm_translations = any(x.get("has_llm_title_es") for x in enriched)

    if not has_llm_translations:
        brief_signals = [
            f"Señal principal: {lead.get('display_title', '')} (score {lead.get('score', 0)}).",
        ]
        for item in enriched[1:5]:
            brief_signals.append(f"También importa: {item.get('display_title', '')} (score {item.get('score', 0)}).")
        brief_risks = ["Día con señales dispersas: conviene priorizar noticias con producto, regulación o infraestructura ya tangible."]
        brief_watch = [
            f"Vigilar si {momentum_entities[0] if 'momentum_entities' in locals() and momentum_entities else 'los actores principales'} mantiene tracción mañana.",
            "Buscar confirmación en fuentes primarias antes de elevar la convicción.",
        ]

    if has_llm_translations and briefing_obj.get("signals"):
        todays_thesis = clean_briefing_text(briefing_obj["signals"][0])
    else:
        todays_thesis = f"{dominant_theme_label}: {truncate_text(lead.get('display_title', ''), 120)}"
    brief_signals = [clean_briefing_text(x) for x in brief_signals]
    brief_risks = [clean_briefing_text(x) for x in brief_risks]
    brief_watch = [clean_briefing_text(x) for x in brief_watch]
    if not brief_signals:
        brief_signals = [todays_thesis, "Comprobar mañana si el tema principal se mantiene."]
    if not brief_risks:
        brief_risks = ["Pocas señales duras: el día puede parecer más relevante de lo que realmente es."]
    if not brief_watch:
        brief_watch = ["Vigilar evidencias duras: precios, computación, regulación o modelos ya disponibles."]

    briefing_cards = [
        {"label": "Clave", "text": truncate_text(brief_signals[0], 130)},
        {"label": "Riesgo", "text": truncate_text(brief_risks[0], 130)},
        {"label": "Vigilar", "text": truncate_text(brief_watch[0], 130)},
    ]

    entity_counter = Counter()
    for it in enriched[:8]:
        for e in it.get("entities", []):
            entity_counter[e] += 1
    momentum_entities = [e for e, _ in entity_counter.most_common(12)]
    for fallback in ["OpenAI", "Anthropic", "DeepMind", "DeepSeek", "Meta", "xAI", "NVIDIA", "TSMC"]:
        if fallback not in momentum_entities:
            momentum_entities.append(fallback)
        if len(momentum_entities) >= 12:
            break

    source_counter = Counter(x.get("source", "") for x in enriched)
    top_sources = []
    for src, _ in source_counter.most_common(6):
        sample = next((x for x in enriched if x.get("source") == src), {})
        top_sources.append(
            {
                "label": source_label(src),
                "logo": source_logo_url(src, sample.get("url") or sample.get("link") or ""),
            }
        )

    return TEMPLATE.render(
        generated_at=datetime.now().strftime("%Y-%m-%d"),
        items=enriched,
        lead=lead,
        secondary_signals=enriched[1:3],
        signal_label=signal_label,
        signal_class=signal_class,
        strong_signals_count=strong_signals_count,
        noise_suppressed_count=noise_suppressed_count,
        repeat_count=repeat_count,
        dominant_theme_label=dominant_theme_label,
        theme_rows=theme_rows,
        theme_options=theme_options,
        momentum_entities=momentum_entities,
        top_sources=top_sources,
        briefing_cards=briefing_cards,
        todays_thesis=todays_thesis,
        avg_top=round(avg_top, 1),
        briefing=briefing_obj,
        brief_signals=brief_signals,
        brief_risks=brief_risks,
        brief_watch=brief_watch,
    )
