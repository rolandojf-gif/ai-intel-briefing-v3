from datetime import datetime
from urllib.parse import urlparse
from collections import Counter
import re

from jinja2 import Environment, select_autoescape


def _safe_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return "#"

    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return raw
    return "#"


def human_theme(theme: str) -> str:
    mapping = {
        "agents_automation": "Agentic automation",
        "compute_chips_dc": "Compute & chips",
        "frontier_capability": "Frontier capability",
        "model_economics_pricing": "Model economics",
        "geopolitics_power": "Geopolitics & power",
        "china_stack": "China AI stack",
        "other": "Other signals",
        "misc": "Other signals",
    }
    key = (theme or "other").strip()
    return mapping.get(key, mapping.get(key.lower(), key.replace("_", " ").title()))


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


def item_reason(item: dict, limit: int = 150) -> str:
    txt = (item.get("why") or "").strip()
    if not txt:
        txt = (item.get("summary") or "").strip()
    return truncate_text(txt, limit) if txt else "No analysis available."


def item_entities(item: dict, limit: int = 6) -> list[str]:
    raw = item.get("entities") or []
    out: list[str] = []
    seen = set()

    for e in raw:
        if not isinstance(e, str):
            continue
        name = re.sub(r"\s+", " ", e.strip())
        if not name or len(name) < 3:
            continue
        if len(name) > 24:
            continue
        if name.lower() in {"image", "thread", "post", "tweet", "update"}:
            continue
        # Evita basura semántica muy larga o tipo frase.
        if len(name.split()) > 3:
            continue
        k = name.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(name)
        if len(out) >= limit:
            break
    return out


def truncate_text(text: str, limit: int = 140) -> str:
    raw = (text or "").strip()
    if len(raw) <= limit:
        return raw
    return raw[: max(0, limit - 1)].rstrip() + "…"


