from jinja2 import Template
from datetime import datetime

TEMPLATE = Template("""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>AI Intel Briefing</title>
  <style>
    :root{
      --bg:#0b0f14;
      --panel:#0f1722;
      --border:#1b2635;
      --text:#d7e1f0;
      --muted:#8aa2c2;
      --neon:#7bdff2;
      --link:#a78bfa;
      --chip:#0b1220;
    }
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; background:var(--bg); color:var(--text); margin:0; }
    header { padding:22px 0; border-bottom:1px solid var(--border); background: linear-gradient(90deg,#0b0f14,#0f1722); }
    .wrap { padding:22px; max-width:1100px; margin:0 auto; }
    h1 { margin:0; font-size:20px; letter-spacing:0.6px; }
    .sub { color:var(--muted); margin-top:6px; font-size:13px; display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
    .pill { display:inline-flex; gap:8px; align-items:center; padding:4px 10px; border:1px solid var(--border); background:rgba(15,23,34,0.6); border-radius:999px; font-size:12px; color:var(--muted); }
    .grid { display:grid; grid-template-columns: 1fr; gap:12px; }
    .card { border:1px solid var(--border); background:var(--panel); border-radius:14px; padding:14px 14px 12px; }
    .top { display:flex; justify-content:space-between; align-items:flex-start; gap:12px; }
    .src { color:var(--neon); font-size:12px; }
    .score { font-size:12px; color:var(--muted); display:flex; gap:8px; align-items:center; }
    .bar { width:90px; height:8px; border-radius:999px; border:1px solid var(--border); background:#0a0f18; overflow:hidden; }
    .fill { height:100%; background:linear-gradient(90deg, #7bdff2, #a78bfa); width:0%; }
    a { color:var(--link); text-decoration:none; }
    a:hover { text-decoration:underline; }
    .title { margin-top:6px; font-size:15px; line-height:1.3; }
    .meta { color:var(--muted); font-size:12px; margin-top:8px; display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
    .chip { padding:3px 8px; border:1px solid var(--border); background:var(--chip); border-radius:999px; font-size:11px; color:var(--muted); }
    .summary { margin-top:10px; color:#b7c7df; font-size:13px; line-height:1.35; }
    .foot { margin-top:18px; color:var(--muted); font-size:12px; opacity:0.85; }
  </style>
</head>
<body>
<header>
  <div class="wrap">
    <h1>AI Intel Briefing</h1>
    <div class="sub">
      <span class="pill">Cyberpunk sobrio</span>
      <span class="pill">Generado: {{ generated_at }}</span>
      <span class="pill">Top señales (cap ~20)</span>
    </div>
  </div>
</header>

<div class="wrap">
  <div class="grid">
    {% for item in items %}
      <div class="card">
        <div class="top">
          <div class="src">{{ item.source }}</div>
          <div class="score">
            <span>Score {{ item.score }}</span>
            <div class="bar">
              <div class="fill" style="width: {{ item.score }}%;"></div>
            </div>
          </div>
        </div>

        <div class="title">
          <a href="{{ item.link }}" target="_blank" rel="noreferrer">{{ item.title }}</a>
        </div>

        <div class="meta">
          <span class="chip">{{ item.primary }}</span>
          {% for t in item.tags %}
            <span class="chip">{{ t }}</span>
          {% endfor %}
          {% for t in item.feed_tags %}
            <span class="chip">{{ t }}</span>
          {% endfor %}
          <span class="chip">{{ item.published or "sin fecha" }}</span>
        </div>

        {% if item.summary %}
          <div class="summary">
            {{ item.summary | striptags | truncate(320, True, "…") }}
          </div>
        {% endif %}
      </div>
    {% endfor %}
  </div>

  <div class="foot">
    Nota: esto aún es scoring heurístico (keywords + bonus por fuente). El siguiente salto será Gemini Flash para clasificar y resumir mejor sin tragar artículos enteros.
  </div>
</div>
</body>
</html>
""")

def render_index(items):
    return TEMPLATE.render(
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        items=items
    )
