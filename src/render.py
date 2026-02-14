from datetime import datetime
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


ENV = Environment(autoescape=select_autoescape(["html", "xml"]))
ENV.filters["safe_url"] = _safe_url

TEMPLATE = ENV.from_string("""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>AI Intel Briefing</title>
  <style>
    :root{
      --bg:#0b0f14; --panel:#0f1722; --border:#1b2635; --text:#d7e1f0;
      --muted:#8aa2c2; --neon:#7bdff2; --link:#a78bfa; --chip:#0b1220;
    }
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; background:var(--bg); color:var(--text); margin:0; }
    header { padding:22px 0; border-bottom:1px solid var(--border); background: linear-gradient(90deg,#0b0f14,#0f1722); }
    .wrap { padding:22px; max-width:1100px; margin:0 auto; }
    h1 { margin:0; font-size:20px; letter-spacing:0.6px; }
    .sub { color:var(--muted); margin-top:8px; font-size:13px; display:flex; gap:10px; flex-wrap:wrap; }
    .pill { padding:4px 10px; border:1px solid var(--border); background:rgba(15,23,34,0.6); border-radius:999px; font-size:12px; color:var(--muted); }

    .panel { border:1px solid var(--border); background:var(--panel); border-radius:16px; padding:14px; margin:18px 0 16px; }
    .panel h2 { margin:0 0 10px; font-size:14px; letter-spacing:0.4px; color:var(--neon); }
    .cols { display:grid; grid-template-columns: 1fr; gap:10px; }
    @media (min-width: 860px){ .cols { grid-template-columns: 2fr 1fr; } }
    .box { border:1px solid var(--border); background:rgba(11,18,32,0.55); border-radius:14px; padding:12px; }
    .box h3 { margin:0 0 8px; font-size:12px; color:var(--muted); letter-spacing:0.3px; }
    ul { margin:0; padding-left:18px; color:#cfe0ff; }
    li { margin:6px 0; font-size:13px; line-height:1.25; }

    .grid { display:grid; grid-template-columns: 1fr; gap:12px; }
    .card { border:1px solid var(--border); background:var(--panel); border-radius:14px; padding:14px; }
    .top { display:flex; justify-content:space-between; gap:12px; }
    .src { color:var(--neon); font-size:12px; }
    .score { font-size:12px; color:var(--muted); display:flex; gap:8px; align-items:center; }
    .bar { width:90px; height:8px; border-radius:999px; border:1px solid var(--border); background:#0a0f18; overflow:hidden; }
    .fill { height:100%; background:linear-gradient(90deg, #7bdff2, #a78bfa); width:0%; }
    a { color:var(--link); text-decoration:none; }
    a:hover { text-decoration:underline; }
    .title { margin-top:6px; font-size:15px; line-height:1.3; }
    .meta { color:var(--muted); font-size:12px; margin-top:8px; display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
    .chip { padding:3px 8px; border:1px solid var(--border); background:var(--chip); border-radius:999px; font-size:11px; color:var(--muted); }
    .why { margin-top:10px; color:#dbe8ff; font-size:13px; line-height:1.35; }
  </style>
</head>
<body>
<header>
  <div class="wrap">
    <h1>AI Intel Briefing</h1>
    <div class="sub">
      <span class="pill">Generado: {{ generated_at }}</span>
      <span class="pill">Items: {{ items|length }}</span>
    </div>
  </div>
</header>

<div class="wrap">

  {% if briefing and (briefing.signals or briefing.risks or briefing.watch or briefing.entities_top) %}
  <div class="panel">
    <h2>Briefing</h2>
    <div class="cols">
      <div class="box">
        <h3>Señales del día</h3>
        <ul>
          {% for s in briefing.signals %}
            <li>{{ s }}</li>
          {% endfor %}
        </ul>
      </div>

      <div class="box">
        <h3>Riesgos / cuellos de botella</h3>
        <ul>
          {% for r in briefing.risks %}
            <li>{{ r }}</li>
          {% endfor %}
        </ul>

        <h3 style="margin-top:12px;">Entidades dominantes</h3>
        <ul>
          {% for e in briefing.entities_top %}
            <li>{{ e }}</li>
          {% endfor %}
        </ul>

        <h3 style="margin-top:12px;">Watch (mañana)</h3>
        <ul>
          {% for w in briefing.watch %}
            <li>{{ w }}</li>
          {% endfor %}
        </ul>
      </div>
    </div>
  </div>
  {% endif %}

  <div class="grid">
    {% for item in items %}
      <div class="card">
        <div class="top">
          <div class="src">{{ item.source }}</div>
          <div class="score">
            <span>Score {{ item.score }}</span>
            <div class="bar"><div class="fill" style="width: {{ item.score }}%;"></div></div>
          </div>
        </div>

        <div class="title">
          <a href="{{ (item.url or item.link)|safe_url }}" target="_blank" rel="noopener noreferrer">{{ item.title }}</a>
        </div>

        <div class="meta">
          {% if item.primary %}<span class="chip">{{ item.primary }}</span>{% endif %}
          {% for t in item.tags %}<span class="chip">{{ t }}</span>{% endfor %}
          {% for e in item.entities %}<span class="chip">{{ e }}</span>{% endfor %}
          <span class="chip">{{ item.published or "sin fecha" }}</span>
        </div>

        {% if item.why %}
          <div class="why">{{ item.why }}</div>
        {% endif %}
      </div>
    {% endfor %}
  </div>

</div>
</body>
</html>
""")

def render_index(items, briefing=None):
    return TEMPLATE.render(
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        items=items,
        briefing=briefing or {}
    )
