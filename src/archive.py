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
from markupsafe import Markup

from src.brand import BASE_CSS as BRAND_CSS, HEAD as BRAND_HEAD, HTML_ATTRS, THEME_JS, bi, credits as brand_credits, header as brand_header, seo_head

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
    from src.render import strip_evidence_prefix
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
    text = strip_evidence_prefix(text)
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
    degraded = bool(snap.get("degraded"))
    n_shown = n_signal or len(items)
    if degraded:
        # Un dia degradado no tiene señales: son items que nadie filtro.
        n_label = "sin filtrar"
    else:
        n_label = "1 señal" if n_shown == 1 else f"{n_shown} señales"
    return {
        "date": date,
        "thesis": thesis_of(snap),
        "n_items": len(items),
        "n_signal": n_shown,
        "n_label": n_label,
        "n_label_en": "unfiltered" if degraded else ("1 signal" if n_shown == 1 else f"{n_shown} signals"),
        "thesis_en": re.sub(r"\s+", " ", str((snap.get("briefing") or {}).get("thesis_en") or "").strip())[:220],
        "activity_label": activity.get("label") or "",
        "activity_class": activity.get("class") or "quiet",
        "month_key": month_key,
        "month_label": month_label,
        "day_label": day_label,
        "degraded": bool(snap.get("degraded")),
    }


# La marca va como globales del entorno: cualquier render de la plantilla
# (tambien los tests) sale con cabecera y estilos.
ENV.globals.update(
    brand_head=Markup(BRAND_HEAD),
    brand_css=Markup(BRAND_CSS),
    brand_header=brand_header("archivo"),
    theme_js=Markup(THEME_JS),
    html_attrs=Markup(HTML_ATTRS),
    bi=bi,
    credits=brand_credits(),
    seo=seo_head("RADAR.AI · Archivo: todas las ediciones del radar", path="archivo.html"),
)

