"""Render del radar diario estilo Perplexity Discover.

Direccion visual: carbon + turquesa de Perplexity (#191a1a / #20b8cd), tipografia
Space Grotesk para titulares e Inter para cuerpo, y la sena de identidad del feed
Discover: rejilla de cards con imagen 16:9 arriba y titular debajo, con tabs de
tema filtrables en cliente. La capa de memoria y el mercado viven en la sidebar.
"""

from collections import Counter
from urllib.parse import urlparse
import re

from jinja2 import Environment, select_autoescape
from markupsafe import Markup

from src.brand import BASE_CSS as BRAND_CSS, HEAD as BRAND_HEAD, HTML_ATTRS, THEME_JS, bi, credits as brand_credits, header as brand_header, seo_head
from src.evidence import UNVERIFIED, canonical_url, measurement_context, source_url
from src.config import LEAD_SLOT_COUNT, demote_repeats_from_lead, radar_today_str


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


_EVIDENCE_PREFIX_RE = re.compile(
    r"^(?:Confirmado|Confirmed|Según la fuente|Reported|Inferencia|Inference|"
    r"Hipótesis|Hypothesis|Sin verificar|Unverified|Señal destacada|Featured signal)\s*[·:\-–—]\s*",
    re.I,
)

EVIDENCE_BADGES = {
    "confirmed": ("Confirmado", "Confirmed", "Confirmado por fuente primaria", "Confirmed by primary source"),
    "reported": ("Según la fuente", "Reported", "Reportado por medio externo", "Reported by external outlet"),
    "inference": ("Inferencia", "Inference", "Lectura editorial basada en la fuente", "Editorial reading based on the source"),
    "speculation": ("Hipótesis", "Hypothesis", "Hipótesis, rumor o anuncio en curso", "Hypothesis, rumor, or pending announcement"),
    "unverified": ("Sin verificar", "Unverified", "Sin evidencia verificable en la fuente", "No verifiable evidence in the source"),
}

_PREFIX_TO_KIND = {
    "confirmado": "confirmed", "confirmed": "confirmed",
    "según la fuente": "reported", "reported": "reported",
    "inferencia": "inference", "inference": "inference",
    "hipótesis": "speculation", "hypothesis": "speculation",
    "sin verificar": "unverified", "unverified": "unverified",
}


def strip_evidence_prefix(text: str) -> str:
    """Elimina prefijos repetitivos de certeza del texto visible (pasan a pastilla discreta)."""
    cleaned = clean_text(text)
    while cleaned:
        m = _EVIDENCE_PREFIX_RE.match(cleaned)
        if not m:
            break
        cleaned = cleaned[m.end():].lstrip()
    return cleaned


def evidence_badge(item: dict) -> dict | None:
    """Devuelve metadatos para la pastilla informativa discreta de certeza, si existe."""
    kind = (item.get("evidence_kind") or "").strip().lower()
    if kind not in EVIDENCE_BADGES:
        for field in ("title_es", "title_en"):
            m = _EVIDENCE_PREFIX_RE.match(clean_text(item.get(field) or ""))
            if m:
                raw_lbl = re.sub(r"\s*[·:\-–—]\s*$", "", m.group(0)).strip().lower()
                kind = _PREFIX_TO_KIND.get(raw_lbl, "")
                if kind in EVIDENCE_BADGES:
                    break
    if kind not in EVIDENCE_BADGES:
        return None
    es, en, tip_es, tip_en = EVIDENCE_BADGES[kind]
    return {"kind": kind, "es": es, "en": en, "tip_es": tip_es, "tip_en": tip_en}


def clamp_headline(text: str, limit: int = 160) -> str:
    """Acorta titulares desmesurados (p. ej. hilos de X) en fin de frase o palabra."""
    raw = re.sub(r"\s+", " ", (text or "").strip())
    if len(raw) <= limit:
        return raw
    # Si hay un final de frase natural entre 55 y `limit` caracteres, cortamos ahi.
    sentence_ends = [m.end() for m in re.finditer(r"[.!?](?:\s|$)", raw[: limit + 1])]
    good_ends = [pos for pos in sentence_ends if 55 <= pos <= limit + 1]
    if good_ends:
        return raw[: good_ends[-1]].strip()
    cut = raw[: max(0, limit - 1)]
    if " " in cut[40:]:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:-–—") + "…"


def _dedup_subtitle(title: str, subtitle: str, fallback_body: str = "") -> str:
    """Evita que el subtitulo repita el arranque literal del titular (tipico en posts de X)."""
    sub = re.sub(r"\s+", " ", (subtitle or "").strip())
    if not sub:
        return ""
    probe = re.sub(r"\s+", " ", (title or "").strip()).rstrip("….").strip()
    if len(probe) < 24:
        return sub

    def _norm(s: str) -> str:
        return s.lower().replace("’", "'").replace("“", '"').replace("”", '"')

    probe_n = _norm(probe)
    if not _norm(sub).startswith(probe_n):
        return sub

    source = sub
    fb = re.sub(r"\s+", " ", (fallback_body or "").strip())
    if fb and len(fb) > len(sub) and _norm(fb).startswith(probe_n):
        source = fb
    rest = source[len(probe):].lstrip(" .!?…,:;–—-\"'")
    return rest if len(rest) >= 20 else ""


def display_title(item: dict) -> str:
    """Prefiere el titular reescrito por el LLM, limpio de prefijos repetitivos de evidencia."""
    t = strip_evidence_prefix(item.get("title_es") or "")
    if not t:
        t = strip_evidence_prefix(item.get("title") or "")
    return clamp_headline(t) or "(sin titulo)"


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
    "zhipu": "z.ai",
    "minimax": "minimax.io",
    "moonshot": "moonshot.cn",
    "chinatalk": "chinatalk.media",
    "stratechery": "stratechery.com",
    "fabricated knowledge": "fabricatedknowledge.com",
    "semianalysis": "semianalysis.com",
    "semiwiki": "semiwiki.com",
    "nvidia": "nvidia.com",
    "tsmc": "tsmc.com",
    "asml": "asml.com",
    "microsoft": "microsoft.com",
    "amazon": "amazon.com",
    "aws": "aws.amazon.com",
    "apple": "apple.com",
    "alibaba": "alibabacloud.com",
    "epoch": "epoch.ai",
    "interconnects": "interconnects.ai",
    "import ai": "importai.substack.com",
    "latent space": "latent.space",
    "simon willison": "simonwillison.net",
    "hugging face": "huggingface.co",
    "arc prize": "arcprize.org",
    "artificial analysis": "artificialanalysis.ai",
    "openrouter": "openrouter.ai",
    "supermicro": "supermicro.com",
    "reuters": "reuters.com",
    "bloomberg": "bloomberg.com",
    "business insider": "businessinsider.com",
    "yahoo finance": "finance.yahoo.com",
    "venturebeat": "venturebeat.com",
    "the verge": "theverge.com",
    "techcrunch": "techcrunch.com",
    "ars technica": "arstechnica.com",
    "techradar": "techradar.com",
}


def source_label(source: str) -> str:
    raw = (source or "Fuente").strip()
    if raw.startswith("X @"):
        return raw.replace("X @", "@", 1)
    return raw.replace(" (AI)", "").replace(" (alto voltaje)", "")


def source_logo_url(source: str, url: str = "") -> str:
    src = (source or "").strip().lower()
    for key, domain in SOURCE_DOMAIN_HINTS.items():
        if key in src:
            return f"https://www.google.com/s2/favicons?domain={domain}&sz=64"
    host = urlparse(url or "").netloc.replace("www.", "")
    return f"https://www.google.com/s2/favicons?domain={host or 'github.com'}&sz=64"


def item_fallback_image(item: dict, lang: str = "es") -> str:
    """Portada generada (data URI) para un item sin imagen o con la imagen caida.

    Lleva tema, entidad protagonista (si existe), puntuacion y fuente: el titular
    ya va justo debajo, en la card. El dibujo lo hace src/cover.py.
    """
    from src.cover import cover_data_uri

    theme_key = (item.get("strategic_theme") or item.get("primary") or "other").strip() or "other"
    seed = f"{item.get('title') or item.get('title_es') or ''}|{item.get('url') or item.get('link') or ''}"
    label = THEME_LABELS_EN.get(theme_key, "Other signals") if lang == "en" else human_theme(theme_key)
    ents = item_entities(item, limit=1)
    entity = ents[0] if ents else ""
    sc = score_value(item)
    return cover_data_uri(theme_key, label, source_label(item.get("source", "")), seed, entity=entity, score=sc)


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


THEME_LABELS_EN = {
    "frontier_capability": "Frontier capability", "agents_automation": "Agents",
    "compute_chips_dc": "Compute & chips", "model_economics": "Model economics",
    "model_economics_pricing": "Model economics", "china_stack": "China stack",
    "geopolitics_power": "Geopolitics", "other": "Other signals", "misc": "Other signals",
}
ACTIVITY_EN = {"ALERTA": "ALERT", "ACTIVO": "ACTIVE", "TRANQUILO": "QUIET",
               "SIN SEÑAL": "NO SIGNAL", "SIN FILTRAR": "UNFILTERED"}


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


def score_tier(score: int) -> str:
    if score >= 95:
        return "s-95"
    if score >= 88:
        return "s-88"
    if score >= 80:
        return "s-80"
    if score >= 70:
        return "s-70"
    return "s-low"


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
ENV.globals["bi"] = bi

