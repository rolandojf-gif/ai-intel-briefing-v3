from datetime import datetime
from urllib.parse import urlparse
from collections import Counter

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
  <title>AI Strategic Radar</title>
  <style>
    :root {
      --bg:#070b12;
      --bg-soft:#0a1019;
      --panel:#0e1726;
      --panel-strong:#111d30;
      --border:#1f2d44;
      --text:#dbe7ff;
      --muted:#8aa2c2;
      --link:#a78bfa;
      --accent:#7bdff2;
      --good:#34d399;
      --warn:#f59e0b;
      --hot:#fb7185;
    }
    * { box-sizing:border-box; }
    body { margin:0; background:linear-gradient(180deg,var(--bg),var(--bg-soft)); color:var(--text); font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }
    a { color:var(--link); text-decoration:none; }
    a:hover { text-decoration:underline; }
    .wrap { max-width:1150px; margin:0 auto; padding:20px; }
    .hero {
      border:1px solid var(--border);
      background:radial-gradient(circle at top right, #132846 0%, #0d1727 55%, #0a1220 100%);
      border-radius:18px;
      padding:22px;
      margin-top:8px;
    }
    .eyebrow { color:var(--accent); font-size:11px; letter-spacing:.8px; text-transform:uppercase; font-weight:700; }
    h1 { margin:7px 0 0 0; font-size:31px; letter-spacing:.2px; }
    .subtitle { margin-top:8px; color:var(--muted); font-size:13px; }
    .hero-meta { margin-top:12px; display:flex; flex-wrap:wrap; gap:8px; }
    .pill { border:1px solid var(--border); border-radius:999px; padding:4px 10px; color:var(--muted); font-size:12px; background:rgba(9,14,24,.55); }

    .section { margin-top:16px; border:1px solid var(--border); border-radius:16px; background:var(--panel); padding:14px; }
    .section h2 { margin:0; font-size:15px; color:var(--accent); letter-spacing:.3px; }
    .section-sub { margin-top:6px; color:var(--muted); font-size:12px; }

    .take { margin-top:12px; font-size:18px; line-height:1.35; font-weight:600; color:#e9f2ff; }
    .signal-line { margin-top:10px; display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
    .signal-badge { border-radius:999px; padding:5px 11px; font-size:12px; font-weight:700; letter-spacing:.3px; border:1px solid var(--border); }
    .signal-low { color:#93c5fd; background:rgba(59,130,246,.15); border-color:rgba(59,130,246,.35); }
    .signal-medium { color:#fde68a; background:rgba(245,158,11,.15); border-color:rgba(245,158,11,.35); }
    .signal-high { color:#fdba74; background:rgba(249,115,22,.16); border-color:rgba(249,115,22,.35); }
    .signal-extreme { color:#fda4af; background:rgba(244,63,94,.18); border-color:rgba(244,63,94,.4); }

    .top-grid { margin-top:12px; display:grid; grid-template-columns:1fr; gap:10px; }
    @media (min-width: 900px) { .top-grid { grid-template-columns:repeat(3,minmax(0,1fr)); } }
    .signal-card { border:1px solid var(--border); background:var(--panel-strong); border-radius:14px; padding:12px; display:flex; flex-direction:column; gap:7px; }
    .signal-card .title { font-size:14px; line-height:1.3; font-weight:600; }
    .meta { display:flex; flex-wrap:wrap; gap:6px; color:var(--muted); font-size:11px; }
    .chip { border:1px solid var(--border); border-radius:999px; padding:2px 8px; font-size:11px; color:var(--muted); background:#0b1422; }
    .chip.hot { color:var(--hot); border-color:rgba(251,113,133,.4); }
    .chip.good { color:var(--good); border-color:rgba(52,211,153,.35); }
    .reason { color:#d3e2ff; font-size:12px; line-height:1.35; }

    .dashboard { margin-top:12px; display:grid; grid-template-columns:1fr; gap:10px; }
    @media (min-width: 900px) { .dashboard { grid-template-columns:1.4fr 1fr 1fr; } }
    .box { border:1px solid var(--border); background:rgba(10,18,30,.7); border-radius:14px; padding:12px; min-height:128px; }
    .box h3 { margin:0 0 9px 0; color:#d6e6ff; font-size:13px; }
    .list { margin:0; padding-left:18px; }
    .list li { margin:6px 0; font-size:12px; line-height:1.35; }
    .radar-row { display:flex; justify-content:space-between; gap:10px; margin:7px 0; font-size:12px; }
    .bar { height:7px; border:1px solid var(--border); border-radius:999px; overflow:hidden; background:#09111e; margin-top:3px; }
    .bar > span { display:block; height:100%; background:linear-gradient(90deg,#7bdff2,#a78bfa); }

    .watchlist { display:flex; flex-wrap:wrap; gap:6px; }
    .watch { border:1px solid var(--border); border-radius:999px; padding:4px 9px; background:#0a1321; font-size:12px; color:#c9dcff; }

    .controls { margin-top:14px; display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
    .controls select { background:#0a1321; color:var(--text); border:1px solid var(--border); border-radius:9px; padding:6px 9px; }

    .intel-grid { margin-top:10px; display:grid; grid-template-columns:1fr; gap:9px; }
    .intel-card { border:1px solid var(--border); background:var(--panel); border-radius:12px; padding:11px; }
    .intel-top { display:flex; justify-content:space-between; align-items:flex-start; gap:10px; }
    .intel-title { font-size:14px; line-height:1.3; margin-top:5px; }
    .intel-kpi { display:flex; flex-wrap:wrap; gap:5px; justify-content:flex-end; }
    .source { color:var(--accent); font-size:11px; }
    .intel-reason { margin-top:7px; color:#d3e3ff; font-size:12px; line-height:1.32; }
  </style>
</head>
<body>
<div class="wrap">
  <section class="hero">
    <div class="eyebrow">Daily Cockpit</div>
    <h1>AI Strategic Radar</h1>
    <div class="subtitle">Frontier labs, agents, compute, China stack, market power shifts</div>
    <div class="hero-meta">
      <span class="pill">Briefing: {{ generated_at }}</span>
      <span class="pill">Items: {{ items|length }}</span>
      <span class="pill">Dominant theme: {{ dominant_theme_label }}</span>
    </div>
  </section>

  <section class="section">
    <h2>Today’s Strategic Take</h2>
    <div class="take">{{ strategic_take }}</div>
    <div class="signal-line">
      <span class="signal-badge signal-{{ signal_level_class }}">{{ signal_level }}</span>
      <span class="pill">Top avg score: {{ top_avg_score }}</span>
      <span class="pill">Theme concentration: {{ theme_concentration_pct }}%</span>
      <span class="pill">Noise suppressed: {{ noise_suppressed_count }}</span>
    </div>

    <div class="top-grid">
      {% for item in top_signals %}
        <article class="signal-card">
          <div class="meta">
            <span class="chip">{{ item.source }}</span>
            <span class="chip">{{ item.theme }}</span>
            <span class="chip hot">score {{ item.display_score }}</span>
          </div>
          <div class="title">
            <a href="{{ (item.url or item.link)|safe_url }}" target="_blank" rel="noopener noreferrer">{{ item.title }}</a>
          </div>
          <div class="reason">{{ item.reason }}</div>
          <div class="meta">
            {% for e in item.entities[:4] %}
              <span class="chip good">{{ e }}</span>
            {% endfor %}
          </div>
        </article>
      {% endfor %}
    </div>
  </section>

  <section class="dashboard">
    <article class="box">
      <h3>Theme Radar</h3>
      {% if theme_rows %}
        {% for row in theme_rows %}
          <div class="radar-row">
            <span>{{ row.label }}</span>
            <span>{{ row.count }}</span>
          </div>
          <div class="bar"><span style="width: {{ row.pct }}%;"></span></div>
        {% endfor %}
      {% else %}
        <div class="section-sub">Sin temas detectables todavía.</div>
      {% endif %}
    </article>

    <article class="box">
      <h3>Entity Momentum / Watchlist</h3>
      {% if entity_watchlist %}
        <div class="watchlist">
          {% for entity in entity_watchlist %}
            <span class="watch">{{ entity }}</span>
          {% endfor %}
        </div>
      {% else %}
        <div class="section-sub">OpenAI · Anthropic · Google DeepMind · DeepSeek · Meta · xAI · NVIDIA · Huawei</div>
      {% endif %}
      <div class="section-sub" style="margin-top:10px;">Noise Suppressed: {{ noise_suppressed_count }} items con noise_penalty ≥ 8.</div>
    </article>

    <article class="box">
      <h3>Watchlist for Tomorrow</h3>
      <ul class="list">
        {% for watch in watch_for_tomorrow %}
          <li>{{ watch }}</li>
        {% endfor %}
      </ul>
    </article>
  </section>

  <section class="section">
    <h2>Supporting Intelligence</h2>
    <div class="section-sub">Listado completo de soporte para profundizar señales.</div>

    <div class="controls">
      <label for="viewFilter" class="pill">Vista</label>
      <select id="viewFilter" onchange="applyFilter()">
        <option value="all">Todas</option>
        <option value="new">Solo novedades</option>
        <option value="repeat">Solo repetidas</option>
      </select>
    </div>

    <div class="intel-grid" id="itemsGrid">
      {% for item in items %}
        <article class="intel-card" data-repeat="{{ '1' if item.is_repeat else '0' }}">
          <div class="intel-top">
            <div>
              <div class="source">{{ item.source }}</div>
              <div class="intel-title">
                <a href="{{ (item.url or item.link)|safe_url }}" target="_blank" rel="noopener noreferrer">{{ item.title }}</a>
              </div>
            </div>
            <div class="intel-kpi">
              <span class="chip hot">score {{ item.display_score }}</span>
              <span class="chip">{{ item.theme }}</span>
              {% if item.noise_penalty and item.noise_penalty >= 8 %}<span class="chip">noise {{ item.noise_penalty }}</span>{% endif %}
              {% if item.is_repeat %}<span class="chip">repetida</span>{% else %}<span class="chip good">nueva</span>{% endif %}
            </div>
          </div>
          <div class="meta">
            {% for e in item.entities[:5] %}<span class="chip">{{ e }}</span>{% endfor %}
            <span class="chip">{{ item.published or "sin fecha" }}</span>
          </div>
          {% if item.reason %}
            <div class="intel-reason">{{ item.reason }}</div>
          {% endif %}
        </article>
      {% endfor %}
    </div>
  </section>
</div>
<script>
function applyFilter(){
  const value = document.getElementById('viewFilter').value;
  document.querySelectorAll('#itemsGrid .intel-card').forEach((card)=>{
    const isRepeat = card.dataset.repeat === '1';
    const show = value === 'all' || (value === 'new' && !isRepeat) || (value === 'repeat' && isRepeat);
    card.style.display = show ? '' : 'none';
  });
}
</script>
</body>
</html>
""")

def render_index(items, briefing=None):
    def pick_score(it: dict) -> int:
        for key in ("final_score", "score", "adjusted_score", "heuristic_score"):
            val = it.get(key)
            if isinstance(val, (int, float)):
                return int(round(val))
            if isinstance(val, str):
                try:
                    return int(round(float(val)))
                except ValueError:
                    continue
        return 0

    def pick_theme(it: dict) -> str:
        return (it.get("strategic_theme") or it.get("primary") or "other").strip() or "other"

    def pick_reason(it: dict) -> str:
        txt = (it.get("ranking_reason") or it.get("why") or "").strip()
        if txt:
            return txt
        return (it.get("summary") or "").strip()[:180]

    enriched = []
    for raw in items or []:
        it = dict(raw)
        it["display_score"] = pick_score(it)
        it["theme"] = pick_theme(it)
        it["reason"] = pick_reason(it)
        it.setdefault("entities", [])
        it.setdefault("tags", [])
        enriched.append(it)

    enriched.sort(key=lambda x: x.get("display_score", 0), reverse=True)
    top_signals = enriched[:3]
    top_for_signal = enriched[:6]

    top_scores = [x.get("display_score", 0) for x in top_for_signal]
    top_avg_score = round(sum(top_scores) / max(1, len(top_scores)), 1)

    top_theme_counter = Counter(x.get("theme", "other") for x in top_for_signal if x.get("theme"))
    dominant_theme, dominant_count = ("other", 0)
    if top_theme_counter:
        dominant_theme, dominant_count = top_theme_counter.most_common(1)[0]
    theme_concentration = dominant_count / max(1, len(top_for_signal))
    theme_concentration_pct = int(round(theme_concentration * 100))

    if top_avg_score >= 78 or (top_avg_score >= 70 and theme_concentration >= 0.60):
        signal_level = "Extreme"
    elif top_avg_score >= 62 or theme_concentration >= 0.50:
        signal_level = "High"
    elif top_avg_score >= 45:
        signal_level = "Medium"
    else:
        signal_level = "Low"
    signal_level_class = signal_level.lower()

    if top_signals:
        lead = top_signals[0]
        strategic_take = (
            f"Cambio crítico en {lead.get('theme', 'other')}: "
            f"{lead.get('source', 'fuente n/a')} acelera la narrativa con '{lead.get('title', '')[:120]}'."
        )
    else:
        strategic_take = "No hay suficiente señal hoy. Mantener vigilancia en frontier labs, agentes y compute."

    theme_counter = Counter(x.get("theme", "other") for x in enriched if x.get("theme"))
    total_items = max(1, len(enriched))
    theme_rows = [
        {"label": k, "count": v, "pct": round((v / total_items) * 100, 1)}
        for k, v in theme_counter.most_common(6)
    ]

    entity_counter = Counter()
    for it in top_for_signal:
        for e in (it.get("entities") or []):
            if isinstance(e, str) and e.strip():
                entity_counter[e.strip()] += 1
    entity_watchlist = [name for name, _ in entity_counter.most_common(10)]

    noise_suppressed_count = sum(1 for it in enriched if isinstance(it.get("noise_penalty"), (int, float)) and it.get("noise_penalty", 0) >= 8)

    watch_for_tomorrow = []
    if dominant_theme and dominant_theme != "other":
        watch_for_tomorrow.append(f"Watch for continuation or reversal in '{dominant_theme}'.")
    if entity_watchlist:
        watch_for_tomorrow.append(f"Watch for follow-up from {entity_watchlist[0]} and {entity_watchlist[1] if len(entity_watchlist) > 1 else 'other frontier actors'}.")
    if noise_suppressed_count > 0:
        watch_for_tomorrow.append("Watch for fresh, high-signal replacements to today's suppressed noise cluster.")
    while len(watch_for_tomorrow) < 3:
        watch_for_tomorrow.append("Watch for model pricing, compute capacity and strategic power-shift signals.")

    return TEMPLATE.render(
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        items=enriched,
        briefing=briefing or {},
        strategic_take=strategic_take,
        signal_level=signal_level,
        signal_level_class=signal_level_class,
        top_avg_score=top_avg_score,
        theme_concentration_pct=theme_concentration_pct,
        dominant_theme_label=dominant_theme,
        top_signals=top_signals,
        theme_rows=theme_rows,
        entity_watchlist=entity_watchlist,
        noise_suppressed_count=noise_suppressed_count,
        watch_for_tomorrow=watch_for_tomorrow[:3],
    )
