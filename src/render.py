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


def human_theme(theme: str) -> str:
    mapping = {
        "agents_automation": "Agents & automation",
        "compute_chips_dc": "Compute & chips",
        "frontier_capability": "Frontier models",
        "model_economics_pricing": "Model economics",
        "geopolitics_power": "Geopolitics",
        "china_stack": "China stack",
        "other": "Other",
        "misc": "Other",
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
        return "Extreme", "extreme"
    if score >= 65:
        return "High", "high"
    if score >= 45:
        return "Medium", "medium"
    return "Low", "low"


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
      --bg:#090a0c; --surface:#11151b; --surface2:#161b22; --line:#27313d;
      --text:#edf2f7; --muted:#9aa8b7; --cyan:#67e8f9; --green:#74d99f;
      --amber:#f4bd50; --red:#fb7185; --violet:#c4b5fd; --blue:#93c5fd;
      --shadow:0 16px 45px rgba(0,0,0,.32);
    }
    *{box-sizing:border-box}
    html{scroll-behavior:smooth}
    body{margin:0;background:#090a0c;color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif}
    body:before{content:"";position:fixed;inset:0;pointer-events:none;background:linear-gradient(145deg,rgba(103,232,249,.10),transparent 32%),linear-gradient(30deg,rgba(116,217,159,.08),transparent 40%);z-index:-1}
    a{color:#cfe6ff;text-decoration:none} a:hover{text-decoration:underline}
    .wrap{max-width:1240px;margin:0 auto;padding:18px}
    .topbar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px}
    .brand{font-weight:800;letter-spacing:.2px}.nav{display:flex;gap:8px;flex-wrap:wrap}
    .nav a{border:1px solid var(--line);border-radius:8px;padding:8px 10px;color:var(--muted);background:rgba(17,21,27,.72);font-size:13px}.nav a.active{color:var(--text);border-color:rgba(103,232,249,.55)}
    .hero{border:1px solid var(--line);background:linear-gradient(180deg,rgba(22,27,34,.96),rgba(13,16,21,.96));border-radius:8px;padding:22px;box-shadow:var(--shadow)}
    .eyebrow{font-size:11px;color:var(--cyan);font-weight:800;text-transform:uppercase;letter-spacing:.8px}
    h1{margin:6px 0 0;font-size:clamp(34px,6vw,68px);line-height:1;font-weight:850}
    .subtitle{margin-top:10px;color:var(--muted);font-size:15px;max-width:820px}
    .thesis{margin-top:16px;font-size:clamp(20px,3vw,34px);line-height:1.16;font-weight:760;max-width:980px}
    .metrics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:18px}
    @media (min-width:820px){.metrics{grid-template-columns:repeat(6,minmax(0,1fr))}}
    .metric{border:1px solid var(--line);background:#0d1117;border-radius:8px;padding:10px;min-height:78px}
    .metric .k{font-size:11px;color:var(--muted);text-transform:uppercase;font-weight:750}.metric .v{margin-top:7px;font-size:22px;font-weight:820;line-height:1.05}
    .signal{display:inline-flex;border:1px solid transparent;border-radius:999px;padding:5px 9px;font-size:12px;font-weight:850}
    .low{color:var(--blue);background:rgba(147,197,253,.10);border-color:rgba(147,197,253,.35)}
    .medium{color:var(--amber);background:rgba(244,189,80,.12);border-color:rgba(244,189,80,.38)}
    .high{color:var(--green);background:rgba(116,217,159,.12);border-color:rgba(116,217,159,.38)}
    .extreme{color:var(--red);background:rgba(251,113,133,.13);border-color:rgba(251,113,133,.42)}
    .grid{display:grid;grid-template-columns:1fr;gap:12px;margin-top:12px}@media (min-width:980px){.grid.two{grid-template-columns:1.35fr .9fr}.grid.three{grid-template-columns:1.2fr 1fr 1fr}}
    .panel,.lead,.mini,.feed-card{border:1px solid var(--line);border-radius:8px;background:rgba(17,21,27,.90)}
    .panel{padding:14px}.panel h2,.feed h2{margin:0 0 10px;font-size:17px}.lead{padding:18px;background:linear-gradient(180deg,#18202a,#111820)}
    .lead h2{font-size:clamp(26px,4vw,44px);line-height:1.08;margin:8px 0 0}
    .meta{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}.badge{display:inline-flex;align-items:center;border:1px solid var(--line);border-radius:999px;background:#0d1117;color:#dbe7f3;font-size:12px;padding:5px 9px}.badge.score{color:var(--red);border-color:rgba(251,113,133,.42)}.badge.theme{color:var(--cyan);border-color:rgba(103,232,249,.38)}.badge.repeat{color:var(--amber);border-color:rgba(244,189,80,.38)}
    .why{margin-top:13px;color:#d8e4ef;line-height:1.42;border-left:3px solid var(--cyan);padding-left:10px}
    .entities{display:flex;gap:7px;flex-wrap:wrap;margin-top:12px}.entity{border:1px solid var(--line);background:#0b0f14;border-radius:999px;padding:6px 9px;font-size:12px;color:#dfe8f2}
    .actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:15px}.btn{border:1px solid var(--line);background:#0d1117;color:var(--text);border-radius:8px;padding:9px 11px;font-weight:750;cursor:pointer;font-size:13px}.btn.primary{border-color:rgba(103,232,249,.5);background:rgba(103,232,249,.10)}.btn.fav.active{border-color:rgba(244,189,80,.6);color:var(--amber)}
    .mini{padding:13px}.mini h3{font-size:18px;line-height:1.18;margin:8px 0 0}.mini .why{font-size:13px}
    .brief-list{display:grid;gap:8px}.brief-row{display:grid;grid-template-columns:26px 1fr;gap:8px;align-items:start;font-size:14px;line-height:1.35}.num{width:24px;height:24px;border-radius:999px;border:1px solid rgba(103,232,249,.5);display:flex;align-items:center;justify-content:center;color:var(--cyan);font-size:12px;font-weight:800}
    .risk{color:#ffe0a3}.watch-text{color:#dcd4ff}.bar-row{margin:10px 0}.bar-top{display:flex;justify-content:space-between;gap:10px;font-size:13px}.bar{height:10px;border:1px solid var(--line);border-radius:999px;overflow:hidden;background:#0b0f14;margin-top:6px}.fill{height:100%;background:linear-gradient(90deg,var(--green),var(--cyan),var(--amber))}
    .controls{position:sticky;top:0;z-index:5;margin-top:14px;border:1px solid var(--line);border-radius:8px;background:rgba(9,10,12,.92);backdrop-filter:blur(10px);padding:10px;display:grid;gap:8px}
    @media (min-width:900px){.controls{grid-template-columns:1fr 180px 180px 170px}}
    input,select{width:100%;border:1px solid var(--line);border-radius:8px;background:#0d1117;color:var(--text);padding:10px;font:inherit}
    .feed{margin-top:14px}.feed-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px}.count{color:var(--muted);font-size:13px}
    .feed-grid{display:grid;grid-template-columns:1fr;gap:9px}.feed-card{padding:12px}.feed-card.hidden{display:none}.feed-card.favorited{border-color:rgba(244,189,80,.58)}
    .feed-top{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}.feed-title{font-size:17px;font-weight:760;line-height:1.25}.feed-reason{margin-top:8px;color:#cbd6e2;font-size:13px;line-height:1.38}.tiny{font-size:12px;color:var(--muted)}
    .empty{display:none;color:var(--muted);border:1px dashed var(--line);border-radius:8px;padding:18px;text-align:center}.empty.show{display:block}
    @media (max-width:700px){.wrap{padding:12px}.hero,.lead,.panel{padding:13px}.feed-top{display:block}.metric .v{font-size:19px}}
  </style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div class="brand">AI Strategic Radar</div>
    <nav class="nav">
      <a class="active" href="./index.html">Daily</a>
      <a href="./weekly.html">Weekly</a>
      <a href="#feed">Signals</a>
    </nav>
  </div>

  <section class="hero">
    <div class="eyebrow">Morning intelligence brief</div>
    <h1>{{ signal_label }} signal day</h1>
    <div class="subtitle">Frontier labs, agents, compute, China stack, model economics and power shifts.</div>
    <div class="thesis">{{ todays_thesis }}</div>
    <div class="metrics">
      <div class="metric"><div class="k">Date</div><div class="v">{{ generated_at }}</div></div>
      <div class="metric"><div class="k">Conviction</div><div class="v"><span class="signal {{ signal_class }}">{{ signal_label }}</span></div></div>
      <div class="metric"><div class="k">Top score</div><div class="v">{{ lead.score }}</div></div>
      <div class="metric"><div class="k">Avg top 3</div><div class="v">{{ avg_top }}</div></div>
      <div class="metric"><div class="k">Strong</div><div class="v">{{ strong_signals_count }}</div></div>
      <div class="metric"><div class="k">Filtered</div><div class="v">{{ noise_suppressed_count }}</div></div>
    </div>
  </section>

  <section class="grid two">
    <article class="lead" data-id="{{ lead.id }}">
      <div class="eyebrow">Lead signal</div>
      <h2>{{ lead.title }}</h2>
      <div class="meta">
        <span class="badge">{{ lead.source }}</span>
        <span class="badge theme">{{ lead.theme_label }}</span>
        <span class="badge score">Score {{ lead.score }}</span>
        <span class="badge {{ lead.conviction_class }}">{{ lead.conviction_label }}</span>
        {% if lead.is_repeat %}<span class="badge repeat">Repeat</span>{% endif %}
      </div>
      <div class="why">{{ lead.reason }}</div>
      <div class="entities">{% for e in lead.entities %}<span class="entity">{{ e }}</span>{% endfor %}</div>
      <div class="actions">
        <a class="btn primary" href="{{ (lead.url or lead.link)|safe_url }}" target="_blank" rel="noopener noreferrer">Read source</a>
        <button class="btn fav" data-fav="{{ lead.id }}" type="button">Save</button>
        <button class="btn" data-copy="{{ lead.title }} - {{ (lead.url or lead.link)|safe_url }}" type="button">Copy</button>
      </div>
    </article>
    <aside class="grid">
      {% for item in secondary_signals %}
      <article class="mini" data-id="{{ item.id }}">
        <div class="meta">
          <span class="badge">{{ item.source }}</span>
          <span class="badge theme">{{ item.theme_label }}</span>
          <span class="badge score">{{ item.score }}</span>
        </div>
        <h3><a href="{{ (item.url or item.link)|safe_url }}" target="_blank" rel="noopener noreferrer">{{ item.title }}</a></h3>
        <div class="why">{{ item.reason }}</div>
      </article>
      {% endfor %}
    </aside>
  </section>

  <section class="grid three">
    <article class="panel">
      <h2>Intelligence brief</h2>
      <div class="brief-list">
        {% for s in brief_signals %}
        <div class="brief-row"><span class="num">{{ loop.index }}</span><span>{{ s }}</span></div>
        {% endfor %}
      </div>
    </article>
    <article class="panel">
      <h2>Risks</h2>
      {% for r in brief_risks %}<p class="risk">{{ r }}</p>{% endfor %}
      <h2>Watch next</h2>
      {% for w in brief_watch %}<p class="watch-text">{{ w }}</p>{% endfor %}
    </article>
    <article class="panel">
      <h2>Entity momentum</h2>
      <div class="entities">{% for ent in momentum_entities %}<span class="entity">{{ ent }}</span>{% endfor %}</div>
      <p class="tiny">Dominant theme: {{ dominant_theme_label }}. Repeat pressure: {{ repeat_count }} items.</p>
    </article>
  </section>

  <section class="panel">
    <h2>Theme radar</h2>
    {% for t in theme_rows %}
    <div class="bar-row">
      <div class="bar-top"><span>{{ t.label }}</span><strong>{{ t.count }} / {{ t.pct }}%</strong></div>
      <div class="bar"><div class="fill" style="width: {{ t.pct }}%;"></div></div>
    </div>
    {% endfor %}
  </section>

  <section class="controls" aria-label="Signal controls">
    <input id="searchBox" type="search" placeholder="Search signal, source, entity"/>
    <select id="themeFilter">
      <option value="all">All themes</option>
      {% for t in theme_options %}<option value="{{ t }}">{{ t }}</option>{% endfor %}
    </select>
    <select id="viewFilter">
      <option value="all">All signals</option>
      <option value="new">New only</option>
      <option value="repeat">Repeated only</option>
      <option value="fav">Saved only</option>
    </select>
    <select id="sortMode">
      <option value="score">Sort by score</option>
      <option value="theme">Sort by theme</option>
      <option value="source">Sort by source</option>
    </select>
  </section>

  <section class="feed" id="feed">
    <div class="feed-head"><h2>Signal stream</h2><span class="count" id="visibleCount">{{ items|length }} visible</span></div>
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
            <div class="tiny">{{ item.source }} · {{ item.domain }}</div>
            <div class="feed-title"><a href="{{ (item.url or item.link)|safe_url }}" target="_blank" rel="noopener noreferrer">{{ item.title }}</a></div>
          </div>
          <div class="meta">
            <span class="badge score">{{ item.score }}</span>
            <span class="badge theme">{{ item.theme_label }}</span>
            {% if item.is_repeat %}<span class="badge repeat">Repeat</span>{% endif %}
          </div>
        </div>
        <div class="feed-reason">{{ item.reason }}</div>
        <div class="entities">{% for e in item.entities %}<span class="entity">{{ e }}</span>{% endfor %}</div>
        <div class="actions">
          <button class="btn fav" data-fav="{{ item.id }}" type="button">Save</button>
          <button class="btn" data-copy="{{ item.title }} - {{ (item.url or item.link)|safe_url }}" type="button">Copy</button>
        </div>
      </article>
      {% endfor %}
    </div>
    <div class="empty" id="emptyState">No signals match the current view.</div>
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
    btn.textContent = active ? 'Saved' : 'Save';
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
  document.getElementById('visibleCount').textContent = visible + ' visible';
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
  if(copy && navigator.clipboard){ await navigator.clipboard.writeText(copy.dataset.copy); copy.textContent = 'Copied'; setTimeout(()=>copy.textContent='Copy', 900); }
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
        it.update(
            {
                "id": f"sig-{idx}",
                "score": score,
                "theme": theme,
                "theme_label": theme_label,
                "reason": item_reason(it),
                "entities": entities,
                "noise_penalty": int(it.get("noise_penalty", 0) or 0),
                "conviction_label": label,
                "conviction_class": css,
                "domain": source_domain(url),
                "search_blob": " ".join(
                    [
                        str(it.get("title", "")),
                        str(it.get("source", "")),
                        theme_label,
                        " ".join(entities),
                        str(it.get("reason", "")),
                    ]
                ).lower(),
            }
        )
        enriched.append(it)

    enriched.sort(key=lambda x: x.get("score", 0), reverse=True)
    lead = enriched[0] if enriched else {
        "id": "sig-empty",
        "title": "No strong lead signal detected today.",
        "source": "Radar",
        "theme_label": human_theme("other"),
        "score": 0,
        "reason": "Insufficient data to produce a dominant lead signal.",
        "entities": [],
        "noise_penalty": 0,
        "url": "#",
        "link": "#",
        "conviction_label": "Low",
        "conviction_class": "low",
        "is_repeat": False,
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
    ] or [{"label": "Other", "count": 0, "pct": 0}]
    theme_options = sorted({x["label"] for x in theme_rows})

    briefing_obj = briefing or {}
    brief_signals = (briefing_obj.get("signals") or [])[:5]
    brief_risks = (briefing_obj.get("risks") or [])[:3]
    brief_watch = (briefing_obj.get("watch") or [])[:3]

    if briefing_obj.get("signals"):
        todays_thesis = briefing_obj["signals"][0]
    else:
        todays_thesis = f"{dominant_theme_label}: {truncate_text(lead.get('title', ''), 120)}"
    if not brief_signals:
        brief_signals = [todays_thesis, "Monitor whether the top theme persists tomorrow."]
    if not brief_risks:
        brief_risks = ["Low hard-signal density can make the day look busier than it is."]
    if not brief_watch:
        brief_watch = ["Watch for hard evidence: pricing, compute, policy or shipped model changes."]

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
        todays_thesis=todays_thesis,
        avg_top=round(avg_top, 1),
        briefing=briefing_obj,
        brief_signals=brief_signals,
        brief_risks=brief_risks,
        brief_watch=brief_watch,
    )