TEMPLATE = ENV.from_string("""
{%- macro watch_text(it) -%}
  {%- if it.watch_anchor -%}<a class="watch-link" href="#{{ it.watch_anchor }}">{{ bi("Ver hito","View milestone") }}</a>
  {%- else -%}{{ bi(it.watch_next, it.watch_next_en) }}{%- endif -%}
{%- endmacro %}
{%- macro measurement(it) -%}
  {% if it.measurement -%}
  <details class="metric-context"><summary>{{ bi("Contexto de la medición","Measurement context") }}</summary>
    <blockquote>{{ bi(it.measurement.es or ("Cita original: " ~ it.measurement.quote), it.measurement.quote) }}</blockquote>
    <a href="{{ it.measurement.url|safe_url }}" target="_blank" rel="noopener noreferrer">{{ it.source_label }} ↗</a>
  </details>
  {%- endif %}
{%- endmacro %}
{%- macro ev_pill(it) -%}
  {% if it.ev -%}<span class="ev-pill ev-{{ it.ev.kind }}" title="{{ it.ev.tip_es }}">{{ bi(it.ev.es, it.ev.en) }}</span>{%- endif %}
{%- endmacro %}
<!doctype html>
<html {{ html_attrs }}>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
{{ seo }}{{ brand_head }}<script>
  // Va en <head> para estar escuchando antes de que se pinte la primera imagen.
  // Si falla la foto del Hero, la portada pasa limpiamente a modo Dossier tipografico
  // en vez de enseñar un rectangulo gigante de relleno; en las cards usa la portada SVG.
  document.addEventListener('error', function(ev){
    var t = ev.target;
    if (!t || t.tagName !== 'IMG') return;
    if (t.classList.contains('hero-img')) {
      var lead = t.closest && t.closest('.lead');
      if (lead) {
        lead.classList.remove('lead-photo');
        lead.classList.add('lead-dossier');
        var media = t.closest('.lead-media');
        if (media) media.remove();
        return;
      }
    }
    var fb = t.getAttribute('data-fb');
    if (fb) {
      // La portada generada lleva texto: se pone una por idioma.
      var en = t.getAttribute('data-fb-en');
      t.removeAttribute('data-fb'); t.removeAttribute('data-fb-en'); t.removeAttribute('loading');
      if (en) { var c = t.cloneNode(false); c.src = en; c.classList.add('l-en'); t.classList.add('l-es'); t.parentNode.insertBefore(c, t.nextSibling); }
      t.src = fb;
    }
    else { t.style.visibility = 'hidden'; }
  }, true);
</script>
<style>{{ brand_css }}
  .wrap{max-width:1580px;margin:0 auto;padding:18px 24px 80px}
  .stale{font:700 10.5px/1 var(--f-mono);text-transform:uppercase;color:#121211;background:#FBBF24;
         border:1px solid var(--ink);padding:3px 7px}
  .arch-bar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:0 0 18px;padding:10px 14px;
            background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow-sm);font:600 12.5px var(--f-mono);text-transform:uppercase}
  .arch-bar a{color:var(--orange-ink);text-decoration:underline;text-underline-offset:3px}
  .arch-bar .here{background:var(--lime);color:#121211;padding:2px 6px;border:1px solid var(--ink)}

  /* -- Tesis -- */
  .thesis{padding:0 0 22px}
  .thesis .page-h1{margin-top:8px}
  .thesis .tz{font:700 clamp(19px,2.2vw,26px)/1.3 var(--f-head);letter-spacing:-.015em;max-width:64ch;margin:0}
  .notice{margin:0 0 16px;padding:14px 18px;border:2px dashed var(--ink);background:var(--card);font-size:14.5px;line-height:1.55}
  .notice.warn{border-style:solid;box-shadow:inset 6px 0 0 #FBBF24}

  /* -- Tabs de tema -- */
  .tabs{display:flex;gap:8px;flex-wrap:wrap;padding:0 0 18px}
  .tab{appearance:none;margin:0;color:var(--text);font:600 12px/1.2 var(--f-mono);text-transform:uppercase;padding:7px 11px;cursor:pointer;user-select:none;
       border:2px solid var(--ink);background:var(--card);box-shadow:var(--shadow-sm);transition:transform .08s,box-shadow .08s}
  .tab:hover{background:rgba(204,255,0,.3)}
  .tab:active{transform:translate(2px,2px);box-shadow:none}
  .tab.on{background:var(--lime);color:#121211}
  .tab-new.on{background:#34D399;color:#121211}
  .tab .n{font-weight:700;color:var(--orange-ink);margin-left:6px}
  .tab.on .n{color:#121211}
  .below.filter-empty,.ctx-block.filter-empty{display:none}

  /* -- Banda de telemetria (Pulso + Mercados) debajo de la portada -- */
  .telemetry-band{margin-top:26px;display:grid;grid-template-columns:minmax(0,1fr);gap:18px;width:100%;max-width:100%}
  .telemetry-band>*{min-width:0;max-width:100%}
  .deck.filtered .telemetry-band{display:none}
  .ticker{margin:0;min-width:0;max-width:100%;overflow:hidden;background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow);padding:10px 14px 12px}
  .ticker-h{display:flex;justify-content:space-between;gap:12px;align-items:center;font:400 10.5px var(--f-mono);color:var(--muted);text-transform:uppercase}
  .ticker-h strong{display:flex;align-items:center;gap:8px;color:var(--text);font-weight:700;letter-spacing:.08em}
  .ticker-h strong::before{content:"";width:10px;height:10px;background:var(--orange);border:2px solid var(--ink)}
  .ticker-q{display:flex;gap:8px;padding-right:8px}
  .tq{flex:0 0 210px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:2px 6px;align-items:center;padding:8px 10px;border:1px solid var(--ink);background:var(--card-2);min-width:0;color:inherit;text-decoration:none;transition:border-color .12s,background-color .12s,transform .12s}
  a.tq:hover{border-color:var(--orange);background:var(--card);transform:translateY(-1px)}
  a.tq:focus-visible{outline:2px solid var(--orange);outline-offset:-2px}
  .tq-n{grid-column:1/-1;display:flex;justify-content:space-between;align-items:center;gap:6px;font:600 10.5px var(--f-mono);color:var(--muted);text-transform:uppercase}
  a.tq .tq-n::after{content:"↗";font-size:10px;opacity:.45;transition:opacity .12s,color .12s}
  a.tq:hover .tq-n::after{opacity:1;color:var(--orange-ink)}
  .tq-p{font:700 clamp(14px,1.25vw,18px) var(--f-mono);white-space:nowrap;font-variant-numeric:tabular-nums}
  .tq .spark{grid-column:1/-1;height:20px}

  .ticker-view{overflow:hidden;margin-top:10px;max-width:100%}
  .ticker-track{display:flex;width:max-content;animation:tick calc(var(--n) * 5s) linear infinite}
  .ticker-view:hover .ticker-track{animation-play-state:paused}
  @keyframes tick{to{transform:translateX(-50%)}}
  @media (prefers-reduced-motion: reduce){.ticker-track{animation:none}.ticker-view{overflow-x:auto}}

  .pulse{display:grid;grid-template-columns:minmax(230px,300px) minmax(0,1fr);gap:22px;align-items:end;margin:0;min-width:0;max-width:100%;padding:14px 16px;
         background:var(--asphalt);color:#E8E7E1;border:2px solid var(--ink);box-shadow:var(--shadow)}
  .pulse-hist{min-width:0}
  .pulse .kicker{color:var(--lime)}
  .pulse-num{display:flex;align-items:baseline;gap:6px;margin:4px 0 8px}
  .pulse-num strong{font:700 58px/.9 var(--f-head);letter-spacing:-.04em;color:#fff}
  .pulse-num>span{font:700 14px var(--f-mono);color:#9C9B95}
  .pulse-num .pulse-state{margin-left:8px;padding:3px 6px;font-size:10.5px;text-transform:uppercase;color:#121211;background:#9C9B95}
  .pulse-state.s-alert{background:var(--orange)} .pulse-state.s-active{background:var(--lime)}
  .pulse-bar{height:12px;border:2px solid #E8E7E1;background:#1E1E1C}
  .pulse-bar i{display:block;height:100%;background:linear-gradient(90deg,var(--lime),var(--orange))}
  .pulse-cols{display:flex;align-items:flex-end;gap:3px;height:74px}
  .pulse-cols i{flex:1;min-width:3px;background:#5B5A55}
  .pulse-cols i.now{background:var(--lime)}
  .pulse-cols i:hover{background:var(--orange)}
  .pulse-note{font:400 11px/1.4 var(--f-mono);color:#9C9B95;margin-top:8px}


  /* -- Portada a 3 columnas: Editorial (izq) · Hero #01 (centro) · Contexto + Qué vigilar (der) -- */
  .opening{display:grid;grid-template-columns:minmax(295px,330px) minmax(0,1.85fr) minmax(310px,345px);gap:24px;align-items:stretch}
  .opening[data-cols="2"]{grid-template-columns:320px minmax(0,1fr)}
  .deck.filtered{display:flex;flex-direction:column}
  .deck.filtered .opening{order:2;display:block;margin-top:26px}
  .deck.filtered .opening.filter-empty{display:none}
  .deck.filtered .opening .rail,.deck.filtered .opening .lead,.deck.filtered .opening .watch-rail{display:none}
  .deck.filtered .opening .side-rail{padding:0;background:transparent;border:0;box-shadow:none;height:auto}

  .rail,.side-rail{display:flex;flex-direction:column;height:100%;min-width:0;background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow);padding:18px 20px}
  .rail-h{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:0 0 12px;padding:0 0 8px;border-bottom:2px solid var(--ink);
          font:700 11.5px/1.2 var(--f-mono);text-transform:uppercase;letter-spacing:.08em}
  .rail-h>span:first-child{display:flex;align-items:center;gap:8px}
  .rail-h>span:first-child::before{content:"";width:10px;height:10px;background:var(--orange);border:2px solid var(--ink);flex:0 0 auto}
  .watch-rail .rail-h>span:first-child::before{background:var(--lime)}
  .rail-h .lbl{font:400 10.5px var(--f-mono);color:var(--muted);letter-spacing:.04em;white-space:nowrap}
  .rail-title{font:700 23px/1.1 var(--f-head);text-transform:uppercase;letter-spacing:-.028em;margin:2px 0 10px}
  .rail-thesis{font:500 15px/1.52 var(--f-head);margin:0 0 18px}
  .keys{margin:0 0 14px;padding:0;list-style:none;counter-reset:k}
  .keys li{counter-increment:k;display:grid;grid-template-columns:25px 1fr;gap:8px;padding:0 0 10px;margin-bottom:10px;border-bottom:1px dashed var(--line);font-size:14px;line-height:1.48}
  .keys li:last-child{margin-bottom:0;border-bottom:none;padding-bottom:0}
  .keys li::before{content:counter(k,decimal-leading-zero);font:700 11.5px/1.6 var(--f-mono);color:var(--orange-ink)}
  .rail-foot{margin-top:auto;padding-top:14px;display:flex;flex-direction:column;gap:10px}
  .figures{border-top:2px solid var(--ink);padding-top:12px;display:flex;flex-direction:column;gap:8px}
  .fig-row{display:flex;align-items:baseline;justify-content:space-between;gap:8px;flex-wrap:wrap}
  .fig-count{font:700 24px/1 var(--f-head);letter-spacing:-.03em}
  .fig-note{font:400 11px/1.35 var(--f-mono);color:var(--muted)}
  .figures .ents{margin-top:0;gap:6px}
  .figures .ent{font-size:11px;padding:3px 6px}

  /* Columna derecha: Contexto (lectura rapida) + Que vigilar (seguimiento) */
  .side-rail{gap:20px}
  .side-rail .ctx-block{margin:0}
  .side-rail .ctx{border-top:0;background:transparent;counter-reset:cx}
  .side-rail .cx{counter-increment:cx;display:grid;grid-template-columns:25px minmax(0,1fr);gap:8px;align-items:start;padding:0 0 12px;margin-bottom:12px;border-bottom:1px dashed var(--line)}
  .side-rail .cx:last-child{margin-bottom:0;padding-bottom:0;border-bottom:none}
  .side-rail .cx::before{content:counter(cx,decimal-leading-zero);font:700 11.5px/1.45 var(--f-mono);color:var(--orange-ink)}
  .side-rail .cx-body{display:flex;flex-direction:column;gap:4px;min-width:0}
  .side-rail .cx-theme{font:700 10.5px/1.2 var(--f-mono);text-transform:uppercase;letter-spacing:.06em;color:var(--orange-ink)}
  .side-rail .cx-t{margin:0;font:700 15px/1.34 var(--f-head);letter-spacing:-.012em;max-width:none;
                   display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}
  .side-rail .cx .src{font-size:11px;gap:6px;margin-top:2px}
  .side-rail .cx .src img{width:15px;height:15px}
  .side-rail .metric-context{margin:.45rem 0 0;font-size:.84rem}
  .side-rail .metric-context summary{padding:.2rem .65rem;font-size:.8rem}
  .deck.filtered .watch-standalone{display:none}
  .side-rail .watch-agenda{border-top:0;background:transparent}
  .side-rail .watch-row{display:flex;flex-direction:column;gap:5px;padding:10px 0 10px 12px;border-bottom:1px dashed var(--line);border-left:3px solid var(--lime)}
  .side-rail .watch-row:first-child{padding-top:3px}
  .side-rail .watch-row:last-child{border-bottom:none;padding-bottom:0}
  .side-rail .watch-row p{font:500 14px/1.46 var(--f-head);max-width:none;margin:0}
  .side-rail .watch-row .src{font-size:11px;line-height:1.35}
  .side-rail [id^="watch-point-"]:target{background:rgba(255,87,34,.08);border-left-color:var(--orange);box-shadow:none;padding-right:6px}
  .deck.filtered .side-rail .ctx{border-top:2px solid var(--ink);background:var(--card)}
  .deck.filtered .side-rail .cx{grid-template-columns:minmax(0,1fr);gap:6px;padding:14px 16px;margin-bottom:0;border-bottom:1px solid var(--line)}
  .deck.filtered .side-rail .cx::before{display:none}
  .deck.filtered .side-rail .cx-t{font:600 16px/1.45 var(--f-head)}

  .lead{position:relative;display:flex;flex-direction:column;height:100%;min-width:0;background:var(--card);border:2px solid var(--ink);border-top:5px solid var(--lead-accent,var(--orange));
        box-shadow:var(--shadow);overflow:hidden;transition:transform .12s,box-shadow .12s}
  .lead:hover{transform:translate(-2px,-2px);box-shadow:6px 6px 0 var(--ink)}
  .lead-wm{display:none;position:absolute;top:0;right:0;width:64%;height:100%;opacity:.36;pointer-events:none;z-index:1;
           -webkit-mask-image:linear-gradient(245deg,rgba(0,0,0,.95) 0%,rgba(0,0,0,.35) 56%,transparent 88%);
           mask-image:linear-gradient(245deg,rgba(0,0,0,.95) 0%,rgba(0,0,0,.35) 56%,transparent 88%)}
  .lead-wm svg{width:100%;height:100%;display:block}
  .lead-media{position:relative;display:block;overflow:hidden;background:var(--asphalt);border-bottom:2px solid var(--ink)}
  .lead-media::after{content:"";position:absolute;inset:0;pointer-events:none;
                     background:linear-gradient(180deg,rgba(15,15,14,.55) 0%,rgba(15,15,14,0) 38%,rgba(15,15,14,.32) 100%)}
  .lead-media .hero-img{display:block;width:100%;aspect-ratio:16/9;max-height:360px;object-fit:cover;border-bottom:0;transition:transform .35s ease}
  .lead-media:hover .hero-img{transform:scale(1.02)}
  .lead-media-bar{position:absolute;top:14px;left:16px;right:16px;z-index:2;display:flex;align-items:center;gap:8px;flex-wrap:wrap;pointer-events:none}
  .lead-media-bar .tag{background:var(--lead-accent,var(--orange));color:#121211;border:2px solid #121211;box-shadow:2px 2px 0 rgba(18,18,17,.65)}
  .lead-media-bar .score{font-size:12.5px;padding:5px 9px}
  .lead-body{position:relative;z-index:2;flex:1;display:flex;flex-direction:column;padding:22px 26px 22px}
  .lead-top{display:none;align-items:center;gap:8px;flex-wrap:wrap;margin:0 0 18px}
  .lead-top .tag{background:var(--lead-accent,var(--orange));color:#121211}
  .lead-top .score{font-size:12.5px;padding:5px 9px}
  .lead .hero-title{font:700 clamp(26px,2.35vw,38px)/1.08 var(--f-head);letter-spacing:-.032em;margin:0 0 14px;
                    display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}
  .lead .sw{font-size:clamp(15.5px,1.15vw,17.5px);line-height:1.55;color:var(--muted);margin:0 0 18px;max-width:66ch}

  .lead-intel{display:grid;gap:12px;margin:0 0 16px}
  @media(min-width:740px){.lead-intel.two{grid-template-columns:1fr 1fr;gap:14px}}
  .intel-box{padding:12px 15px;background:var(--card-2);border:1.5px solid var(--line);display:flex;flex-direction:column;gap:6px}
  .intel-box.pw{border-left:3.5px solid var(--orange)}
  .intel-box.wn{border-left:3.5px solid var(--lime)}
  .intel-k{display:inline-flex;align-self:flex-start;font:700 10.5px/1 var(--f-mono);text-transform:uppercase;letter-spacing:.06em;
           padding:3px 6px;border:1px solid var(--ink)}
  .intel-box.pw .intel-k{background:var(--orange);color:#121211}
  .intel-box.wn .intel-k{background:var(--lime);color:#121211}
  .intel-v{font-size:14px;line-height:1.48}

  .lead-foot{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-top:auto;padding-top:16px;border-top:1px dashed var(--line)}
  .lead-foot-l{display:flex;align-items:center;gap:10px;flex-wrap:wrap;min-width:0}
  .lead-foot-l .ents{margin-top:0}
  .lead-cta{display:inline-flex;align-items:center;gap:7px;font:700 12px/1 var(--f-mono);text-transform:uppercase;letter-spacing:.04em;
            padding:10px 15px;background:var(--lime);color:#121211;border:2px solid var(--ink);box-shadow:var(--shadow-sm);
            transition:transform .08s,box-shadow .08s;white-space:nowrap}
  .lead-cta:hover{transform:translate(-1px,-1px);box-shadow:3px 3px 0 var(--ink)}

  /* Modo Dossier tipografico (cuando la noticia #1 no tiene foto real o la remota falla) */
  .lead.lead-dossier{background:
      radial-gradient(circle at 82% 24%,color-mix(in srgb,var(--lead-accent,#FF5722) 22%,transparent),transparent 58%),
      linear-gradient(rgba(232,231,225,.05) 1px,transparent 1px),
      linear-gradient(90deg,rgba(232,231,225,.05) 1px,transparent 1px),
      #0F0F0E;
      background-size:100% 100%,26px 26px,26px 26px,100% 100%;
      color:#F4F3EF;border-color:var(--ink)}
  .lead.lead-dossier .lead-wm{display:block}
  .lead.lead-dossier .lead-media{display:none}
  .lead.lead-dossier .lead-top{display:flex}
  .lead.lead-dossier .lead-body{padding:28px 30px 24px}
  .lead.lead-dossier .lead-top .tag{border-color:#E8E7E1}
  .lead.lead-dossier .lead-top .badge-new{border-color:#E8E7E1}
  .lead.lead-dossier .hero-title{font-size:clamp(30px,3vw,46px);line-height:1.05;color:#FFFFFF;max-width:24ch;margin-bottom:18px}
  .lead.lead-dossier .hero-title a:hover{text-decoration-color:var(--lead-accent,var(--lime))}
  .lead.lead-dossier .sw{color:#D4D3CC;font-size:clamp(16px,1.2vw,18px);line-height:1.55;margin-bottom:24px;max-width:58ch}
  .lead.lead-dossier .metric-context blockquote{border-left-color:#44443E;color:#D4D3CC}
  .lead.lead-dossier .metric-context a{color:var(--lime)}
  .lead.lead-dossier .lead-intel{margin-top:auto;margin-bottom:0}
  .lead.lead-dossier .intel-box{background:rgba(20,20,18,.9);border-color:#34342F;color:#ECEBE5;padding:14px 16px}
  .lead.lead-dossier .intel-box.pw{border-left-color:var(--orange)}
  .lead.lead-dossier .intel-box.wn{border-left-color:var(--lime)}
  .lead.lead-dossier .intel-k{border-color:#121211}
  .lead.lead-dossier .also{margin-top:14px}
  .lead.lead-dossier .lead-foot{border-top-color:#34342F}
  .lead.lead-dossier .lead-intel~.lead-foot{margin-top:16px}
  .lead.lead-dossier .src{color:#D6D5CE}
  .lead.lead-dossier .src img{border-color:#44443E}
  .lead.lead-dossier .ent{background:#1D1D1A;border-color:#474740;color:#E8E7E1}
  .lead.lead-dossier .also{color:#9C9B95}
  .lead.lead-dossier .also a,.lead.lead-dossier .also span{color:#E8E7E1}
  .lead.lead-dossier .lead-cta{border-color:#E8E7E1;box-shadow:3px 3px 0 rgba(232,231,225,.28)}
  .lead.lead-dossier .lead-cta:hover{background:#FFFFFF;box-shadow:4px 4px 0 var(--lead-accent,var(--orange))}

  .below{margin-top:30px;padding-top:24px;border-top:3px solid var(--ink)}
  .below .section-h{margin:0 0 16px}
  .below .grid{display:flex;flex-wrap:wrap;--card-width:calc((100% - 44px)/3)}
  .below .card{flex:1 1 var(--card-width);min-width:0}
  .deck.filtered .from-archive{display:none}
  .deck:not(.filtered) .dup,.deck:not(.filtered) .h-filtered,.deck.filtered .h-all{display:none}
  .deck:not(.filtered) .below.no-rest{display:none}
  .deck.filtered .below{order:1;margin-top:0;padding-top:0;border-top:0}


  /* -- Hero y cards: bordes de tinta y sombra dura -- */
  .hero,.card{background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow);transition:transform .1s,box-shadow .1s}
  .hero{margin-bottom:22px}
  .hero:hover,.card:hover{transform:translate(-2px,-2px);box-shadow:6px 6px 0 var(--ink)}
  .hero-img,.card-img{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;background:var(--asphalt);border-bottom:2px solid var(--ink)}
  .hero-body{padding:18px 20px 20px}
  .meta-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px}
  .src{display:inline-flex;align-items:center;gap:7px;font:600 11.5px var(--f-mono);color:var(--muted);text-transform:uppercase}
  .src img{width:18px;height:18px;padding:1px;background:var(--logo-bg);border:1px solid var(--line);flex-shrink:0}
  .tag,.badge-new,.multi{display:inline-block;font:700 10.5px/1 var(--f-mono);text-transform:uppercase;padding:4px 6px;
       border:2px solid var(--ink);background:var(--card-2);flex-shrink:0}
  .tag{background:var(--orange);color:#121211}
  .badge-new{background:var(--lime);color:#121211}
  .ev-pill{display:inline-flex;align-items:center;gap:4px;font:600 9.5px/1 var(--f-mono);text-transform:uppercase;letter-spacing:.03em;
           padding:3px 7px;border:1px solid var(--line);border-radius:999px;background:transparent;color:var(--muted);flex-shrink:0;white-space:nowrap}
  .ev-pill::before{content:"";width:5px;height:5px;border-radius:50%;background:currentColor;opacity:.78;flex:0 0 auto}
  .ev-pill.ev-confirmed{color:var(--open);border-color:color-mix(in srgb,var(--open) 42%,transparent)}
  .ev-pill.ev-speculation{color:#B45309;border-color:rgba(217,119,6,.42)}
  .ev-pill.ev-unverified{border-style:dashed}
  .lead.lead-dossier .ev-pill{color:#A8A7A0;border-color:#3A3A34;background:rgba(255,255,255,.04)}
  .lead.lead-dossier .ev-pill.ev-confirmed{color:#34D399;border-color:rgba(52,211,153,.38)}
  .lead.lead-dossier .ev-pill.ev-speculation{color:#FBBF24;border-color:rgba(251,191,36,.38)}
  .cx-meta{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-top:2px}
  .cx-meta .ev-pill{font-size:8.8px;padding:2px 6px}
  .score{display:inline-flex;align-items:center;font:700 11px/1 var(--f-mono);margin-left:auto;padding:4px 7px;
         border:1px solid var(--line);background:var(--card-2);color:var(--muted);font-variant-numeric:tabular-nums;
         letter-spacing:.02em;flex-shrink:0}
  .score.s-95{background:#FF4500;color:#121211;border:2px solid var(--ink);box-shadow:1px 1px 0 var(--ink)}
  .score.s-88{background:#FF8A5C;color:#121211;border:1.5px solid var(--ink)}
  .score.s-80{background:#FFE4D6;color:#9A3412;border:1.5px solid #EA580C}
  .score.s-70{background:#F3F1EA;color:var(--muted);border:1px solid var(--line)}
  .score.s-low{background:var(--card-2);color:var(--muted);border:1px solid var(--line);opacity:.82}
  :root[data-theme="dark"] .score.s-80{background:rgba(255,87,34,.22);color:#FFA07A;border-color:#EA580C}
  :root[data-theme="dark"] .score.s-70{background:#232320;color:var(--muted);border-color:var(--line)}
  :root[data-theme="dark"] .ev-pill.ev-speculation{color:#FBBF24;border-color:rgba(251,191,36,.38)}
  @media (prefers-color-scheme: dark){
    :root:not([data-theme="light"]) .score.s-80{background:rgba(255,87,34,.22);color:#FFA07A;border-color:#EA580C}
    :root:not([data-theme="light"]) .score.s-70{background:#232320;color:var(--muted);border-color:var(--line)}
    :root:not([data-theme="light"]) .ev-pill.ev-speculation{color:#FBBF24;border-color:rgba(251,191,36,.38)}
  }
  .hero-title{margin:0 0 10px;font:700 clamp(21px,2.4vw,30px)/1.15 var(--f-head);letter-spacing:-.02em}
  .hero-title a:hover,.card-title a:hover,.cx-t a:hover{text-decoration:underline;text-decoration-thickness:2px;text-underline-offset:3px}
  .sw{font-size:15px;line-height:1.6}
  .facts{display:grid;gap:8px;margin-top:14px;padding-top:12px;border-top:1px dashed var(--line)}
  @media(min-width:860px){.facts.two{grid-template-columns:1fr 1fr;gap:18px}}
  .fact{display:flex;gap:9px;align-items:flex-start;font-size:13px;line-height:1.5}
  .fact .k{font:700 10.5px var(--f-mono);text-transform:uppercase;flex-shrink:0;padding:2px 5px;border:1px solid var(--ink)}
  .fact.pw .k{background:var(--orange);color:#121211}
  .fact.wn .k{background:var(--lime);color:#121211}
  .also{font:400 12px/1.7 var(--f-mono);color:var(--muted);margin-top:10px}
  .also a,.also span{color:var(--text)}
  .also a{text-decoration:underline;text-underline-offset:2px}
  .also a:hover{background:rgba(204,255,0,.3)}
  .ents{display:flex;gap:6px;flex-wrap:wrap;margin-top:12px}
  .ent{font:600 10.5px var(--f-mono);padding:3px 6px;border:1px solid var(--ink);background:var(--card-2)}

  .grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:22px}
  .card{display:flex;flex-direction:column}
  .card-body{padding:14px 16px 16px;display:flex;flex-direction:column;gap:8px;flex:1}
  .card .meta-row{margin-bottom:0}
  .card-title{margin:0;font:700 19px/1.22 var(--f-head);letter-spacing:-.01em;
              display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}
  .card .sw{font-size:14px;line-height:1.5;color:var(--muted);overflow-wrap:anywhere;
            display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
  .card-foot{margin-top:auto;padding-top:10px;border-top:1px dashed var(--line);display:grid;gap:6px}
  .card-foot .fact{font-size:12px;line-height:1.4}
  .card-foot .fact .v{min-width:0;flex:1;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}

  /* -- Contexto -- */
  .section-h{margin:34px 0 14px}
  .section-h h2{margin:0}
  .ctx,.watch-agenda,.watch-results{border-top:2px solid var(--ink);background:var(--card)}
  .cx,.watch-row{display:grid;grid-template-columns:minmax(9rem,15rem) minmax(0,1fr);gap:16px;align-items:baseline;padding:14px 16px;border-bottom:1px solid var(--line)}
  .cx-t,.watch-row p{margin:0;font:600 16px/1.45 var(--f-head);max-width:80ch}
  .watch-link,.watch-row a{text-decoration:underline;text-underline-offset:3px}
  .watch-row .src{align-self:start}
  .watch-row blockquote{margin:5px 0;color:var(--muted);font-size:14px}
  [id^="watch-point-"]{scroll-margin-top:12px}
  [id^="watch-point-"]:target{box-shadow:inset 4px 0 var(--orange)}

  .empty{padding:40px 26px;text-align:center;border:2px dashed var(--ink);background:var(--card)}
  .empty .big{font:700 20px var(--f-head);margin-bottom:8px;text-transform:uppercase}
  .empty .sub{font-size:14px;color:var(--muted);max-width:52ch;margin:0 auto;line-height:1.6}

  .metric-context{margin:.65rem 0;font-size:.86rem;line-height:1.45}
  .metric-context summary{display:list-item;width:fit-content;max-width:100%;box-sizing:border-box;cursor:pointer;font-weight:700;background:#ffda55;color:#201a07;border:1px solid #806419;border-radius:1rem;padding:.22rem .75rem}
  .metric-context summary:focus-visible{outline:3px solid currentColor;outline-offset:2px}
  .metric-context blockquote{margin:.45rem 0;padding-left:.7rem;border-left:2px solid var(--line)}
  .metric-context a{text-decoration:underline}

  /* -- Sidebar -- */
  .sidebar{display:grid;gap:22px;position:sticky;top:16px}
  .widget{background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow);padding:14px 16px}
  .widget-title{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:-14px -16px 12px;
                padding:10px 16px;border-bottom:2px solid var(--ink);background:var(--card-2)}
  .widget-title>span:first-child{display:flex;align-items:center;gap:9px;font:700 12px/1.2 var(--f-mono);text-transform:uppercase;letter-spacing:.06em}
  .widget-title>span:first-child::before{content:"";width:10px;height:10px;background:var(--orange);border:2px solid var(--ink)}
  .widget-title .lbl{font:400 10px var(--f-mono);color:var(--muted);text-transform:uppercase}

  .m-chg{font:700 11px var(--f-mono)}
  .m-chg.pos{color:var(--open)} .m-chg.neg{color:var(--bad)}
  .m-chg.na{color:var(--muted);font-weight:400}
  .m-price{font:700 14px var(--f-mono);margin-bottom:4px;font-variant-numeric:tabular-nums}
  .m-nodata{opacity:.55}
  .spark{width:100%;height:22px;display:block}
  .spark.pos polyline{stroke:var(--open)} .spark.neg polyline{stroke:var(--bad)}

  #visit-changes{margin:24px 0 0;padding:16px 18px}
  .visit-update[hidden]{display:none}
  #visit-changes .widget-title{margin:-16px -18px 14px;padding:10px 18px}
  .deck.filtered #visit-changes{order:3}
  .vc-note{margin:0 0 10px;color:var(--muted);font-size:13px}
  .vc-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr));gap:14px}
  .visit-update{display:flex;flex-direction:column;gap:8px;min-width:0;padding:12px 14px;background:var(--card-2);border:1.5px solid var(--ink);overflow-wrap:anywhere}
  .vc-top{display:flex;align-items:center;justify-content:space-between;gap:8px}
  .vc-status{display:inline-flex;align-items:center;gap:5px;font:700 10px/1 var(--f-mono);text-transform:uppercase;letter-spacing:.05em;
             padding:3px 7px;border:1.5px solid var(--ink);background:var(--lime);color:#121211}
  .vc-status.vc-confirmed{background:#34D399;color:#121211}
  .vc-status.vc-correction{background:#FBBF24;color:#121211}
  .vc-status.vc-expired{background:var(--card);color:var(--muted)}
  .vc-date{font:600 10.5px var(--f-mono);color:var(--muted)}
  .vc-flow{display:grid;grid-template-columns:minmax(0,1fr) 22px minmax(0,1.15fr);gap:8px;align-items:stretch}
  .vc-flow.single{grid-template-columns:minmax(0,1fr)}
  .vc-step{display:flex;flex-direction:column;gap:5px;padding:10px 11px;border:1px solid var(--line);background:var(--card)}
  .vc-step.vc-before{background:transparent;border-style:dashed}
  .vc-step.vc-after{border-color:var(--ink);border-left:3.5px solid var(--orange)}
  .vc-step-h{display:flex;align-items:center;justify-content:space-between;gap:6px;flex-wrap:wrap}
  .vc-k{font:700 9.5px/1 var(--f-mono);text-transform:uppercase;letter-spacing:.06em;padding:2px 5px;border:1px solid var(--line);color:var(--muted);background:var(--card-2)}
  .vc-after .vc-k{background:var(--orange);color:#121211;border-color:var(--ink)}
  .vc-meta{font:600 10px/1 var(--f-mono);color:var(--muted);text-transform:uppercase}
  .vc-link{font:600 13.5px/1.35 var(--f-head);color:var(--text);text-decoration:none}
  .vc-before .vc-link{font-weight:500;color:var(--muted)}
  .vc-link:hover{text-decoration:underline;text-underline-offset:2px}
  .vc-arrow{align-self:center;text-align:center;font:700 16px/1 var(--f-mono);color:var(--orange-ink)}
  .vc-watch{display:flex;align-items:baseline;gap:8px;padding-top:8px;border-top:1px dashed var(--line);font-size:12.5px;line-height:1.4;color:var(--muted)}
  .vc-wk{font:700 9.5px/1 var(--f-mono);text-transform:uppercase;padding:2px 5px;border:1px solid var(--ink);background:var(--lime);color:#121211;flex-shrink:0}

  footer{margin-top:56px;padding-top:14px;border-top:3px solid var(--ink);display:flex;justify-content:space-between;
         gap:16px;flex-wrap:wrap;font:400 12px var(--f-mono);color:var(--muted)}

  @media(max-width:1220px){
    .opening{grid-template-columns:1fr 1fr}
    .opening .lead{grid-column:1/-1;order:-1}
    .opening[data-cols="2"]{grid-template-columns:300px minmax(0,1fr)}
    .opening[data-cols="2"] .lead{grid-column:auto;order:0}
    .below .grid{--card-width:calc((100% - 22px)/2)}
  }
  @media(max-width:860px){
    .opening,.opening[data-cols="2"]{grid-template-columns:1fr}
    .opening .lead,.opening[data-cols="2"] .lead{grid-column:auto;order:-1}
  }
  @media(max-width:720px){
    .below .grid{--card-width:100%}
    .grid,.vc-flow{grid-template-columns:minmax(0,1fr)}
    .vc-arrow{display:none}
    .tq{flex:0 0 170px}
    .pulse{grid-template-columns:1fr}
    .cx,.watch-row{grid-template-columns:1fr;gap:5px}
    .lead-media .hero-img{aspect-ratio:16/9;max-height:240px}
    .lead.lead-dossier .lead-body,.lead-body{padding:18px 16px}
    .lead .hero-title,.lead.lead-dossier .hero-title{font-size:27px}
    .wrap{padding:16px 16px 60px}
    .tabs{flex-wrap:nowrap;overflow-x:auto;margin:0 -16px;padding:2px 16px 16px;scrollbar-width:none}
    .tabs::-webkit-scrollbar{display:none}
    .tab{flex:0 0 auto;white-space:nowrap}
  }
</style>
</head>
<body>
{{ brand_header }}
<div class="strip">
  <span>{{ bi("Edición","Edition") }} <b class="hl">{{ generated_at }}</b>{% if nav == 'daily' and not archive %} <span class="stale" id="stale" data-date="{{ generated_at }}" hidden></span>{% endif %}</span>
  <span class="it {{ 'bad' if activity.class == 'alert' else ('warn' if activity.class == 'active' else '') }}">{{ bi(activity.label, activity_en) }}</span>
  {% if pulse and pulse.value is not none %}<span class="it {{ 'bad' if activity.class == 'alert' else ('warn' if activity.class == 'active' else '') }}">{{ bi("Pulso","Pulse") }} <b>{{ pulse.value }}/100</b></span>{% endif %}
  <span class="it">{{ n_signals }} {{ bi("señales","signals") }}{% if n_context %} · {{ n_context }} {{ bi("de contexto","context") }}{% endif %}</span>
  <span class="it{% if sources_dead %} warn{% endif %}">{{ sources_alive }}/{{ sources_total }} {{ bi("fuentes","sources") }}</span>
  {% if x_layer and x_layer.status == 'ok' and x_layer.posts %}<span class="it">X: {{ x_layer.posts }} posts</span>{% elif x_layer and x_layer.status in ['killed','disabled'] %}<span class="it bad">{{ bi("X apagada","X off") }}</span>{% endif %}
  <span class="r data-links"><span class="dl-h">{{ bi("Datos","Data") }}</span>
    <a href="https://artificialanalysis.ai/models" target="_blank" rel="noopener noreferrer" title="Artificial Analysis · índice de inteligencia y precios">Artificial Analysis ↗</a>
    <a href="https://epoch.ai/data/ai-models" target="_blank" rel="noopener noreferrer" title="Epoch AI · base de datos de modelos">Epoch {{ bi("Modelos","Models") }} ↗</a>
    <a href="https://epoch.ai/eci" target="_blank" rel="noopener noreferrer" title="Epoch Capabilities Index">Epoch ECI ↗</a>
  </span>
</div>
<div class="wrap">

  {% if archive %}
  <div class="arch-bar">
    <a href="{{ root }}archivo.html">← {{ bi("Archivo","Archive") }}</a>
    {% if archive.prev %}<a href="{{ root }}d/{{ archive.prev }}.html">{{ archive.prev }}</a>{% endif %}
    <span class="here">{{ generated_at }}</span>
    {% if archive.next %}<a href="{{ root }}d/{{ archive.next }}.html">{{ archive.next }}</a>{% endif %}
    <a href="{{ root }}index.html" style="margin-left:auto">{{ bi("Hoy","Today") }}</a>
  </div>
  {% endif %}

  {% if degraded %}
  <div class="notice warn">
    <b>{{ bi("Modo degradado.","Degraded mode.") }}</b>
    {{ bi("El análisis del LLM no está disponible hoy, así que el filtro de relevancia no se ha aplicado. Lo que ves está ordenado por heurística y puede contener ruido.",
          "The LLM analysis is unavailable today, so the relevance filter was not applied. Items are ranked heuristically and may include noise.") }}
  </div>
  {% endif %}
  {% if x_layer and x_layer.status in ['killed', 'disabled'] %}
  <div class="notice">
    <b>{{ bi("Capa X apagada.","X layer off.") }}</b>
    {% if x_layer.status == 'disabled' %}
    {{ bi("X_DISABLED=1: no se ha consultado el espejo.","X_DISABLED=1: the X mirror was skipped.") }}
    {% else %}
    {{ bi("El espejo no devolvió posts (" ~ x_layer.configured ~ " cuentas). El briefing sigue con RSS.", "The mirror returned no posts (" ~ x_layer.configured ~ " accounts). The briefing continues with RSS.") }}
    {% endif %}
  </div>
  {% endif %}

  <!-- Tabs de tema -->
  {% if theme_tabs or show_new_tab %}
  <div class="tabs" id="tabs" role="tablist">
    <button type="button" role="tab" aria-selected="true" class="tab on" data-filter="all">{{ bi("Todas","All") }}<span class="n">{{ n_signals + n_context }}</span></button>
    {% if show_new_tab %}
    <button type="button" role="tab" aria-selected="false" class="tab tab-new" data-filter="__new__">{{ bi("Nuevo","New") }}<span class="n">{{ n_new }}</span></button>
    {% endif %}
    {% for t in theme_tabs %}
    <button type="button" role="tab" aria-selected="false" class="tab" data-filter="{{ t.key }}">{{ bi(t.label, t.label_en) }}<span class="n">{{ t.count }}</span></button>
    {% endfor %}
  </div>
  {% endif %}

  <div class="deck" id="deck">

  {% if hero %}
  <section class="opening"{% if not context %} data-cols="2"{% endif %}>

    <!-- Columna izquierda: El Editorial -->
    <aside class="rail">
      <div class="rail-h"><span>{{ bi("El editorial","Editorial") }}</span><span class="lbl">01 / {{ bi("Análisis","Analysis") }}</span></div>
      <h1 class="rail-title">{{ bi("La tesis del día","Thesis of the day") }}</h1>
      <p class="rail-thesis">{{ bi(thesis, thesis_en) }}</p>
      {% if key_signals %}
      <div class="rail-h"><span>{{ bi("Claves del día","Key points") }}</span><span class="lbl">{{ bi("Selección","Selection") }}</span></div>
      <ol class="keys">
        {% for k in key_signals %}<li>{{ bi(k, key_signals_en[loop.index0] if loop.index0 < key_signals_en|length else "") }}</li>{% endfor %}
      </ol>
      {% endif %}
      <div class="rail-foot">
        <div class="figures">
          <div class="fig-row">
            <strong class="fig-count">{{ n_signals + n_context }}</strong>
            <span class="fig-note">{{ n_signals }} {{ bi("señales","signals") }}{% if n_context %} · {{ n_context }} {{ bi("contexto","context") }}{% endif %} · {{ n_dropped }} {{ bi("descartadas","dropped") }}</span>
          </div>
          {% if top_entities %}<div class="ents">{% for e in top_entities %}<span class="ent">{{ e }}</span>{% endfor %}</div>{% endif %}
        </div>
      </div>
    </aside>

    <!-- Columna central: Portada #01 (adaptativa foto/dossier) -->
    <article class="lead {% if hero.cover_only %}lead-dossier{% else %}lead-photo{% endif %}" style="--lead-accent:{{ hero.accent }}">
      <div class="lead-wm" aria-hidden="true">{{ hero.watermark_svg|safe }}</div>
      {% if not hero.cover_only %}
      <a class="lead-media" href="{{ (hero.url or hero.link)|safe_url }}" target="_blank" rel="noopener noreferrer">
        <div class="lead-media-bar">
          <span class="tag">#01 · {{ bi("Portada","Front page") }} / {{ bi(hero.theme_label, hero.theme_label_en) }}</span>
          {% if hero.is_new %}<span class="badge-new">{{ bi("Nuevo","New") }}</span>{% endif %}
          <span class="score {{ hero.score_cls }}">{{ hero.score }}/100</span>
        </div>
        <img class="hero-img" src="{{ hero.image_url }}" data-fb="{{ hero.fallback_image }}" data-fb-en="{{ hero.cover_en }}" alt="" referrerpolicy="no-referrer"/>
      </a>
      {% endif %}
      <div class="lead-body">
        <div class="lead-top">
          <span class="tag">#01 · {{ bi("Portada","Front page") }} / {{ bi(hero.theme_label, hero.theme_label_en) }}</span>
          {% if hero.is_new %}<span class="badge-new">{{ bi("Nuevo","New") }}</span>{% endif %}
          <span class="score {{ hero.score_cls }}">{{ hero.score }}/100</span>
        </div>
        <h2 class="hero-title">
          <a href="{{ (hero.url or hero.link)|safe_url }}" target="_blank" rel="noopener noreferrer">{{ bi(hero.display_title, hero.title_en) }}</a>
        </h2>
        {% if hero.so_what and not hero.impact_from_consequence %}<div class="sw">{{ bi(hero.so_what, hero.so_what_en) }}</div>{% endif %}{% if hero.measurement %}
            {{ measurement(hero) }}{% endif %}
        {% if hero.impact or hero.watch_next %}
        <div class="lead-intel {% if hero.impact and hero.watch_next %}two{% endif %}">
          {% if hero.impact %}
          <div class="intel-box pw"><span class="k intel-k">{{ bi("Impacto","Impact") }}</span><span class="intel-v">{{ bi(hero.impact, hero.impact_en) }}</span></div>
          {% endif %}
          {% if hero.watch_next %}
          <div class="intel-box wn"><span class="k intel-k">{{ bi("Vigilar","Watch") }}</span><span class="intel-v">{{ watch_text(hero) }}</span></div>
          {% endif %}
        </div>
        {% endif %}
        {% if hero.also %}
        <div class="also">{{ bi("También en:","Also in:") }}
          {% for a in hero.also %}{% if a.url %}<a href="{{ a.url }}" target="_blank" rel="noopener noreferrer">{{ a.label }}</a>{% else %}<span>{{ a.label }}</span>{% endif %}{% if not loop.last %} · {% endif %}{% endfor %}{% if hero.also_more %} · +{{ hero.also_more }}{% endif %}
        </div>
        {% endif %}
        <div class="lead-foot">
          <div class="lead-foot-l">
            <span class="src"><img src="{{ hero.logo }}" alt="" loading="lazy"/>{{ hero.source_label }}</span>
            {{ ev_pill(hero) }}
            {% if hero.ents %}
            <div class="ents">{% for e in hero.ents[:4] %}<span class="ent">{{ e }}</span>{% endfor %}</div>
            {% endif %}
          </div>
          <a class="lead-cta" href="{{ (hero.url or hero.link)|safe_url }}" target="_blank" rel="noopener noreferrer">{{ bi("Leer fuente ↗","Read source ↗") }}</a>
        </div>
      </div>
    </article>

    <!-- Columna derecha: Contexto + Qué vigilar -->
    {% if context %}
    <aside class="side-rail">
      <section class="ctx-block" id="ctx-block">
        <div class="rail-h"><span>{{ bi("Contexto","Context") }}</span><span class="lbl">{{ bi("Lectura rápida","Quick read") }}</span></div>
        <div class="ctx">
          {% for it in context %}
          <article class="cx" data-topic="{{ it.theme_key }}" data-new="{{ 1 if it.is_new else 0 }}">
            <div class="cx-body">
              <span class="cx-theme">{{ bi(it.theme_label, it.theme_label_en) }}</span>
              <h3 class="cx-t"><a href="{{ (it.url or it.link)|safe_url }}" target="_blank" rel="noopener noreferrer">{{ bi(it.display_title, it.title_en) }}</a></h3>
              <div class="cx-meta">
                <span class="src"><img src="{{ it.logo }}" alt="" loading="lazy"/>{{ it.source_label }}</span>
                {{ ev_pill(it) }}
              </div>
              {% if it.measurement %}{{ measurement(it) }}{% endif %}
            </div>
          </article>
          {% endfor %}
        </div>
      </section>
      {% if watch_agenda %}
      <section class="watch-rail" aria-labelledby="agenda-title">
        <div class="rail-h"><span id="agenda-title">{{ bi("Qué vigilar","What to watch") }}</span><span class="lbl">{{ bi("Seguimiento","Follow-up") }}</span></div>
        <div class="watch-agenda">
          {% for w in watch_agenda %}
          <div class="watch-row" id="{{ w.anchor }}">
            <p>{{ bi(w.text, w.text_en) }}</p>
            {% if w.refs %}<div class="src">{% for ref in w.refs %}<a href="{{ ref.url }}" target="_blank" rel="noopener noreferrer">{{ ref.source }}</a>{% if not loop.last %} · {% endif %}{% endfor %}</div>{% endif %}
          </div>
          {% endfor %}
        </div>
      </section>
      {% endif %}
    </aside>
    {% endif %}
  </section>
  {% endif %}

  {% if watch_agenda and (not hero or not context) %}
  <section class="watch-standalone" aria-labelledby="agenda-title">
    <div class="section-h"><h2 class="sec" id="agenda-title">{{ bi("Qué vigilar","What to watch") }}</h2></div>
    <div class="watch-agenda">
      {% for w in watch_agenda %}
      <div class="watch-row" id="{{ w.anchor }}">
        <div class="src">{% for ref in w.refs %}<a href="{{ ref.url }}" target="_blank" rel="noopener noreferrer">{{ ref.source }}</a>{% if not loop.last %} · {% endif %}{% endfor %}</div>
        <p>{{ bi(w.text, w.text_en) }}</p>
      </div>
      {% endfor %}
    </div>
  </section>
  {% endif %}

  {% if (pulse and pulse.series) or ticker_quotes %}
  <div class="telemetry-band">
    <!-- Pulso de la carrera: indicador propio del radar -->
    {% if pulse and pulse.series %}
    <section class="pulse" aria-label="Race pulse">
      <div class="pulse-now">
        <span class="kicker">{{ bi("Pulso de la carrera","Race pulse") }}</span>
        <div class="pulse-num"><strong>{{ pulse.value }}</strong><span>/100</span></div>
        <div class="pulse-bar" role="img" aria-label="{{ pulse.value }} / 100"><i style="width:{{ pulse.value }}%"></i></div>
      </div>
      <div class="pulse-hist">
        <div class="pulse-cols">
          {% for p in pulse.series %}<i class="{% if loop.last %}now{% endif %}" style="height:{{ [p.value, 4]|max }}%" title="{{ p.date }} · {{ p.value }}"></i>{% endfor %}
        </div>
        <div class="pulse-note">
          {% if pulse.hotter_than is not none %}{{ bi("Más intenso que el " ~ pulse.hotter_than ~ " % de las últimas " ~ pulse.editions ~ " ediciones", "Hotter than " ~ pulse.hotter_than ~ "% of the last " ~ pulse.editions ~ " editions") }} · {% endif %}{{ bi("mide cuánta señal trae el día, no el progreso hacia la AGI", "measures how much signal the day carries, not progress towards AGI") }}
        </div>
      </div>
    </section>
    {% endif %}

    <!-- Mercados: banda rotativa a todo el ancho. El contenido va dos veces para
         que el bucle no tenga corte; la segunda copia es invisible para lectores. -->
    {% if ticker_quotes %}
    <section class="ticker" aria-label="Markets">
      <div class="ticker-h"><strong>{{ bi("Mercados","Markets") }}</strong><span>{{ bi("Último cierre · Investing.com · no es tiempo real","Last close · Investing.com · not real time") }}</span></div>
      <div class="ticker-view">
        <div class="ticker-track" style="--n:{{ ticker_quotes|length }}">
          {% for copy in (0, 1) %}
          <div class="ticker-q"{% if copy %} aria-hidden="true"{% endif %}>
            {% for m in ticker_quotes %}
            {% if m.url %}
            <a class="tq{% if not m.available %} m-nodata{% endif %}" href="{{ m.url|safe_url }}" target="_blank" rel="noopener noreferrer"{% if copy %} tabindex="-1"{% endif %} title="{{ m.label }} · Investing.com">
              <span class="tq-n">{{ m.label }}</span>
              <span class="tq-p">{{ m.price_str }}</span>
              {% if m.available %}<span class="m-chg {% if m.positive %}pos{% else %}neg{% endif %}">{{ m.change_str }}</span>{% else %}<span class="m-chg na">n/d</span>{% endif %}
              {{ m.sparkline_svg|safe }}
            </a>
            {% else %}
            <div class="tq{% if not m.available %} m-nodata{% endif %}">
              <span class="tq-n">{{ m.label }}</span>
              <span class="tq-p">{{ m.price_str }}</span>
              {% if m.available %}<span class="m-chg {% if m.positive %}pos{% else %}neg{% endif %}">{{ m.change_str }}</span>{% else %}<span class="m-chg na">n/d</span>{% endif %}
              {{ m.sparkline_svg|safe }}
            </div>
            {% endif %}
            {% endfor %}
          </div>
          {% endfor %}
        </div>
      </div>
    </section>
    {% endif %}
  </div>
  {% endif %}

  {% if nav == 'daily' and not archive %}
  <section id="visit-changes" class="widget" data-edition="{{ generated_at }}">
    <h2 class="widget-title">
      <span>{{ bi("Qué cambió desde tu última visita", "What changed since your last visit") }}</span>
      <span class="lbl">{{ bi("Seguimiento","Story follow-up") }}</span>
    </h2>
    {%- if visit_updates %}
    <p class="vc-note" id="visit-recent">{{ bi("Últimos cambios registrados en el radar.", "Latest changes tracked by the radar.") }}</p>
    {%- endif %}
    <p class="vc-note" id="visit-empty"{% if visit_updates %} hidden{% endif %}>{{ bi("Sin novedades de seguimiento en este periodo.", "No follow-up updates in this period.") }}</p>
    <div class="vc-list">
      {% for u in visit_updates %}
      <article class="visit-update" data-updated="{{ u.date }}">
        <div class="vc-top">
          <span class="vc-status vc-{{ u.status }}">
            {% if u.status == 'confirmed' %}{{ bi("✓ Hito confirmado","✓ Milestone confirmed") }}
            {% elif u.status == 'expired' %}{{ bi("○ Plazo vencido","○ Deadline passed") }}
            {% elif u.status == 'correction' %}{{ bi("! Rectificación","! Correction") }}
            {% else %}{{ bi("↻ Nuevo desarrollo","↻ New development") }}{% endif %}
          </span>
          <span class="vc-date">{{ u.date }}</span>
        </div>
        <div class="vc-flow{% if not u.after %} single{% endif %}">
          <div class="vc-step vc-before">
            <div class="vc-step-h">
              <span class="vc-k">{{ bi("Antes","Before") }}</span>
              <span class="vc-meta">{{ u.before.source }}{% if u.before.date %} · {{ u.before.date[5:] }}{% endif %}</span>
            </div>
            <a class="vc-link" href="{{ u.before.url|safe_url }}" target="_blank" rel="noopener noreferrer">{{ bi(u.before.es, u.before.en) }}</a>
          </div>
          {% if u.after %}
          <span class="vc-arrow" aria-hidden="true">→</span>
          <div class="vc-step vc-after">
            <div class="vc-step-h">
              <span class="vc-k">{{ bi("Ahora","Now") }}</span>
              <span class="vc-meta">{{ u.after.source }}{% if u.after.date %} · {{ u.after.date[5:] }}{% endif %}</span>
            </div>
            <a class="vc-link" href="{{ u.after.url|safe_url }}" target="_blank" rel="noopener noreferrer">{{ bi(u.after.es, u.after.en) }}</a>
          </div>
          {% endif %}
        </div>
        {% if u.before.watch and u.status != 'confirmed' %}
        <div class="vc-watch">
          <span class="vc-wk">{{ bi("Pendiente","Open") }}</span>
          <span>{{ bi(u.before.watch, u.before.watch_en) }}</span>
        </div>
        {% endif %}
      </article>
      {% endfor %}
    </div>
  </section>
  {% endif %}

  {% if not n_signals and not n_context %}
      <div class="empty">
        <div class="big">{{ bi("Hoy no ha pasado nada que mueva la aguja.","Nothing moved the needle today.") }}</div>
        <div class="sub">
          {{ bi("El filtro de relevancia descartó todo lo ingerido por irrelevante. Un día sin señal también es información: significa que la carrera frontier no se movió.",
                "The relevance filter dropped all ingested items as noise. A day without signals is also information: the frontier race did not move.") }}
        </div>
      </div>
      {% endif %}

  <!-- Resto de señales (#2..#12). Con un filtro activo se incluye tambien la portada. -->
  {% if grid_cards %}
  <section class="below{% if not has_grid_cards %} no-rest{% endif %}">
    <div class="section-h h-all"><h2 class="sec">{{ bi("Más allá del titular","Beyond the headline") }}</h2></div>
    <div class="section-h h-filtered"><h2 class="sec">{{ bi("Señales de esta sección","Signals in this section") }}</h2></div>
    <div class="grid">
      {% for it in grid_cards %}{% set dup = hero and loop.first %}
        <article class="card{% if dup %} dup{% elif it.archive_date %} from-archive{% endif %}"{% if not it.archive_date %} data-topic="{{ it.theme_key }}" data-new="{{ 1 if it.is_new else 0 }}"{% endif %}>
          <a href="{{ (it.url or it.link)|safe_url }}" target="_blank" rel="noopener noreferrer">
            {% if it.cover_only %}<img class="card-img l-es" src="{{ it.image_url }}" alt="" loading="lazy"/><img class="card-img l-en" src="{{ it.cover_en }}" alt="" loading="lazy"/>
            {% else %}<img class="card-img" src="{{ it.image_url }}" data-fb="{{ it.fallback_image }}" data-fb-en="{{ it.cover_en }}" alt="" loading="lazy" referrerpolicy="no-referrer"/>{% endif %}
          </a>
          <div class="card-body">
            <div class="meta-row">
              {% if it.archive_date %}<span class="tag">{{ bi("Archivo","Archive") }} · {{ it.archive_date }}</span>
              {% elif it.is_new %}<span class="badge-new">{{ bi("Nuevo","New") }}</span>{% endif %}
              {% if it.layer == "context" %}<span class="tag">{{ bi("Contexto","Context") }}</span>{% endif %}
              <span class="src"><img src="{{ it.logo }}" alt="" loading="lazy"/>{{ it.source_label }}</span>
              {% if it.other_sources %}<span class="multi">+{{ it.other_sources|length }}</span>{% endif %}
              {{ ev_pill(it) }}
              <span class="score {{ it.score_cls }}">{{ it.score }}/100</span>
            </div>
            <h3 class="card-title">
              <a href="{{ (it.url or it.link)|safe_url }}" target="_blank" rel="noopener noreferrer">{{ bi(it.display_title, it.title_en) }}</a>
            </h3>
            {% if it.so_what and not it.impact_from_consequence %}<div class="sw">{{ bi(it.so_what, it.so_what_en) }}</div>{% endif %}{% if it.measurement %}
            {{ measurement(it) }}{% endif %}
            {% if it.also %}
            <div class="also">{{ bi("También en:","Also in:") }}
              {% for a in it.also %}{% if a.url %}<a href="{{ a.url }}" target="_blank" rel="noopener noreferrer">{{ a.label }}</a>{% else %}<span>{{ a.label }}</span>{% endif %}{% if not loop.last %} · {% endif %}{% endfor %}{% if it.also_more %} · +{{ it.also_more }}{% endif %}
            </div>
            {% endif %}
            {% if it.impact or it.watch_next %}
            <div class="card-foot">
              {% if it.impact %}
              <div class="fact pw"><span class="k">{{ bi("Impacto","Impact") }}</span><span class="v">{{ bi(it.impact, it.impact_en) }}</span></div>
              {% endif %}
              {% if it.watch_next %}
              <div class="fact wn"><span class="k">{{ bi("Vigilar","Watch") }}</span><span class="v">{{ watch_text(it) }}</span></div>
              {% endif %}
            </div>
            {% endif %}
          </div>
        </article>
      {% endfor %}
    </div>
  </section>
  {% endif %}

      {% if context and not hero %}
      <section class="ctx-block" id="ctx-block">
        <div class="section-h">
          <h2 class="sec">{{ bi("Contexto","Context") }}</h2>
        </div>
        <div class="ctx">
          {% for it in context %}
          <article class="cx" data-topic="{{ it.theme_key }}" data-new="{{ 1 if it.is_new else 0 }}">
            <div class="cx-meta">
              <span class="src"><img src="{{ it.logo }}" alt="" loading="lazy"/>{{ it.source_label }}</span>
              {{ ev_pill(it) }}
            </div>
            <div>
              <h3 class="cx-t"><a href="{{ (it.url or it.link)|safe_url }}" target="_blank" rel="noopener noreferrer">{{ bi(it.display_title, it.title_en) }}</a></h3>
              {% if it.measurement %}{{ measurement(it) }}{% endif %}
            </div>
          </article>
          {% endfor %}
        </div>
      </section>
      {% endif %}

  </div>

  {% if watch_results %}
  <section aria-labelledby="results-title">
    <div class="section-h"><h2 class="sec" id="results-title">{{ bi("Hitos confirmados","Confirmed milestones") }}</h2></div>
    <div class="watch-results">
      {% for w in watch_results %}
      <div class="watch-row">
        <a class="src" href="{{ w.evidence_url }}" target="_blank" rel="noopener noreferrer">{{ bi("Ver evidencia","View evidence") }}</a>
        <div><p>{{ bi(w.text, w.text_en) }}</p><blockquote>{{ w.evidence }}</blockquote></div>
      </div>
      {% endfor %}
    </div>
  </section>
  {% endif %}

  {{ credits }}
  <footer>
    <span>{{ n_dropped }} {{ bi("items descartados por el filtro de relevancia","items dropped by the relevance filter") }}</span>
    <span>{{ sources_alive }}/{{ sources_total }} {{ bi("fuentes activas","active sources") }}{% if sources_dead %} · {{ bi("sin items","no items") }}: {{ sources_dead }}{% endif %}{% if x_layer and x_layer.status == 'killed' %} · X: kill switch{% elif x_layer and x_layer.status == 'disabled' %} · X: disabled{% elif x_layer and x_layer.status == 'ok' and x_layer.posts %} · X: {{ x_layer.posts }} posts{% endif %}</span>
  </footer>

</div>

<script>
  // La visita se mide por edición. Recargar mantiene la misma comparación.
  (function(){
    const panel = document.getElementById('visit-changes');
    if (!panel) return;
    const today = panel.dataset.edition;
    const key = 'nexus.daily.visit.v1';
    try {
      let state = null;
      try { state = JSON.parse(localStorage.getItem(key)); } catch (_) {}
      const valid = d => typeof d === 'string' && /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(d);
      if (!valid(today) || (state && valid(state.latest) && state.latest > today)) return;
      const previous = state && valid(state.latest)
        ? (state.latest === today ? state.previous : state.latest) : null;
      localStorage.setItem(key, JSON.stringify({latest: today, previous}));
      if (!valid(previous) || previous >= today) return;
      const recent = panel.querySelector('#visit-recent');
      if (recent) recent.hidden = true;
      let hasUpdates = false;
      for (const row of panel.querySelectorAll('[data-updated]')) {
        row.hidden = !(row.dataset.updated > previous && row.dataset.updated <= today);
        if (!row.hidden) hasUpdates = true;
      }
      panel.querySelector('#visit-empty').hidden = hasUpdates;
    } catch (_) { /* Sin historial local fiable no se afirma que haya novedades. */ }
  })();

  // Si la edicion no es de hoy (por ejemplo, antes de la ejecucion de la manana), se dice:
  // sin esto la portada de ayer se lee como si fuera la de hoy.
  (function(){
    var el = document.getElementById('stale');
    if (!el) return;
    var p = (el.getAttribute('data-date') || '').split('-');
    if (p.length !== 3) return;
    var edition = new Date(+p[0], +p[1] - 1, +p[2]);
    var now = new Date();
    var today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    var days = Math.round((today - edition) / 86400000);
    if (!(days >= 1)) return;
    var es = days === 1 ? 'edición de ayer' : 'edición de hace ' + days + ' días';
    var en = days === 1 ? "yesterday's edition" : days + ' days old';
    el.innerHTML = '<span class="l-es">' + es + '</span><span class="l-en" lang="en">' + en + '</span>';
    el.hidden = false;
  })();
</script>
<script>
  (function(){
    var params = new URLSearchParams(location.search);
    var d = params.get('date');
    if (d && /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(d)) {
      location.replace('d/' + d + '.html');
      return;
    }

    var tabs = document.querySelectorAll('#tabs .tab');
    if (!tabs.length) return;
    tabs.forEach(function(t){
      t.addEventListener('click', function(){
        tabs.forEach(function(x){
          x.classList.remove('on');
          x.setAttribute('aria-selected', 'false');
        });
        t.classList.add('on');
        t.setAttribute('aria-selected', 'true');
        var f = t.getAttribute('data-filter');
        var on = f !== 'all';
        // data-topic, no data-theme: <html data-theme> es el tema claro/oscuro
        // y con el selector anterior el filtro ocultaba la pagina entera.
        // Con filtro: se oculta la portada a tres columnas y la rejilla enseña
        // TODAS las señales que casan (tambien las de portada y En breve).
        var deck = document.getElementById('deck');
        if (deck) deck.classList.toggle('filtered', on);
        var visBelow = 0;
        var visCtx = 0;
        document.querySelectorAll('[data-topic]').forEach(function(c){
          var show;
          if (f === 'all')            show = true;
          else if (f === '__new__')   show = c.getAttribute('data-new') === '1';
          else                        show = c.getAttribute('data-topic') === f;
          c.style.display = show ? '' : 'none';
          if (show) {
            if (c.classList.contains('card')) visBelow++;
            else if (c.classList.contains('cx')) visCtx++;
          }
        });
        var below = document.querySelector('.below');
        if (below) below.classList.toggle('filter-empty', on && visBelow === 0);
        var ctxBlock = document.getElementById('ctx-block');
        if (ctxBlock) ctxBlock.classList.toggle('filter-empty', on && visCtx === 0);
        var opening = document.querySelector('.opening');
        if (opening) opening.classList.toggle('filter-empty', on && visCtx === 0);
      });
    });

    document.addEventListener('click', function(ev){
      var a = ev.target && ev.target.closest && ev.target.closest('a.watch-link');
      if (!a) return;
      var deck = document.getElementById('deck');
      if (deck && deck.classList.contains('filtered')) {
        var allTab = document.querySelector('#tabs .tab[data-filter="all"]');
        if (allTab) allTab.click();
      }
    });
  })();
</script>
{{ theme_js }}
</body>
</html>
""")


