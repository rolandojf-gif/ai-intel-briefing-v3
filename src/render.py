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
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; background:#0b0f14; color:#d7e1f0; margin:0; }
    header { padding:24px; border-bottom:1px solid #1b2635; background: linear-gradient(90deg,#0b0f14,#0f1722); }
    h1 { margin:0; font-size:20px; letter-spacing:0.5px; }
    .sub { color:#8aa2c2; margin-top:6px; font-size:13px; }
    .wrap { padding:24px; max-width:1100px; margin:0 auto; }
    .card { border:1px solid #1b2635; background:#0f1722; border-radius:14px; padding:16px; margin-bottom:14px; }
    .src { color:#7bdff2; font-size:12px; }
    a { color:#a78bfa; text-decoration:none; }
    a:hover { text-decoration:underline; }
    .meta { color:#8aa2c2; font-size:12px; margin-top:6px; }
  </style>
</head>
<body>
<header>
  <div class="wrap">
    <h1>AI Intel Briefing</h1>
    <div class="sub">Cyberpunk sobrio · {{ generated_at }}</div>
  </div>
</header>
<div class="wrap">
  {% for item in items %}
    <div class="card">
      <div class="src">{{ item.source }}</div>
      <div><a href="{{ item.link }}" target="_blank" rel="noreferrer">{{ item.title }}</a></div>
      <div class="meta">{{ item.published or "sin fecha" }}</div>
    </div>
  {% endfor %}
</div>
</body>
</html>
""")

def render_index(items):
    return TEMPLATE.render(generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"), items=items)