def signal_level(top_items: list[dict], all_items: list[dict] | None = None) -> tuple[str, str, float, float]:
    if not top_items:
        return "Low", "low", 0.0, 0.0

    scores = [score_value(x) for x in top_items]
    avg = sum(scores) / max(1, len(scores))
    pool = all_items if all_items else top_items
    theme_counts = Counter((x.get("theme") or "other") for x in pool)
    dominant = theme_counts.most_common(1)[0][1] if theme_counts else 0
    concentration = dominant / max(1, len(pool))

    if avg >= 80 or (avg >= 72 and concentration >= 0.6):
        return "Extreme", "extreme", avg, concentration
    if avg >= 64 or concentration >= 0.50:
        return "High", "high", avg, concentration
    if avg >= 46:
        return "Medium", "medium", avg, concentration
    return "Low", "low", avg, concentration


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
    :root{
      --bg:#070b12; --bg-soft:#0b111d; --panel:#101a2b; --panel-soft:#0f1827; --border:#223149;
      --text:#e3eeff; --muted:#8ea8cc; --cyan:#7bdff2; --purple:#a78bfa; --amber:#f59e0b; --rose:#fb7185; --ok:#34d399;
    }
    *{box-sizing:border-box}
    body{margin:0;background:radial-gradient(circle at top,#0f1d34 0%,#080d16 38%,#070b12 100%);color:var(--text);font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif}
    a{color:#b8c7ff;text-decoration:none} a:hover{text-decoration:underline}
    .wrap{max-width:1250px;margin:0 auto;padding:18px}

    .hero{
      border:1px solid var(--border);
      background:radial-gradient(1200px 600px at 0% 0%,rgba(123,223,242,.22),transparent 55%),radial-gradient(1000px 500px at 100% 0%,rgba(167,139,250,.18),transparent 55%),linear-gradient(180deg,#0e1727,#0c1422);
      border-radius:22px;padding:28px 26px 24px;box-shadow:0 12px 40px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.05);
    }
    .eyebrow{font-size:12px;letter-spacing:1px;color:var(--cyan);text-transform:uppercase;font-weight:700}
    h1{margin:8px 0 0 0;font-size:clamp(34px,5vw,56px);line-height:1.02;letter-spacing:.3px}
    .subtitle{margin-top:10px;color:var(--muted);font-size:15px;max-width:840px}
    .hero-kpis{margin-top:18px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
    @media (min-width:920px){.hero-kpis{grid-template-columns:repeat(5,minmax(0,1fr));}}
    .kpi{border:1px solid var(--border);border-radius:13px;background:rgba(9,15,25,.58);padding:10px 11px}
    .kpi .k{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.4px}
    .kpi .v{margin-top:4px;font-size:21px;font-weight:700}
    .signal{display:inline-flex;align-items:center;border-radius:999px;padding:6px 12px;font-weight:700;font-size:12px;border:1px solid transparent}
    .signal.low{color:#93c5fd;background:rgba(59,130,246,.14);border-color:rgba(59,130,246,.38)}
    .signal.medium{color:#fde68a;background:rgba(245,158,11,.16);border-color:rgba(245,158,11,.38)}
    .signal.high{color:#fdba74;background:rgba(249,115,22,.17);border-color:rgba(249,115,22,.38)}
    .signal.extreme{color:#fda4af;background:rgba(244,63,94,.18);border-color:rgba(244,63,94,.42)}
    .topnav{margin-top:14px;display:flex;gap:10px;align-items:center}
    .topnav-link{display:inline-flex;padding:8px 12px;border-radius:10px;border:1px solid var(--border);background:#0d1726;color:var(--muted);font-size:13px;font-weight:600}
    .topnav-link.active{background:rgba(123,223,242,.12);border-color:rgba(123,223,242,.4);color:#d9f8ff}
    .brief{margin-top:12px;border:1px solid var(--border);border-radius:18px;background:var(--panel);padding:14px}
    .brief-inner{display:grid;grid-template-columns:1fr;gap:12px}
    @media (min-width:980px){.brief-inner{grid-template-columns:1.5fr 1fr 1fr;}}
    .brief-body{display:flex;flex-direction:column;gap:8px}
    .brief-signal{display:flex;gap:9px;align-items:flex-start;font-size:13px;line-height:1.35}
    .brief-n{min-width:22px;height:22px;border-radius:999px;border:1px solid rgba(123,223,242,.5);display:inline-flex;align-items:center;justify-content:center;color:var(--cyan);font-weight:700;font-size:12px}
    .brief-block{border:1px solid var(--border);border-radius:12px;padding:10px;background:#0d1726}
    .brief-block.risks{border-color:rgba(245,158,11,.45)}
    .brief-block.watch{border-color:rgba(167,139,250,.45)}
    .brief-risk-item{color:#fcd9a8;font-size:13px;line-height:1.35;margin:7px 0}
    .brief-watch-item{color:#ddd6fe;font-size:13px;line-height:1.35;margin:7px 0}

    .thesis{margin-top:16px;border:1px solid var(--border);border-radius:16px;background:linear-gradient(180deg,rgba(255,255,255,.02),rgba(255,255,255,0));padding:14px}
    .thesis .lbl{font-size:12px;text-transform:uppercase;letter-spacing:.7px;color:var(--cyan);font-weight:700}
    .thesis .txt{margin-top:7px;font-size:clamp(18px,2.2vw,28px);line-height:1.25;font-weight:650;max-width:960px}

    .signals-layout{margin-top:16px;display:grid;grid-template-columns:1fr;gap:12px}
    @media (min-width:980px){.signals-layout{grid-template-columns:1.55fr 1fr;}}
    .lead{
      border:1px solid var(--border);border-radius:20px;padding:18px;
      background:linear-gradient(180deg,#121f33,#0f1a2c 65%,#0e1828);
      box-shadow:0 10px 28px rgba(0,0,0,.28);
    }
    .lead-title{margin:9px 0 0 0;font-size:clamp(24px,3vw,40px);line-height:1.12}
    .lead-meta{margin-top:10px;display:flex;gap:8px;flex-wrap:wrap}
    .badge{display:inline-flex;align-items:center;border:1px solid var(--border);border-radius:999px;padding:5px 10px;font-size:12px;color:#cfe0ff;background:#0d1726}
    .badge.score{color:var(--rose);border-color:rgba(251,113,133,.45)}
    .badge.theme{color:var(--cyan);border-color:rgba(123,223,242,.42)}
    .lead-why{margin-top:12px;font-size:14px;line-height:1.45;color:#d4e3ff;max-width:920px;border-left:3px solid rgba(123,223,242,.7);padding-left:11px;font-style:italic}
    .lead-entities{margin-top:10px;display:flex;gap:8px;flex-wrap:wrap}
    .entity{padding:6px 10px;border-radius:999px;border:1px solid var(--border);background:#0a1422;font-size:12px}
    .lead-cta{margin-top:14px}
    .cta{display:inline-flex;padding:9px 12px;border-radius:10px;border:1px solid rgba(123,223,242,.45);background:rgba(123,223,242,.08);color:#d8f7ff;font-weight:650}

    .side{display:grid;grid-template-columns:1fr;gap:10px}
    .side-card{border:1px solid var(--border);border-radius:16px;background:var(--panel-soft);padding:14px}
    .side-card h3{margin:8px 0 0;font-size:21px;line-height:1.2}
    .side-why{margin-top:8px;font-size:13px;color:#cfddf7;line-height:1.35;border-left:3px solid rgba(123,223,242,.55);padding-left:9px;font-style:italic}

    .panels{margin-top:16px;display:grid;grid-template-columns:1fr;gap:12px}
    @media (min-width:980px){.panels{grid-template-columns:1.2fr 1fr;}}
    .panel{border:1px solid var(--border);border-radius:16px;background:var(--panel);padding:14px}
    .panel h2{margin:0 0 10px;font-size:18px}
    .theme-row{margin:9px 0}
    .theme-top{display:flex;justify-content:space-between;align-items:center}
    .theme-label{font-size:13px}
    .theme-num{font-size:17px;font-weight:700}
    .theme-bar{height:12px;border-radius:999px;border:1px solid var(--border);overflow:hidden;background:#0b1423;margin-top:6px}
    .theme-fill{height:100%;background:linear-gradient(90deg,var(--cyan),var(--purple))}
    .dominant{margin-top:11px;padding:9px 10px;border:1px solid rgba(123,223,242,.35);border-radius:11px;background:rgba(123,223,242,.08);font-size:13px}

    .watch-badges{display:flex;flex-wrap:wrap;gap:8px}
    .watch{padding:8px 12px;border-radius:999px;border:1px solid var(--border);background:#0b1423;font-size:13px}
    .watch.lead{border-color:rgba(251,113,133,.45);background:rgba(251,113,133,.08)}
    .watch.top{border-color:rgba(123,223,242,.45);background:rgba(123,223,242,.07)}
    .small-note{margin-top:11px;font-size:12px;color:var(--muted)}
    .tomorrow{margin:0;padding-left:18px}
    .tomorrow li{margin:8px 0;line-height:1.35}

    .support{margin-top:20px;border:1px solid var(--border);border-radius:18px;background:rgba(10,16,26,.7);padding:16px}
    .support h2{margin:0;font-size:26px}
    .support-sub{margin-top:5px;color:var(--muted)}
    .controls{margin-top:12px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
    .pill{border:1px solid var(--border);border-radius:999px;padding:5px 10px;color:var(--muted);font-size:12px}
    select{background:#0a1320;color:var(--text);border:1px solid var(--border);border-radius:10px;padding:7px 10px}
    .intel{margin-top:10px;display:grid;grid-template-columns:1fr;gap:9px}
    .intel-card{border:1px solid var(--border);border-radius:13px;background:#0f1929;padding:12px}
    .intel-head{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}
    .intel-source{font-size:12px;color:var(--cyan)}
    .intel-title{margin-top:5px;font-size:18px;line-height:1.25}
    .intel-badges{display:flex;gap:7px;flex-wrap:wrap;justify-content:flex-end}
    .intel-reason{margin-top:8px;color:#cddcf7;font-size:13px;line-height:1.35}
  </style>
</head>
<body>
<div class="wrap">
  <section class="hero">
    <div class="eyebrow">Morning Intelligence Brief</div>
    <h1>AI Strategic Radar</h1>
    <div class="subtitle">Frontier labs, agents, compute, China stack, market power shifts</div>
    <div class="hero-kpis">
      <div class="kpi"><div class="k">Date</div><div class="v">{{ generated_at }}</div></div>
      <div class="kpi"><div class="k">Signal level</div><div class="v"><span class="signal {{ signal_class }}">{{ signal_label }}</span></div></div>
      <div class="kpi"><div class="k">Dominant theme</div><div class="v">{{ dominant_theme_label }}</div></div>
      <div class="kpi"><div class="k">Strong signals</div><div class="v">{{ strong_signals_count }}</div></div>
      <div class="kpi"><div class="k">Noise filtered</div><div class="v">{{ noise_suppressed_count }}</div></div>
    </div>
    <div class="thesis">
      <div class="lbl">Today’s thesis</div>
      <div class="txt">{{ todays_thesis }}</div>
    </div>
  </section>
  <nav class="topnav">
    <a class="topnav-link active" href="./index.html">Daily</a>
    <a class="topnav-link" href="./weekly.html">Weekly</a>
  </nav>
  <section class="brief">
    <div class="brief-inner">
      <div class="brief-body">
        <div class="eyebrow">Intelligence Brief</div>
        {% for s in brief_signals %}
          <div class="brief-signal"><span class="brief-n">{{ loop.index }}</span><span>{{ s }}</span></div>
        {% endfor %}
      </div>
      <div class="brief-block risks">
        <div class="eyebrow" style="color:var(--amber)">Risks</div>
        {% for r in brief_risks %}
          <div class="brief-risk-item">• {{ r }}</div>
        {% endfor %}
      </div>
      <div class="brief-block watch">
        <div class="eyebrow" style="color:var(--purple)">Watch</div>
        {% for w in brief_watch %}
          <div class="brief-watch-item">• {{ w }}</div>
        {% endfor %}
      </div>
    </div>
  </section>

  <section class="signals-layout">
    <article class="lead">
      <div class="eyebrow">Lead Signal</div>
      <h2 class="lead-title">{{ lead.title }}</h2>
      <div class="lead-meta">
        <span class="badge">{{ lead.source }}</span>
        <span class="badge theme">{{ lead.theme_label }}</span>
        <span class="badge score">Score {{ lead.score }}</span>
        {% if lead.noise_penalty >= 8 %}<span class="badge">Noise {{ lead.noise_penalty }}</span>{% endif %}
      </div>
      {% if lead.reason %}<div class="lead-why">{{ lead.reason }}</div>{% endif %}
      <div class="lead-entities">
        {% for e in lead.entities %}
          <span class="entity">{{ e }}</span>
        {% endfor %}
      </div>
      <div class="lead-cta">
        <a class="cta" href="{{ (lead.url or lead.link)|safe_url }}" target="_blank" rel="noopener noreferrer">Read more →</a>
      </div>
    </article>

    <aside class="side">
      {% for item in secondary_signals %}
      <article class="side-card">
        <div class="lead-meta">
          <span class="badge">{{ item.source }}</span>
          <span class="badge theme">{{ item.theme_label }}</span>
          <span class="badge score">Score {{ item.score }}</span>
        </div>
        <h3><a href="{{ (item.url or item.link)|safe_url }}" target="_blank" rel="noopener noreferrer">{{ item.title }}</a></h3>
        <div class="side-why">{{ item.reason }}</div>
      </article>
      {% endfor %}
    </aside>
  </section>

  <section class="panels">
    <article class="panel">
      <h2>Theme Radar</h2>
      {% for t in theme_rows %}
      <div class="theme-row">
        <div class="theme-top">
          <div class="theme-label">{{ t.label }}</div>
          <div class="theme-num">{{ t.count }} · {{ t.pct }}%</div>
        </div>
        <div class="theme-bar"><div class="theme-fill" style="width: {{ t.pct }}%;"></div></div>
      </div>
      {% endfor %}
      <div class="dominant">Dominant today: <strong>{{ dominant_theme_label }}</strong>.</div>
    </article>

    <article class="panel">
      <h2>Entity Momentum / Watchlist</h2>
      <div class="watch-badges">
        {% for ent in momentum_entities %}
          <span class="watch {% if ent in lead_entities %}lead{% elif ent in top_entities %}top{% endif %}">{{ ent }}</span>
        {% endfor %}
      </div>
      <div class="small-note">Noise Suppressed: {{ noise_suppressed_count }} items with noise penalty ≥ 8.</div>
      <h2 style="margin-top:14px;">Watchlist for Tomorrow</h2>
      <ul class="tomorrow">
        {% for w in watch_for_tomorrow %}
          <li>{{ w }}</li>
        {% endfor %}
      </ul>
    </article>
  </section>

  <section class="support">
    <h2>Supporting Intelligence</h2>
    <div class="support-sub">Secondary evidence layer. Useful for drill-down, not the main narrative.</div>
    <div class="controls">
      <span class="pill">View</span>
      <select id="viewFilter" onchange="applyFilter()">
        <option value="all">All</option>
        <option value="new">New only</option>
        <option value="repeat">Repeated only</option>
      </select>
    </div>
    <div class="intel" id="itemsGrid">
      {% for item in items %}
      <article class="intel-card" data-repeat="{{ '1' if item.is_repeat else '0' }}">
        <div class="intel-head">
          <div>
            <div class="intel-source">{{ item.source }}</div>
            <div class="intel-title"><a href="{{ (item.url or item.link)|safe_url }}" target="_blank" rel="noopener noreferrer">{{ item.title }}</a></div>
          </div>
          <div class="intel-badges">
            <span class="badge score">{{ item.score }}</span>
            <span class="badge theme">{{ item.theme_label }}</span>
            {% if item.noise_penalty >= 8 %}<span class="badge">Noise {{ item.noise_penalty }}</span>{% endif %}
          </div>
        </div>
        <div class="intel-reason">{{ item.reason }}</div>
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
    enriched = []
    for raw in (items or []):
        it = dict(raw)
        it["score"] = score_value(it)
        it["theme"] = (it.get("strategic_theme") or it.get("primary") or "other").strip() or "other"
        it["theme_label"] = human_theme(it["theme"])
        it["reason"] = item_reason(it, limit=170)
        it["entities"] = item_entities(it, limit=6)
        it["noise_penalty"] = int(it.get("noise_penalty", 0) or 0)
        enriched.append(it)

    enriched.sort(key=lambda x: x.get("score", 0), reverse=True)
    lead = enriched[0] if enriched else {
        "title": "No strong lead signal detected today.",
        "source": "Radar",
        "theme_label": human_theme("other"),
        "score": 0,
        "reason": "Insufficient data to produce a dominant lead signal.",
        "entities": [],
        "noise_penalty": 0,
        "url": "#",
        "link": "#",
    }
    secondary_signals = enriched[1:3]

    top3 = enriched[:3]
    signal_label, signal_class, avg_top, concentration = signal_level(top3, enriched)
    strong_signals_count = sum(1 for x in enriched if x.get("score", 0) >= 70)
    noise_suppressed_count = sum(1 for x in enriched if x.get("noise_penalty", 0) >= 8)

    theme_counter = Counter(x.get("theme", "other") for x in enriched if x.get("theme"))
    dominant_theme = theme_counter.most_common(1)[0][0] if theme_counter else "other"
    dominant_theme_label = human_theme(dominant_theme)
    total = max(1, len(enriched))
    theme_rows = []
    for t, c in theme_counter.most_common(6):
        pct = round((c / total) * 100, 1)
        theme_rows.append({"label": human_theme(t), "count": c, "pct": pct})
    if not theme_rows:
        theme_rows = [{"label": "Other signals", "count": 0, "pct": 0}]

    if briefing and briefing.get("signals"):
        todays_thesis = briefing["signals"][0]
    else:
        thesis_title = truncate_text(lead.get("title", ""), 108)
        todays_thesis = f"{dominant_theme_label}: {thesis_title}"

    top_entity_counter = Counter()
    for it in top3:
        for e in it.get("entities", []):
            top_entity_counter[e] += 1
    top_entities = [x for x, _ in top_entity_counter.most_common(8)]
    lead_entities = lead.get("entities", [])[:4]

    fallback_watch = ["OpenAI", "Anthropic", "Google DeepMind", "DeepSeek", "Meta", "xAI", "NVIDIA", "Huawei"]
    momentum_entities = top_entities[:] if top_entities else []
    for ent in fallback_watch:
        if ent not in momentum_entities:
            momentum_entities.append(ent)
        if len(momentum_entities) >= 10:
            break

    watch_for_tomorrow = []
    watch_for_tomorrow.append(f"Watch for follow-through in {dominant_theme_label}.")
    if top_entities:
        watch_for_tomorrow.append(f"Watch for narrative acceleration from {top_entities[0]} and {top_entities[1] if len(top_entities) > 1 else 'other frontier actors'}.")
    else:
        watch_for_tomorrow.append("Watch for fresh frontier-lab releases that can displace today’s lead.")
    watch_for_tomorrow.append("Watch for pricing/compute updates that can re-rank strategic urgency tomorrow.")

    briefing_obj = briefing or {}
    brief_signals = (briefing_obj.get("signals") or [])[:5]
    brief_risks = (briefing_obj.get("risks") or [])[:3]
    brief_watch = (briefing_obj.get("watch") or [])[:3]

    if not brief_signals:
        brief_signals = [f"Top narrative: {dominant_theme_label}.", "Monitor top-ranked shift for persistence."]
    if not brief_risks:
        brief_risks = ["Potential over-concentration in one narrative cluster."]
    if not brief_watch:
        brief_watch = ["Watch for new hard-signal evidence in top themes."]

    return TEMPLATE.render(
        generated_at=datetime.now().strftime("%Y-%m-%d"),
        items=enriched,
        lead=lead,
        secondary_signals=secondary_signals,
        signal_label=signal_label,
        signal_class=signal_class,
        strong_signals_count=strong_signals_count,
        noise_suppressed_count=noise_suppressed_count,
        dominant_theme_label=dominant_theme_label,
        theme_rows=theme_rows,
        momentum_entities=momentum_entities,
        lead_entities=lead_entities,
        top_entities=top_entities,
        todays_thesis=todays_thesis,
        avg_top=round(avg_top, 1),
        concentration=round(concentration * 100, 1),
        watch_for_tomorrow=watch_for_tomorrow[:3],
        briefing=briefing_obj,
        brief_signals=brief_signals,
        brief_risks=brief_risks,
        brief_watch=brief_watch,
    )