TICKER_COMPANIES = ("NVDA", "AMZN", "MSFT", "AAPL", "ANT")


def _ticker_quotes(market) -> list[dict]:
    """Banda de mercados: macro + las cuatro grandes, con el mismo formato."""
    from src.market import _generate_sparkline, investing_url
    if not isinstance(market, dict):
        return []
    out = []
    for m in (market.get("macro") or []):
        if not isinstance(m, dict):
            continue
        row = dict(m)
        if not row.get("sparkline_svg") and row.get("sparkline_points"):
            row["sparkline_svg"] = _generate_sparkline(row.get("sparkline_points") or [], positive=bool(row.get("positive")))
        if not row.get("url"):
            row["url"] = investing_url(row.get("key") or "", row.get("label") or "")
        out.append(row)
    by_ticker = {c.get("ticker"): c for c in (market.get("companies") or []) if isinstance(c, dict)}
    for t in TICKER_COMPANIES:
        c = by_ticker.get(t)
        if not c:
            continue
        out.append({
            "label": (c.get("name") or t).replace(" Corp.", "").replace(".com Inc.", "").replace(" Inc.", ""),
            "price_str": c.get("price_str"), "change_str": c.get("change_str"),
            "positive": c.get("positive"), "available": c.get("available"),
            "sparkline_svg": _generate_sparkline(c.get("sparkline_points") or [], positive=bool(c.get("positive"))),
            "url": c.get("url") or investing_url(t, c.get("name") or ""),
        })
    return out


