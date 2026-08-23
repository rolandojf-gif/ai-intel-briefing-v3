"""Archivo del radar: índice de días + una página estática por snapshot.

Los JSON de docs/data/ son la fuente de verdad. El HTML se regenera desde ellos
con el renderer actual, degradando schema viejo (sin layer, sin thesis, sin
imagen). No se reingiere ni se llama a Gemini.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, select_autoescape

from src.render import _safe_url, render_index

DATA_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")
MONTHS_ES = (
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)

ENV = Environment(autoescape=select_autoescape(["html", "xml"]))


def snapshot_paths(data_dir: Path) -> list[Path]:
    if not data_dir.is_dir():
        return []
    paths = [p for p in data_dir.iterdir() if p.is_file() and DATA_NAME_RE.match(p.name)]
    paths.sort(key=lambda p: p.stem)
    return paths


def load_snapshot(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    raw.setdefault("date", path.stem)
    raw.setdefault("items", [])
    if not isinstance(raw["items"], list):
        raw["items"] = []
    briefing = raw.get("briefing")
    if not isinstance(briefing, dict):
        raw["briefing"] = {"thesis": str(briefing or "").strip()}
    activity = raw.get("activity")
    if not isinstance(activity, dict):
        raw["activity"] = {"label": "ARCHIVO", "class": "quiet"}
    else:
        activity.setdefault("label", "ARCHIVO")
        activity.setdefault("class", "quiet")
    return raw


def thesis_of(snap: dict) -> str:
    briefing = snap.get("briefing") or {}
    text = (briefing.get("thesis") or "").strip()
    if not text:
        signals = briefing.get("signals") or []
        if signals and isinstance(signals[0], str):
            text = signals[0].strip()
    if not text:
        items = snap.get("items") or []
        if items:
            it = items[0]
            text = (it.get("title_es") or it.get("title") or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:220]


def meta_of(snap: dict) -> dict:
    date = snap.get("date") or ""
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
        month_key = f"{dt.year}-{dt.month:02d}"
        month_label = f"{MONTHS_ES[dt.month].capitalize()} {dt.year}"
        day_label = f"{dt.day} {MONTHS_ES[dt.month][:3]}"
    except ValueError:
        month_key, month_label, day_label = date[:7], date, date
    items = snap.get("items") or []
    n_signal = sum(1 for it in items if it.get("layer") == "signal")
    activity = snap.get("activity") or {}
    return {
        "date": date,
        "thesis": thesis_of(snap),
        "n_items": len(items),
        "n_signal": n_signal or len(items),
        "activity_label": activity.get("label") or "",
        "activity_class": activity.get("class") or "quiet",
        "month_key": month_key,
        "month_label": month_label,
        "day_label": day_label,
        "degraded": bool(snap.get("degraded")),
    }


ARCHIVO_TEMPLATE = ENV.from_string("""
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Archivo · AI Strategic Radar</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<style>
  :root{
    --bg:#191a1a; --card:#202222; --card-hover:#262828; --line:#2f3131; --line-2:#3d4040;
    --txt:#e8e8e6; --txt-dim:#c8cbca; --dim:#9b9f9e; --dimmer:#6b6f6e;
    --accent:#20b8cd; --accent-soft:rgba(32,184,205,.12);
    --green:#4bd48b; --rose:#f2665f; --amber:#e8b750;
    --mono:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,monospace;
    --sans:'Inter',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
    --disp:'Space Grotesk','Inter',system-ui,sans-serif;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--txt);font-family:var(--sans);line-height:1.5}
  a{color:inherit;text-decoration:none}
  .wrap{max-width:860px;margin:0 auto;padding:0 24px 80px}
  .topbar{display:flex;align-items:center;justify-content:space-between;gap:16px;
          padding:18px 0;border-bottom:1px solid var(--line);margin-bottom:22px;flex-wrap:wrap}
  .brand{display:flex;align-items:center;gap:10px;font-family:var(--disp);font-size:17px;font-weight:700}
  .brand .dot{width:9px;height:9px;border-radius:50%;background:var(--accent);box-shadow:0 0 12px var(--accent)}
  .nav{display:flex;gap:6px}
  .nav a{font-size:13px;font-weight:600;padding:7px 15px;border-radius:999px;color:var(--dim)}
  .nav a.on{color:var(--accent);background:var(--accent-soft)}
  .nav a:hover{color:var(--txt)}
  .lead h1{margin:0 0 8px;font-family:var(--disp);font-size:clamp(22px,3vw,30px);letter-spacing:-.02em}
  .lead p{margin:0 0 18px;color:var(--dim);font-size:14.5px;max-width:60ch}
  .toolbar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:22px}
  .toolbar input{flex:1;min-width:200px;background:var(--card);border:1px solid var(--line);
                 color:var(--txt);border-radius:10px;padding:10px 12px;font:13px var(--sans)}
  .toolbar input:focus{outline:none;border-color:var(--accent)}
  .hits-h{font-family:var(--mono);font-size:11px;color:var(--dimmer);margin:4px 0 10px;letter-spacing:.04em}
  .hit{display:grid;grid-template-columns:108px 1fr auto;gap:12px;align-items:start;
       padding:12px 4px;border-bottom:1px solid var(--line)}
  .hit:hover{background:var(--card-hover)}
  .hit .t{font-size:14.5px;font-weight:600;line-height:1.35}
  .hit .t:hover{color:var(--accent)}
  .hit .w{font-size:13px;color:var(--dim);margin-top:4px;line-height:1.45;
          display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
  .hit .meta{font-family:var(--mono);font-size:10px;color:var(--dimmer);margin-top:4px}
  .copy-btn{font-family:var(--mono);font-size:9.5px;font-weight:700;letter-spacing:.08em;
            text-transform:uppercase;padding:4px 10px;border-radius:999px;cursor:pointer;
            border:1px solid var(--line);background:transparent;color:var(--dim)}
  .copy-btn:hover{color:var(--accent);border-color:rgba(32,184,205,.35)}
  .copy-btn.ok{color:#0d2b1c;background:var(--green);border-color:var(--green)}
  .months{display:flex;gap:6px;flex-wrap:wrap}
  .months a{font-family:var(--mono);font-size:10px;letter-spacing:.04em;color:var(--dim);
            padding:5px 9px;border:1px solid var(--line);border-radius:999px}
  .months a:hover{color:var(--txt);border-color:var(--line-2)}
  .month{margin:28px 0 8px;font-family:var(--disp);font-size:15px;font-weight:700}
  .day{display:grid;grid-template-columns:108px 1fr auto;gap:12px;align-items:baseline;
       padding:11px 4px;border-bottom:1px solid var(--line)}
  .day:hover{background:var(--card-hover)}
  .day .dt{font-family:var(--mono);font-size:12px;color:var(--accent);font-weight:600}
  .day .th{font-size:14px;line-height:1.4;color:var(--txt-dim);
           display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
  .day .n{font-family:var(--mono);font-size:10px;color:var(--dimmer);white-space:nowrap}
  .empty{padding:40px 10px;color:var(--dim);text-align:center}
  footer{margin-top:48px;padding-top:16px;border-top:1px solid var(--line);
         font-family:var(--mono);font-size:10px;color:var(--dimmer)}
  @media(max-width:640px){
    .wrap{padding:0 14px 60px}
    .day{grid-template-columns:84px 1fr;gap:8px}
    .day .n{grid-column:2;margin-top:-6px}
  }
</style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div class="brand"><span class="dot"></span> AI Strategic Radar</div>
    <nav class="nav">
      <a href="index.html">Diario</a>
      <a href="weekly.html">Semanal</a>
      <a class="on" href="archivo.html">Archivo</a>
    </nav>
  </div>
  <div class="lead">
    <h1>Archivo</h1>
    <p>{{ n }} días · {{ first }} – {{ last }}. Cada entrada es el radar de ese día, no un recorte.</p>
  </div>
  <div class="toolbar">
    <input id="q" type="search" placeholder="NVIDIA, agentes, 2026-08-22…" autocomplete="off"/>
    <div class="months">
      {% for m in months %}
      <a href="#m-{{ m.key }}">{{ m.short }}</a>
      {% endfor %}
    </div>
  </div>
  <div id="hits" hidden>
    <div class="hits-h" id="hits-h"></div>
    <div id="hits-list"></div>
  </div>
  <div id="cal">
  {% for m in months %}
  <h2 class="month" id="m-{{ m.key }}">{{ m.label }}</h2>
  {% for d in m.days %}
  <a class="day" href="d/{{ d.date }}.html" data-q="{{ d.date }} {{ d.thesis }}">
    <span class="dt">{{ d.date }}</span>
    <span class="th">{{ d.thesis or "Sin tesis — heurística" }}</span>
    <span class="n">{{ d.n_signal }} señales</span>
  </a>
  {% endfor %}
  {% endfor %}
  </div>
  <div class="empty" id="none" hidden>Nada coincide.</div>
  <footer>{{ n }} snapshots · {{ n_entries }} señales indexadas · falta {{ missing }}</footer>
</div>
<script>
(function(){
  var q = document.getElementById('q');
  var rows = Array.prototype.slice.call(document.querySelectorAll('.day'));
  var none = document.getElementById('none');
  var cal = document.getElementById('cal');
  var hitsBox = document.getElementById('hits');
  var hitsList = document.getElementById('hits-list');
  var hitsH = document.getElementById('hits-h');
  var months = document.querySelector('.months');
  var index = null;
  var loading = false;

  function fold(s){
    return (s || '').toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g, '');
  }
  function tokens(s){
    return fold(s).split(/[^a-z0-9]+/).filter(function(t){ return t.length >= 2; });
  }
  function hay(it){
    return fold([it.d, it.t, it.s, it.w].join(' '));
  }
  function match(it, toks){
    var h = hay(it);
    for (var i = 0; i < toks.length; i++){
      if (h.indexOf(toks[i]) === -1) return false;
    }
    return true;
  }
  function copied(btn){
    btn.classList.add('ok');
    btn.textContent = 'Copiado';
    setTimeout(function(){ btn.classList.remove('ok'); btn.textContent = 'Copiar'; }, 1600);
  }
  function copyText(text, btn){
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function(){ copied(btn); }).catch(function(){});
      return;
    }
    var ta = document.createElement('textarea');
    ta.value = text; ta.setAttribute('readonly','');
    ta.style.position = 'fixed'; ta.style.left = '-9999px';
    document.body.appendChild(ta); ta.select();
    try { if (document.execCommand('copy')) copied(btn); } catch (e) {}
    document.body.removeChild(ta);
  }
  /* Escapado real. La tabla anterior mapeaba cada caracter a si mismo
     ('&':'&', '<':'<', ...), asi que solo escapaba la comilla simple: un
     titular de feed con <img onerror=...> entraba intacto por innerHTML.
     Se usan codigos numericos para que las entidades no puedan volver a
     decodificarse al generar la plantilla. */
  function esc(s){
    return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){
      return { '&':'&#38;', '<':'&#60;', '>':'&#62;', '"':'&#34;', "'":'&#39;' }[c];
    });
  }
  function renderHits(items, query){
    hitsList.innerHTML = '';
    items.slice(0, 60).forEach(function(it){
      var row = document.createElement('div');
      row.className = 'hit';
      var url = it.u || ('d/' + it.d + '.html');
      var ficha = [it.t, it.w, it.u].filter(Boolean).join('\\n\\n');
      row.innerHTML =
        '<a class="dt" href="d/' + esc(it.d) + '.html">' + esc(it.d) + '</a>' +
        '<div>' +
          '<a class="t" href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">' + esc(it.t) + '</a>' +
          (it.w ? '<div class="w">' + esc(it.w) + '</div>' : '') +
          '<div class="meta">' + esc(it.s || '') + '</div>' +
        '</div>' +
        '<button type="button" class="copy-btn">Copiar</button>';
      row.querySelector('.copy-btn').addEventListener('click', function(ev){
        ev.preventDefault();
        copyText(ficha, ev.currentTarget);
      });
      hitsList.appendChild(row);
    });
    var n = items.length;
    hitsH.textContent = n === 0 ? 'Nada para «' + query + '»' :
      (n === 1 ? '1 señal' : (n > 60 ? '60 de ' + n + ' señales' : n + ' señales'));
    hitsBox.hidden = false;
    cal.hidden = true;
    if (months) months.hidden = true;
    none.hidden = n !== 0;
  }
  function filterDays(s){
    hitsBox.hidden = true;
    cal.hidden = false;
    if (months) months.hidden = false;
    var vis = 0;
    var needle = fold(s);
    rows.forEach(function(r){
      var ok = !needle || fold(r.getAttribute('data-q') || '').indexOf(needle) !== -1;
      r.style.display = ok ? '' : 'none';
      if (ok) vis++;
    });
    document.querySelectorAll('.month').forEach(function(h){
      var next = h.nextElementSibling;
      var any = false;
      while (next && !next.classList.contains('month')) {
        if (next.classList.contains('day') && next.style.display !== 'none') any = true;
        next = next.nextElementSibling;
      }
      h.style.display = any ? '' : 'none';
    });
    none.hidden = vis !== 0;
  }
  function apply(){
    var s = (q.value || '').trim();
    var toks = tokens(s);
    if (toks.length && index) {
      var found = [];
      for (var i = index.length - 1; i >= 0; i--) {
        if (match(index[i], toks)) found.push(index[i]);
      }
      renderHits(found, s);
      return;
    }
    filterDays(s);
  }
  function loadIndex(cb){
    if (index) { cb(); return; }
    if (loading) return;
    loading = true;
    fetch('search.json').then(function(r){ return r.json(); }).then(function(data){
      index = Array.isArray(data) ? data : [];
      loading = false;
      cb();
    }).catch(function(){
      loading = false;
      index = [];
      cb();
    });
  }
  q.addEventListener('input', function(){
    var s = (q.value || '').trim();
    if (tokens(s).length) loadIndex(apply);
    else apply();
  });
  var boot = new URLSearchParams(location.search).get('q');
  if (boot) {
    q.value = boot;
    loadIndex(apply);
  }
})();
</script>
</body>
</html>
""")


def _group_months(metas: list[dict]) -> list[dict]:
    buckets: dict[str, list] = defaultdict(list)
    labels: dict[str, str] = {}
    for m in metas:
        buckets[m["month_key"]].append(m)
        labels[m["month_key"]] = m["month_label"]
    months = []
    for key in sorted(buckets.keys(), reverse=True):
        days = sorted(buckets[key], key=lambda d: d["date"], reverse=True)
        months.append({
            "key": key,
            "label": labels[key],
            "short": labels[key][:3] + " " + key[:4],
            "days": days,
        })
    return months


def search_entries(snaps: list[dict]) -> list[dict]:
    """Índice compacto para búsqueda en cliente: título, so_what, fuente, fecha, url."""
    out = []
    for snap in snaps:
        date = snap.get("date") or ""
        for it in snap.get("items") or []:
            if not isinstance(it, dict):
                continue
            title = re.sub(r"\s+", " ", (it.get("title_es") or it.get("title") or "").strip())
            if not title:
                continue
            so = re.sub(r"\s+", " ", (it.get("so_what") or it.get("why") or "").strip())
            # El indice se pintaba con la URL cruda del feed, saltandose el
            # _safe_url() que ya usa el render: un <link>javascript:...</link>
            # acababa en un href pulsable. Aqui solo pasan http/https.
            raw_url = (it.get("url") or it.get("link") or "").strip()
            url = _safe_url(raw_url)
            if url == "#":
                url = ""
            out.append({
                "d": date,
                "t": title[:180],
                "s": (it.get("source") or "").strip()[:48],
                "u": url[:400],
                "w": so[:160],
            })
    return out


def write_archive(docs_dir: Path, *, write_days: bool = True) -> int:
    """Escribe docs/archivo.html, docs/search.json y (opcional) docs/d/YYYY-MM-DD.html."""
    docs_dir = Path(docs_dir)
    data_dir = docs_dir / "data"
    day_dir = docs_dir / "d"
    day_dir.mkdir(parents=True, exist_ok=True)

    paths = snapshot_paths(data_dir)
    snaps = [load_snapshot(p) for p in paths]
    metas = [meta_of(s) for s in snaps]
    dates = [m["date"] for m in metas]
    entries = search_entries(snaps)

    months = _group_months(metas)
    first = dates[0] if dates else "—"
    last = dates[-1] if dates else "—"
    html = ARCHIVO_TEMPLATE.render(
        n=len(metas),
        n_entries=len(entries),
        first=first,
        last=last,
        months=months,
        missing="6 may 2026" if "2026-05-06" not in dates else "ninguno",
    )
    (docs_dir / "archivo.html").write_text(html, encoding="utf-8")
    (docs_dir / "search.json").write_text(
        json.dumps(entries, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    if write_days:
        for i, snap in enumerate(snaps):
            prev_date = dates[i - 1] if i > 0 else ""
            next_date = dates[i + 1] if i + 1 < len(dates) else ""
            page = render_index(
                snap.get("items") or [],
                briefing=snap.get("briefing") or {},
                snapshot=snap,
                market={},
                nav="archivo",
                root="../",
                archive={
                    "prev": prev_date,
                    "next": next_date,
                },
            )
            (day_dir / f"{snap['date']}.html").write_text(page, encoding="utf-8")

    return len(snaps)