ARCHIVO_TEMPLATE = ENV.from_string("""
<!doctype html>
<html {{ html_attrs }}>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
{{ seo }}{{ brand_head }}<style>{{ brand_css }}
  .wrap{max-width:860px;margin:0 auto;padding:0 24px 80px}
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
  .day .n.deg{color:var(--amber)}
  .empty{padding:40px 10px;color:var(--dim);text-align:center}
  footer{margin-top:48px;padding-top:16px;border-top:1px solid var(--line);
         font-family:var(--mono);font-size:10px;color:var(--dimmer)}
  @media(max-width:640px){
    .wrap{padding:0 14px 60px}
    .day{grid-template-columns:84px 1fr;gap:8px}
    .day .n{grid-column:2;margin-top:-6px}
  }

  .wrap{max-width:900px;margin:0 auto;padding:28px 24px 80px}
  .lead p{color:var(--muted);font-size:17px;margin:0 0 20px}
  .toolbar input{background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow-sm);border-radius:0;
                 color:var(--text);padding:11px 12px;font:14px var(--f-mono)}
  .toolbar input:focus{outline:none;box-shadow:var(--shadow);background:var(--card)}
  .months a{font:600 11px var(--f-mono);text-transform:uppercase;color:var(--text);padding:5px 8px;border:2px solid var(--ink);
            border-radius:0;background:var(--card);box-shadow:var(--shadow-sm)}
  .months a:hover{background:rgba(204,255,0,.3)}
  .month{display:flex;align-items:center;gap:10px;font:700 13px/1.2 var(--f-mono);text-transform:uppercase;letter-spacing:.08em;margin:34px 0 10px}
  .month::before{content:"";width:12px;height:12px;background:var(--orange);border:2px solid var(--ink)}
  #cal,#hits{background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow);padding:0 14px}
  #hits{margin-bottom:24px;padding:10px 14px}
  #cal{background:transparent;border:0;box-shadow:none;padding:0}
  .day,.hit{border-bottom:1px dashed var(--line)}
  .day{background:var(--card);border:2px solid var(--ink);border-top-width:0;padding:11px 12px}
  .month + .day{border-top-width:2px}
  .day:hover,.hit:hover{background:rgba(204,255,0,.18)}
  .day .dt{color:var(--orange-ink);font-weight:700}
  .day .th{color:var(--text)}
  .day .n{color:var(--muted)}
  .day .n.deg{color:#121211;background:#FBBF24;border:1px solid var(--ink);padding:2px 5px;font-weight:700;text-transform:uppercase}
  .hit .t:hover{color:inherit;text-decoration:underline}
  .copy-btn{border:2px solid var(--ink);border-radius:0;color:var(--text);background:var(--card);font:700 10.5px var(--f-mono)}
  .copy-btn:hover{background:rgba(204,255,0,.3);color:var(--text)}
  .copy-btn.ok{background:#34D399;color:#121211}
  footer{border-top:3px solid var(--ink);font:400 12px var(--f-mono);color:var(--muted)}
</style>
</head>
<body>
{{ brand_header }}
<div class="wrap">
  <div class="lead">
    <span class="kicker">{{ first }} – {{ last }}</span>
    <h1 class="page-h1">{{ bi("Archivo","Archive") }}</h1>
    <p>{{ n }} {{ bi("días","days") }} · {{ first }} – {{ last }}. {{ bi("Cada entrada es el radar de ese día, no un recorte.","Each entry is that day's full radar, not an excerpt.") }}</p>
  </div>
  <div class="toolbar">
    <input id="q" type="search" aria-label="Search archive / Buscar en el archivo" placeholder="NVIDIA, agentes, 2026-08-22…" autocomplete="off"/>
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
    <span class="th">{{ bi(d.thesis or "Sin tesis — heurística", d.thesis_en) }}</span>
    <span class="n{% if d.degraded %} deg{% endif %}">{{ bi(d.n_label, d.n_label_en) }}</span>
  </a>
  {% endfor %}
  {% endfor %}
  </div>
  <div class="empty" id="none" hidden>{{ bi("Nada coincide.","No matches.") }}</div>
  {{ credits }}
  <footer>{{ n }} snapshots · {{ n_entries }} {{ bi("señales indexadas","indexed signals") }} · {{ bi("falta","missing") }} {{ missing }}</footer>
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

  function isEn(){
    return document.documentElement.getAttribute('data-lang') === 'en';
  }
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
    btn.textContent = isEn() ? 'Copied' : 'Copiado';
    setTimeout(function(){
      btn.classList.remove('ok');
      btn.textContent = isEn() ? 'Copy' : 'Copiar';
    }, 1600);
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
    var en = isEn();
    var copyLbl = en ? 'Copy' : 'Copiar';
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
        '<button type="button" class="copy-btn">' + copyLbl + '</button>';
      row.querySelector('.copy-btn').addEventListener('click', function(ev){
        ev.preventDefault();
        copyText(ficha, ev.currentTarget);
      });
      hitsList.appendChild(row);
    });
    var n = items.length;
    if (en) {
      hitsH.textContent = n === 0 ? 'Nothing for "' + query + '"' :
        (n === 1 ? '1 signal' : (n > 60 ? '60 of ' + n + ' signals' : n + ' signals'));
    } else {
      hitsH.textContent = n === 0 ? 'Nada para «' + query + '»' :
        (n === 1 ? '1 señal' : (n > 60 ? '60 de ' + n + ' señales' : n + ' señales'));
    }
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
{{ theme_js }}
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
    # Los dias en que fallo el analisis no se publican en el archivo: no pasaron
    # el filtro de relevancia. El snapshot se conserva en data/ para la memoria.
    for s in snaps:
        if s.get("degraded") and s.get("date"):
            (docs_dir / "d" / f"{s['date']}.html").unlink(missing_ok=True)
    snaps = [s for s in snaps if not s.get("degraded")]
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
    # Para buscadores: mapa del sitio con las tres paginas y cada edicion.
    from src.brand import SITE_URL
    urls = [("", last), ("weekly.html", last), ("archivo.html", last)] + [(f"d/{d}.html", d) for d in sorted(dates, reverse=True)]
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sitemap += [f"<url><loc>{SITE_URL}{path}</loc><lastmod>{mod}</lastmod></url>" for path, mod in urls]
    sitemap.append("</urlset>")
    (docs_dir / "sitemap.xml").write_text("\n".join(sitemap) + "\n", encoding="utf-8")
    (docs_dir / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}sitemap.xml\n", encoding="utf-8")

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