ALSO_MAX = 6  # medios listados en "Tambien en" antes de resumir con +N


def _watch_agenda(briefing, signals, results):
    """Prioritize the watch points of stories cited by the daily briefing."""
    agenda = []
    seen = {w["text"].strip().casefold() for w in results}
    english = briefing.get("watch_en") or []
    evidence = briefing.get("evidence") or {}
    watches = (briefing.get("watch") or [])[:3]
    ref_groups = []
    for i in range(len(watches)):
        ref_groups.append([
            {"url": ref["url"], "source": source_label(ref.get("source") or urlparse(ref["url"]).netloc)}
            for ref in evidence.get(f"watch.{i}", [])
            if isinstance(ref, dict) and _safe_url(ref.get("url")) != "#"
        ])
    citations = Counter(ref["url"] for refs in ref_groups for ref in refs)
    for i, (text, refs) in enumerate(zip(watches, ref_groups)):
        if not isinstance(text, str) or not text.strip() or text.strip().casefold() in seen:
            continue
        # A citation selects a story for the agenda, not evidence of a hit.
        # With multiple references or cards, retain the briefing's own wording.
        cited = []
        if len(refs) == 1 and citations[refs[0]["url"]] == 1:
            cited = [it for it in signals if refs[0]["url"] == (it.get("url") or it.get("link"))]
        anchor = f"watch-point-{i + 1}"
        text_en = english[i] if i < len(english) else ""
        original = text.strip().casefold()
        if len(cited) == 1 and cited[0]["watch_next"] and not cited[0].get("watch_anchor"):
            it = cited[0]
            if it["watch_next"].casefold() not in seen:
                it["watch_anchor"] = anchor
                text, text_en = it["watch_next"], it["watch_next_en"]
        seen.update((original, text.strip().casefold()))
        agenda.append({"anchor": anchor, "refs": refs, "text": text, "text_en": text_en})
    return agenda


def _enrich_cards(items):
    enriched = []
    for raw in (items or []):
        it = dict(raw)
        it["score"] = score_value(it)
        it["score_cls"] = score_tier(it["score"])
        it["theme_key"] = (it.get("strategic_theme") or it.get("primary") or "other").strip() or "other"
        it["theme_label"] = human_theme(it["theme_key"])
        it["measurement"] = measurement_context(raw)
        it["ev"] = evidence_badge(raw)
        it["display_title"] = display_title(it)
        raw_sw = strip_evidence_prefix(it.get("so_what") or it.get("why") or "")
        raw_summary = strip_evidence_prefix(it.get("summary") or "") if not it.get("so_what") else ""
        it["so_what"] = truncate_text(_dedup_subtitle(it["display_title"], raw_sw, raw_summary), 230)
        it["power_shift"] = truncate_text(strip_evidence_prefix(it.get("power_shift") or ""), 120)
        it["watch_next"] = (it.get("watch_next") or "").strip()
        it["theme_label_en"] = THEME_LABELS_EN.get(it["theme_key"], "Other signals")
        # Sin titular traducido, el original del feed (casi siempre en inglés).
        it["title_en"] = clamp_headline(
            strip_evidence_prefix(it.get("title_en") or "") or strip_evidence_prefix(it.get("title") or "")
        )
        raw_sw_en = strip_evidence_prefix(it.get("so_what_en") or "")
        it["so_what_en"] = truncate_text(_dedup_subtitle(it["title_en"], raw_sw_en), 230)
        it["power_shift_en"] = truncate_text(strip_evidence_prefix(it.get("power_shift_en") or ""), 120)
        it["watch_next_en"] = (it.get("watch_next_en") or "").strip()
        # La consecuencia editorial también es impacto; conservar su grado de certeza.
        it["impact_from_consequence"] = bool(
            not it["power_shift"] and it.get("evidence") and it["so_what"] and it["so_what"] != UNVERIFIED[0]
        )
        it["impact"] = it["so_what"] if it["impact_from_consequence"] else it["power_shift"]
        it["impact_en"] = it["so_what_en"] if it["impact_from_consequence"] else it["power_shift_en"]
        it["ents"] = item_entities(it)
        it["source_label"] = source_label(it.get("source", ""))
        it["logo"] = source_logo_url(it.get("source", ""), it.get("url") or it.get("link") or "")
        # "Nuevo" = no aparecio en los snapshots de los ultimos 5 dias.
        # `is_repeat` ya lo calcula apply_novelty_penalty comparando URL
        # canonica y huella del titular contra el historico.
        it["is_new"] = not bool(it.get("is_repeat"))

        # "Tambien en": el resto de medios que cuentan el mismo suceso. Los
        # fusionados tras el LLM traen enlace; los del dedup de ingest, solo nombre.
        also, seen_also = [], set()
        for rel in (it.get("related") or []):
            label = source_label(rel.get("source", "")) if isinstance(rel, dict) else ""
            url = _safe_url(rel.get("url", "")) if isinstance(rel, dict) else "#"
            if label and label not in seen_also:
                seen_also.add(label)
                also.append({"label": label, "url": "" if url == "#" else url})
        for src in (it.get("other_sources") or []):
            label = source_label(src) if isinstance(src, str) else ""
            if label and label not in seen_also:
                seen_also.add(label)
                also.append({"label": label, "url": ""})
        it["also"] = also[:ALSO_MAX]
        it["also_more"] = max(0, len(also) - ALSO_MAX)

        # La portada generada sirve dos veces: como imagen si el item no trae
        # ninguna, y como respaldo en cliente (data-fb) si la remota no carga.
        # La portada lleva el tema escrito, asi que hay una por idioma.
        fallback, fallback_en = item_fallback_image(it), item_fallback_image(it, "en")
        img = (it.get("image_url") or "").strip()
        it["cover_only"] = not img or not img.startswith(("http://", "https://"))
        it["image_url"] = fallback if it["cover_only"] else img
        it["fallback_image"] = "" if it["cover_only"] else fallback
        it["cover_en"] = fallback_en
        enriched.append(it)

    return enriched


def _story_keys(item):
    urls = [source_url(item)] + [source_url(ref) for ref in item.get("related") or [] if isinstance(ref, dict)]
    titles = [strip_evidence_prefix(item.get(key, "")).casefold() for key in ("title", "title_es", "title_en")]
    return {canonical_url(url) for url in urls if url} | {title for title in titles if title}


def _archive_cards(history, date, current, needed):
    if needed <= 0 or not history:
        return []
    seen = {key for item in current for key in _story_keys(item)}
    chosen = []
    for edition in reversed(history):
        day = edition.get("date") or ""
        if edition.get("degraded") or not day or day >= date:
            continue
        for item in edition.get("items") or []:
            if item.get("layer") != "signal" or item.get("is_repeat") or not source_url(item):
                continue
            if item.get("evidence_kind") not in ("confirmed", "reported") or not item.get("title_es"):
                continue
            if not (item.get("evidence") or {}).get("quote"):
                continue
            keys = _story_keys(item)
            if keys & seen:
                continue
            chosen.append(dict(item, archive_date=day))
            seen.update(keys)
            if len(chosen) == needed:
                return _enrich_cards(chosen)
    return _enrich_cards(chosen)


def render_index(items, briefing=None, snapshot=None, market=None, nav="daily", root="", archive=None, history=()):
    briefing = briefing or {}
    snapshot = snapshot or {}

    if market is None:
        try:
            from src.market import get_market_overview
            market = get_market_overview()
        except Exception:
            market = {}

    enriched = _enrich_cards(items)
    ev_rank = {"confirmed": 4, "reported": 3, "inference": 2, "speculation": 1, "unverified": 0}
    enriched.sort(
        key=lambda x: (
            x.get("score", 0),
            ev_rank.get(((x.get("ev") or {}).get("kind") or x.get("evidence_kind") or ""), 3),
            int(x.get("llm_score") or 0),
        ),
        reverse=True,
    )

    signals = [it for it in enriched if it.get("layer") == "signal"]
    context = [it for it in enriched if it.get("layer") == "context"]
    if not signals and not context:
        signals = enriched  # modo degradado: sin veredictos, todo a la capa principal

    # El sort por score devolvería un repeat al hero. El radar es "qué cambió hoy".
    signals = demote_repeats_from_lead(signals, LEAD_SLOT_COUNT)

    hero = signals[0] if signals else None
    if hero is not None:
        from src.cover import motif_watermark_svg, theme_accent
        h_seed = f"{hero.get('title') or hero.get('title_es') or ''}|{hero.get('url') or hero.get('link') or ''}"
        hero["accent"] = theme_accent(hero["theme_key"])
        hero["watermark_svg"] = motif_watermark_svg(hero["theme_key"], h_seed)

    # La portada vive fuera de la cuadrícula. Completar primero con contexto de hoy.
    count = max(0, len(signals) - 1)
    complete_rows = (count + len(context)) // 3
    target = max(6, count + (-count % 3), complete_rows * 3)
    needed = target - count
    past = _archive_cards(history, snapshot.get("date") or "", enriched, needed - len(context))
    take = min(needed, len(context)) if past or count + len(context) >= target else 0
    grid_cards = signals + context[:take] + past

    # Tabs de tema estilo Discover: solo los temas presentes hoy, con contador.
    visible = signals + context
    tab_counter = Counter(it["theme_key"] for it in visible)
    theme_tabs = [
        {"key": k, "label": human_theme(k), "label_en": THEME_LABELS_EN.get(k, "Other signals"), "count": c}
        for k, c in tab_counter.most_common()
    ]
    if len(theme_tabs) < 2:
        theme_tabs = []  # con un solo tema, las tabs no aportan nada

    # Tab "Nuevo": primeras apariciones. Solo se ofrece si discrimina algo;
    # si todo es nuevo (o nada lo es) el filtro no informaria.
    n_new = sum(1 for it in visible if it.get("is_new"))
    show_new_tab = 0 < n_new < len(visible)

    memory = snapshot.get("memory") or {}
    watch_results = [
        w for w in (memory.get("watch_resolved") or [])
        if w.get("status") == "hit" and w.get("text") and (w.get("evidence") or "").strip()
        and _safe_url(w.get("evidence_url")) != "#"
    ]
    watch_agenda = _watch_agenda(briefing, signals, watch_results)

    thesis = strip_evidence_prefix(briefing.get("thesis") or "")
    if not thesis:
        sigs = briefing.get("signals") or []
        if sigs:
            thesis = strip_evidence_prefix(sigs[0])
        elif signals:
            thesis = signals[0]["display_title"]
        else:
            thesis = "Sin movimientos de frontera hoy."

    health = snapshot.get("source_health") or {}
    dead = health.get("dead") or []

    raw_updates = (memory.get("followups") or {}).get("updates", [])[:3]
    visit_updates = []
    for u in raw_updates:
        if not isinstance(u, dict):
            continue
        clean_u = dict(u)
        for side in ("before", "after"):
            part = clean_u.get(side)
            if isinstance(part, dict):
                cp = dict(part)
                for k in ("es", "en"):
                    if isinstance(cp.get(k), str):
                        cp[k] = clamp_headline(strip_evidence_prefix(cp[k]), 140)
                clean_u[side] = cp
        visit_updates.append(clean_u)

    return TEMPLATE.render(
        generated_at=snapshot.get("date") or radar_today_str(),
        activity=snapshot.get("activity") or {"label": "ACTIVO", "class": "active"},
        thesis=thesis,
        grid_cards=grid_cards,
        ticker_quotes=_ticker_quotes(market),
        pulse=snapshot.get("pulse") or {},
        has_grid_cards=len(grid_cards) > int(bool(hero)),
        key_signals=[clamp_headline(strip_evidence_prefix(x), 180) for x in (briefing.get("signals") or []) if isinstance(x, str)][:3],
        key_signals_en=[clamp_headline(strip_evidence_prefix(x), 180) for x in (briefing.get("signals_en") or []) if isinstance(x, str)][:3],
        top_entities=[e.get("entity") for e in (snapshot.get("top_entities") or []) if isinstance(e, dict) and e.get("entity")][:6],
        hero=hero,
        context=context[take:],
        theme_tabs=theme_tabs,
        show_new_tab=show_new_tab,
        n_new=n_new,
        n_signals=len(signals),
        n_context=len(context),
        n_dropped=snapshot.get("dropped_noise", 0),
        degraded=bool(snapshot.get("degraded")),
        visit_updates=visit_updates,
        watch_agenda=watch_agenda,
        watch_results=watch_results,
        sources_alive=health.get("alive", 0),
        sources_total=health.get("configured", 0),
        sources_dead=", ".join(dead[:4]) if dead else "",
        nav=nav or "daily",
        root=root or "",
        archive=archive,
        html_attrs=Markup(HTML_ATTRS),
        brand_head=Markup(BRAND_HEAD),
        seo=seo_head("RADAR.AI · Radar diario de la carrera hacia la AGI" if not archive else f"RADAR.AI · Edición del {snapshot.get('date') or ''}",
                     path="" if not archive else f"d/{snapshot.get('date') or ''}.html"),
        credits=brand_credits(),
        thesis_en=strip_evidence_prefix(briefing.get("thesis_en") or ""),
        activity_en=ACTIVITY_EN.get(str((snapshot.get("activity") or {}).get("label") or ""), ""),
        brand_css=Markup(BRAND_CSS),
        brand_header=brand_header(nav or "daily", root or ""),
        theme_js=Markup(THEME_JS),
        x_layer=snapshot.get("x_layer") or (snapshot.get("source_health") or {}).get("x") or {},
    )
