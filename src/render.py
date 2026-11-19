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


def display_title(item: dict) -> str:
    """Prefiere el titular reescrito por el LLM: los originales llegan sucios."""
    t = clean_text(item.get("title_es") or "")
    if not t:
        t = clean_text(item.get("title") or "")
    return t or "(sin titulo)"


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
  .wrap{max-width:1500px;margin:0 auto;padding:18px 24px 80px}
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
  .tq{flex:0 0 210px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:2px 6px;align-items:center;padding:8px 10px;border:1px solid var(--ink);background:var(--card-2);min-width:0}
  .tq-n{grid-column:1/-1;font:600 10.5px var(--f-mono);color:var(--muted);text-transform:uppercase}
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

  .movers{list-style:none;margin:0;padding:0}
  .movers li{display:grid;grid-template-columns:1fr auto;gap:4px 8px;align-items:baseline;padding:0 0 9px;margin-bottom:9px;border-bottom:1px dashed var(--line)}
  .movers li:last-child{padding-bottom:0;margin-bottom:0;border-bottom:none}
  .mv-n{font:700 14.5px var(--f-head)}
  .mv-t{font:700 10.5px var(--f-mono);color:var(--muted);text-transform:uppercase}
  .mv-t.t-up,.mv-t.t-new{color:var(--open)} .mv-t.t-down{color:var(--bad)}
  .mv-bar{grid-column:1/-1;height:8px;border:1px solid var(--ink);background:var(--card-2)}
  .mv-bar i{display:block;height:100%;background:var(--orange)}

  /* -- Portada (Hero adaptativo + Editorial estrecho y alineado) -- */
  .opening{display:grid;grid-template-columns:minmax(0,1fr) 365px;gap:22px;align-items:stretch}
  .deck.filtered .opening{display:none}

  .rail{display:flex;flex-direction:column;height:100%;min-width:0;background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow);padding:16px 18px}
  .rail-h{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:0 0 10px;padding:0 0 7px;border-bottom:2px solid var(--ink);
          font:700 11.5px/1.2 var(--f-mono);text-transform:uppercase;letter-spacing:.08em}
  .rail-h>span:first-child{display:flex;align-items:center;gap:8px}
  .rail-h>span:first-child::before{content:"";width:10px;height:10px;background:var(--orange);border:2px solid var(--ink);flex:0 0 auto}
  .rail-h .lbl{font:400 10px var(--f-mono);color:var(--muted);letter-spacing:.04em;white-space:nowrap}
  .rail-title{font:700 22px/1.08 var(--f-head);text-transform:uppercase;letter-spacing:-.028em;margin:2px 0 8px}
  .rail-thesis{font:500 14px/1.48 var(--f-head);margin:0 0 14px}
  .keys{margin:0 0 12px;padding:0;list-style:none;counter-reset:k}
  .keys li{counter-increment:k;display:grid;grid-template-columns:24px 1fr;gap:7px;padding:0 0 7px;margin-bottom:7px;border-bottom:1px dashed var(--line);font-size:13px;line-height:1.42}
  .keys li:last-child{margin-bottom:0;border-bottom:none;padding-bottom:0}
  .keys li::before{content:counter(k,decimal-leading-zero);font:700 10.5px/1.65 var(--f-mono);color:var(--orange-ink)}
  .rail-foot{margin-top:auto;padding-top:12px;display:flex;flex-direction:column;gap:12px}
  .onradar{margin:0;padding:10px 12px;background:var(--card-2);border:2px solid var(--ink);box-shadow:inset 5px 0 0 var(--orange)}
  .onradar .rail-h{margin-bottom:6px;padding-bottom:5px;border-bottom-width:1.5px;font-size:10.5px}
  .onradar p{font-size:12.8px;line-height:1.44;margin:0}
  .figures{border-top:2px solid var(--ink);padding-top:10px;display:flex;flex-direction:column;gap:7px}
  .fig-row{display:flex;align-items:baseline;justify-content:space-between;gap:8px;flex-wrap:wrap}
  .fig-count{font:700 18px/1 var(--f-head);letter-spacing:-.03em}
  .fig-note{font:400 10.5px/1.35 var(--f-mono);color:var(--muted)}
  .figures .ents{margin-top:0;gap:5px}
  .figures .ent{font-size:10px;padding:2px 5px}

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
  .lead-media .hero-img{display:block;width:100%;aspect-ratio:21/9;max-height:320px;object-fit:cover;border-bottom:0;transition:transform .35s ease}
  .lead-media:hover .hero-img{transform:scale(1.02)}
  .lead-media-bar{position:absolute;top:14px;left:16px;right:16px;z-index:2;display:flex;align-items:center;gap:8px;flex-wrap:wrap;pointer-events:none}
  .lead-media-bar .tag{background:var(--lead-accent,var(--orange));color:#121211;border:2px solid #121211;box-shadow:2px 2px 0 rgba(18,18,17,.65)}
  .lead-media-bar .score{font-size:12.5px;padding:5px 9px}
  .lead-body{position:relative;z-index:2;flex:1;display:flex;flex-direction:column;padding:20px 26px 20px}
  .lead-top{display:none;align-items:center;gap:8px;flex-wrap:wrap;margin:0 0 18px}
  .lead-top .tag{background:var(--lead-accent,var(--orange));color:#121211}
  .lead-top .score{font-size:12.5px;padding:5px 9px}
  .lead .hero-title{font:700 clamp(25px,2.45vw,38px)/1.08 var(--f-head);letter-spacing:-.032em;margin:0 0 12px}
  .lead .sw{font-size:clamp(15px,1.15vw,17.5px);line-height:1.52;color:var(--muted);margin:0 0 16px;max-width:68ch}

  .lead-intel{display:grid;gap:10px;margin:0 0 14px}
  @media(min-width:740px){.lead-intel.two{grid-template-columns:1fr 1fr;gap:12px}}
  .intel-box{padding:11px 14px;background:var(--card-2);border:1.5px solid var(--line);display:flex;flex-direction:column;gap:5px}
  .intel-box.pw{border-left:3.5px solid var(--orange)}
  .intel-box.wn{border-left:3.5px solid var(--lime)}
  .intel-k{display:inline-flex;align-self:flex-start;font:700 10px/1 var(--f-mono);text-transform:uppercase;letter-spacing:.06em;
           padding:3px 6px;border:1px solid var(--ink)}
  .intel-box.pw .intel-k{background:var(--orange);color:#121211}
  .intel-box.wn .intel-k{background:var(--lime);color:#121211}
  .intel-v{font-size:13.5px;line-height:1.45}

  .lead-foot{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-top:auto;padding-top:16px;border-top:1px dashed var(--line)}
  .lead-foot-l{display:flex;align-items:center;gap:10px;flex-wrap:wrap;min-width:0}
  .lead-foot-l .ents{margin-top:0}
  .lead-cta{display:inline-flex;align-items:center;gap:7px;font:700 11.5px/1 var(--f-mono);text-transform:uppercase;letter-spacing:.04em;
            padding:9px 14px;background:var(--lime);color:#121211;border:2px solid var(--ink);box-shadow:var(--shadow-sm);
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
  .lead.lead-dossier .lead-body{padding:28px 34px 24px}
  .lead.lead-dossier .lead-top .tag{border-color:#E8E7E1}
  .lead.lead-dossier .lead-top .badge-new{border-color:#E8E7E1}
  .lead.lead-dossier .hero-title{font-size:clamp(32px,3.5vw,54px);line-height:1.03;color:#FFFFFF;max-width:25ch;margin-bottom:18px}
  .lead.lead-dossier .hero-title a:hover{text-decoration-color:var(--lead-accent,var(--lime))}
  .lead.lead-dossier .sw{color:#D4D3CC;font-size:clamp(16px,1.25vw,19px);line-height:1.54;margin-bottom:26px;max-width:58ch}
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
  .below .grid{grid-template-columns:repeat(3,minmax(0,1fr))}
  .deck:not(.filtered) .dup,.deck:not(.filtered) .h-filtered,.deck.filtered .h-all{display:none}
  .deck:not(.filtered) .below.no-rest{display:none}
  .deck.filtered .below{margin-top:0;padding-top:0;border-top:0}

  .insights{display:grid;grid-template-columns:minmax(0,1.75fr) minmax(280px,1fr);gap:22px;margin-top:34px;align-items:start}
  .insights.single{grid-template-columns:minmax(0,1fr)}
  .companies{margin-top:0}
  .companies .company-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 28px}
  .memory{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:22px;margin-top:34px;align-items:start}

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
  @media (prefers-color-scheme: dark){
    :root:not([data-theme="light"]) .score.s-80{background:rgba(255,87,34,.22);color:#FFA07A;border-color:#EA580C}
    :root:not([data-theme="light"]) .score.s-70{background:#232320;color:var(--muted);border-color:var(--line)}
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
  .card-title{margin:0;font:700 19px/1.2 var(--f-head);letter-spacing:-.01em}
  .card .sw{font-size:14px;line-height:1.5;color:var(--muted);
            display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
  .card-foot{margin-top:auto;padding-top:10px;border-top:1px dashed var(--line);display:grid;gap:6px}
  .card-foot .fact{font-size:12px;line-height:1.4}
  .card-foot .fact .v{min-width:0;flex:1;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}

  /* -- Contexto -- */
  .section-h{margin:34px 0 14px}
  .section-h h2{margin:0}
  .ctx-block .section-h{display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap}
  .sec-sub{margin:0;font:400 11.5px var(--f-mono);color:var(--muted);text-transform:uppercase}
  .ctx{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}
  .cx{display:flex;flex-direction:column;gap:8px;padding:14px 16px;background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow-sm)}
  .cx .meta-row{margin-bottom:0}
  .cx-tag{display:inline-block;font:700 10px/1 var(--f-mono);text-transform:uppercase;padding:3px 6px;border:1px solid var(--ink);background:var(--card-2);color:var(--text);flex-shrink:0}
  .cx-t{margin:0;font:700 16px/1.3 var(--f-head);letter-spacing:-.01em}
  .cx-w{font-size:13.5px;color:var(--muted);line-height:1.48;margin:0;
        display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}

  .empty{padding:40px 26px;text-align:center;border:2px dashed var(--ink);background:var(--card)}
  .empty .big{font:700 20px var(--f-head);margin-bottom:8px;text-transform:uppercase}
  .empty .sub{font-size:14px;color:var(--muted);max-width:52ch;margin:0 auto;line-height:1.6}

  /* -- Sidebar -- */
  .sidebar{display:grid;gap:22px;position:sticky;top:16px}
  .widget{background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow);padding:14px 16px}
  .widget-title{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:-14px -16px 12px;
                padding:10px 16px;border-bottom:2px solid var(--ink);background:var(--card-2)}
  .widget-title>span:first-child{display:flex;align-items:center;gap:9px;font:700 12px/1.2 var(--f-mono);text-transform:uppercase;letter-spacing:.06em}
  .widget-title>span:first-child::before{content:"";width:10px;height:10px;background:var(--orange);border:2px solid var(--ink)}
  .widget-title .lbl{font:400 10px var(--f-mono);color:var(--muted);text-transform:uppercase}

  .market-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
  .m-box{background:var(--card-2);border:1px solid var(--ink);padding:9px 10px}
  .m-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px}
  .m-lbl{font:600 11px var(--f-mono);text-transform:uppercase;color:var(--muted)}
  .m-chg{font:700 11px var(--f-mono)}
  .m-chg.pos,.comp-chg.pos{color:var(--open)} .m-chg.neg,.comp-chg.neg{color:var(--bad)}
  .m-chg.na,.comp-chg.na,.comp-price.na{color:var(--muted);font-weight:400}
  .m-price{font:700 14px var(--f-mono);margin-bottom:4px;font-variant-numeric:tabular-nums}
  .m-nodata{opacity:.55}
  .spark{width:100%;height:22px;display:block}
  .spark.pos polyline{stroke:var(--open)} .spark.neg polyline{stroke:var(--bad)}

  .comp-item{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:8px 0;border-bottom:1px dashed var(--line)}
  .comp-item:last-child{border-bottom:none;padding-bottom:0}
  .comp-info{display:flex;align-items:center;gap:9px;min-width:0}
  .comp-logo{width:24px;height:24px;padding:2px;flex-shrink:0;background:var(--logo-bg);border:1px solid var(--line)}
  .comp-name{font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .comp-ticker{font:400 10px var(--f-mono);color:var(--muted)}
  .comp-val{text-align:right;flex-shrink:0}
  .comp-price{font:700 12px var(--f-mono);font-variant-numeric:tabular-nums}
  .comp-chg{font:700 10.5px var(--f-mono)}

  .wr,.thr,.mv,.rk{padding:8px 0;border-bottom:1px dashed var(--line)}
  .wr:last-child,.thr:last-child,.mv:last-child,.rk:last-child{border-bottom:none;padding-bottom:0}
  .wr{display:flex;gap:10px;align-items:flex-start}
  .wr-ic{font:700 12px/1.5 var(--f-mono);flex-shrink:0}
  .wr.hit .wr-ic{color:var(--open)} .wr.open .wr-ic{color:var(--muted)}
  .wr-t{font-size:13px;line-height:1.5}
  .wr.open .wr-t{color:var(--muted)}
  .wr-ev{font-size:12px;color:var(--open);margin-top:3px;line-height:1.4}
  .thr{display:flex;gap:11px;align-items:baseline}
  .thr-d{font:700 10px var(--f-mono);flex-shrink:0;padding:3px 5px;border:2px solid var(--ink);background:var(--ink);color:var(--paper)}
  .thr-t{font-size:13px;font-weight:600}
  .thr-l{font-size:12px;color:var(--muted);margin-top:2px;line-height:1.4}
  .mv{display:flex;gap:8px;align-items:center;font-size:12.5px;flex-wrap:wrap}
  .mv-b{font:700 9.5px/1 var(--f-mono);text-transform:uppercase;padding:3px 5px;border:1px solid var(--ink);flex-shrink:0}
  .mv-b.new{background:var(--lime);color:#121211}
  .mv-b.ret{background:#FBBF24;color:#121211}
  .mv-b.str{background:var(--orange);color:#121211}
  .mv .nm{font-weight:600}
  .mv .dt{color:var(--muted);font:400 10.5px var(--f-mono)}
  .none{font-size:12.5px;color:var(--muted);font-style:italic}
  .rk{font-size:13px;line-height:1.5}
  .rk::before{content:"!";display:inline-grid;place-content:center;width:16px;height:16px;margin-right:7px;
              font:700 10px var(--f-mono);background:#FBBF24;color:#121211;border:1px solid var(--ink);vertical-align:1px}
  .rk.w::before{content:"→";background:var(--lime)}

  footer{margin-top:56px;padding-top:14px;border-top:3px solid var(--ink);display:flex;justify-content:space-between;
         gap:16px;flex-wrap:wrap;font:400 12px var(--f-mono);color:var(--muted)}

  @media(max-width:1180px){
    .opening{grid-template-columns:minmax(0,1fr) 320px}
    .below .grid,.ctx{grid-template-columns:repeat(2,minmax(0,1fr))}
    .insights{grid-template-columns:1fr}
    .memory{grid-template-columns:1fr 1fr}
  }
  @media(max-width:920px){
    .opening{grid-template-columns:1fr}
  }
  @media(max-width:720px){
    .grid,.below .grid,.ctx{grid-template-columns:1fr}
    .tq{flex:0 0 170px}
    .pulse{grid-template-columns:1fr}
    .memory,.companies .company-list{grid-template-columns:1fr}
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
    {{ bi("<b>Modo degradado.</b> El análisis del LLM no está disponible hoy, así que el filtro de relevancia no se ha aplicado. Lo que ves está ordenado por heurística y puede contener ruido."|safe,
          "<b>Degraded mode.</b> The LLM analysis is unavailable today, so the relevance filter was not applied. Items are ranked heuristically and may include noise."|safe) }}
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
  <section class="opening">

    <!-- Portada #01 (adaptativa foto/dossier) a altura completa junto al Editorial -->
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
        {% if hero.so_what %}<div class="sw">{{ bi(hero.so_what, hero.so_what_en) }}</div>{% endif %}
        {% if hero.power_shift or hero.watch_next %}
        <div class="lead-intel {% if hero.power_shift and hero.watch_next %}two{% endif %}">
          {% if hero.power_shift %}
          <div class="intel-box pw"><span class="k intel-k">{{ bi("Impacto","Impact") }}</span><span class="intel-v">{{ bi(hero.power_shift, hero.power_shift_en) }}</span></div>
          {% endif %}
          {% if hero.watch_next %}
          <div class="intel-box wn"><span class="k intel-k">{{ bi("Vigilar","Watch") }}</span><span class="intel-v">{{ bi(hero.watch_next, hero.watch_next_en) }}</span></div>
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
            {% if hero.ents %}
            <div class="ents">{% for e in hero.ents[:4] %}<span class="ent">{{ e }}</span>{% endfor %}</div>
            {% endif %}
          </div>
          <a class="lead-cta" href="{{ (hero.url or hero.link)|safe_url }}" target="_blank" rel="noopener noreferrer">{{ bi("Leer fuente ↗","Read source ↗") }}</a>
        </div>
      </div>
    </article>

    <!-- Editorial -->
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
        {% if watch_list %}
        <div class="onradar">
          <div class="rail-h"><span>{{ bi("En el radar","On the radar") }}</span></div>
          <p>{{ bi(watch_list[0], watch_en[0] if watch_en else "") }}</p>
        </div>
        {% endif %}
        <div class="figures">
          <div class="fig-row">
            <strong class="fig-count">{{ n_signals + n_context }}</strong>
            <span class="fig-note">{{ n_signals }} {{ bi("señales","signals") }}{% if n_context %} · {{ n_context }} {{ bi("contexto","context") }}{% endif %} · {{ n_dropped }} {{ bi("descartadas","dropped") }}</span>
          </div>
          {% if top_entities %}<div class="ents">{% for e in top_entities %}<span class="ent">{{ e }}</span>{% endfor %}</div>{% endif %}
        </div>
      </div>
    </aside>
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
      <div class="ticker-h"><strong>{{ bi("Mercados","Markets") }}</strong><span>{{ bi("Último cierre · no es tiempo real","Last close · not real time") }}</span></div>
      <div class="ticker-view">
        <div class="ticker-track" style="--n:{{ ticker_quotes|length }}">
          {% for copy in (0, 1) %}
          <div class="ticker-q"{% if copy %} aria-hidden="true"{% endif %}>
            {% for m in ticker_quotes %}
            <div class="tq{% if not m.available %} m-nodata{% endif %}">
              <span class="tq-n">{{ m.label }}</span>
              <span class="tq-p">{{ m.price_str }}</span>
              {% if m.available %}<span class="m-chg {% if m.positive %}pos{% else %}neg{% endif %}">{{ m.change_str }}</span>{% else %}<span class="m-chg na">n/d</span>{% endif %}
              {{ m.sparkline_svg|safe }}
            </div>
            {% endfor %}
          </div>
          {% endfor %}
        </div>
      </div>
    </section>
    {% endif %}
  </div>
  {% endif %}

  {% if not hero and not stream %}
      <div class="empty">
        <div class="big">{{ bi("Hoy no ha pasado nada que mueva la aguja.","Nothing moved the needle today.") }}</div>
        <div class="sub">
          {{ bi("El filtro de relevancia descartó todo lo ingerido por irrelevante. Un día sin señal también es información: significa que la carrera frontier no se movió.",
                "The relevance filter dropped all ingested items as noise. A day without signals is also information: the frontier race did not move.") }}
        </div>
      </div>
      {% endif %}

  <!-- Resto de señales (#2..#12). Con un filtro activo se incluye tambien la portada. -->
  {% if signals %}
  <section class="below{% if not rest %} no-rest{% endif %}">
    <div class="section-h h-all"><h2 class="sec">{{ bi("Más allá del titular","Beyond the headline") }}</h2></div>
    <div class="section-h h-filtered"><h2 class="sec">{{ bi("Señales de esta sección","Signals in this section") }}</h2></div>
    <div class="grid">
      {% for it in signals %}{% set dup = loop.index0 < lead_n %}
        <article class="card{% if dup %} dup{% endif %}" data-topic="{{ it.theme_key }}" data-new="{{ 1 if it.is_new else 0 }}">
          <a href="{{ (it.url or it.link)|safe_url }}" target="_blank" rel="noopener noreferrer">
            {% if it.cover_only %}<img class="card-img l-es" src="{{ it.image_url }}" alt="" loading="lazy"/><img class="card-img l-en" src="{{ it.cover_en }}" alt="" loading="lazy"/>
            {% else %}<img class="card-img" src="{{ it.image_url }}" data-fb="{{ it.fallback_image }}" data-fb-en="{{ it.cover_en }}" alt="" loading="lazy" referrerpolicy="no-referrer"/>{% endif %}
          </a>
          <div class="card-body">
            <div class="meta-row">
              {% if it.is_new %}<span class="badge-new">{{ bi("Nuevo","New") }}</span>{% endif %}
              <span class="src"><img src="{{ it.logo }}" alt="" loading="lazy"/>{{ it.source_label }}</span>
              {% if it.other_sources %}<span class="multi">+{{ it.other_sources|length }}</span>{% endif %}
              <span class="score {{ it.score_cls }}">{{ it.score }}/100</span>
            </div>
            <h3 class="card-title">
              <a href="{{ (it.url or it.link)|safe_url }}" target="_blank" rel="noopener noreferrer">{{ bi(it.display_title, it.title_en) }}</a>
            </h3>
            {% if it.so_what %}<div class="sw">{{ bi(it.so_what, it.so_what_en) }}</div>{% endif %}
            {% if it.also %}
            <div class="also">{{ bi("También en:","Also in:") }}
              {% for a in it.also %}{% if a.url %}<a href="{{ a.url }}" target="_blank" rel="noopener noreferrer">{{ a.label }}</a>{% else %}<span>{{ a.label }}</span>{% endif %}{% if not loop.last %} · {% endif %}{% endfor %}{% if it.also_more %} · +{{ it.also_more }}{% endif %}
            </div>
            {% endif %}
            {% if it.power_shift or it.watch_next %}
            <div class="card-foot">
              {% if it.power_shift %}
              <div class="fact pw"><span class="k">{{ bi("Impacto","Impact") }}</span><span class="v">{{ bi(it.power_shift, it.power_shift_en) }}</span></div>
              {% endif %}
              {% if it.watch_next %}
              <div class="fact wn"><span class="k">{{ bi("Vigilar","Watch") }}</span><span class="v">{{ bi(it.watch_next, it.watch_next_en) }}</span></div>
              {% endif %}
            </div>
            {% endif %}
          </div>
        </article>
      {% endfor %}
    </div>
  </section>
  {% endif %}

      {% if context %}
      <section class="ctx-block" id="ctx-block">
        <div class="section-h">
          <h2 class="sec">{{ bi("Contexto","Context") }}</h2>
          <p class="sec-sub">{{ bi("En segundo plano · Señales complementarias que completan la foto","In the background · Supporting signals shaping the backdrop") }}</p>
        </div>
        <div class="ctx">
          {% for it in context %}
          <article class="cx" data-topic="{{ it.theme_key }}" data-new="{{ 1 if it.is_new else 0 }}">
            <div class="meta-row">
              <span class="cx-tag">{{ bi(it.theme_label, it.theme_label_en) }}</span>
              <span class="src"><img src="{{ it.logo }}" alt="" loading="lazy"/>{{ it.source_label }}</span>
              <span class="score {{ it.score_cls }}">{{ it.score }}/100</span>
            </div>
            <h3 class="cx-t">
              <a href="{{ (it.url or it.link)|safe_url }}" target="_blank" rel="noopener noreferrer">{{ bi(it.display_title, it.title_en) }}</a>
            </h3>
            {% if it.so_what %}<div class="cx-w">{{ bi(it.so_what, it.so_what_en) }}</div>{% endif %}
          </article>
          {% endfor %}
        </div>
      </section>
      {% endif %}

  </div>

      {% if (market and market.companies) or movers %}
      <section class="insights{% if not (market and market.companies and movers) %} single{% endif %}">
        {% if market and market.companies %}
        <div class="widget companies">
          <div class="widget-title">
            <span>{{ bi("Empresas en tendencia","Trending companies") }}</span>
            <span class="lbl">AI & Semis</span>
          </div>
          <div class="company-list">
            {% for c in market.companies %}
            <div class="comp-item">
              <div class="comp-info">
                <img src="{{ c.logo }}" alt="" class="comp-logo" loading="lazy"/>
                <div>
                  <div class="comp-name">{{ c.name }}</div>
                  <div class="comp-ticker">{{ c.ticker }} · {{ c.exchange }}</div>
                </div>
              </div>
              <div class="comp-val">
                <div class="comp-price{% if not c.available %} na{% endif %}">{{ c.price_str }}</div>
                {% if c.available %}
                <div class="comp-chg {% if c.positive %}pos{% else %}neg{% endif %}">{{ c.change_str }}</div>
                {% else %}
                <div class="comp-chg na" title="Cotización no disponible en este run">n/d</div>
                {% endif %}
              </div>
            </div>
            {% endfor %}
          </div>
        </div>
        {% endif %}
        {% if movers %}
        <div class="widget">
          <div class="widget-title">
            <span>{{ bi("Quién mueve la carrera","Who moves the race") }}</span>
            <span class="lbl">{{ bi("Últimas ediciones","Recent editions") }}</span>
          </div>
          <ul class="movers">
            {% for m in movers %}
            <li><span class="mv-n">{{ m.entity }}</span>
              <span class="mv-t t-{{ m.trend }}" title="{{ m.trend }}">{% if m.trend == 'up' %}▲{% elif m.trend == 'down' %}▼{% elif m.trend == 'new' %}{{ bi("nuevo","new") }}{% else %}＝{% endif %}</span>
              <span class="mv-bar"><i style="width:{{ m.share }}%"></i></span></li>
            {% endfor %}
          </ul>
        </div>
        {% endif %}
      </section>
      {% endif %}

  <!-- Memoria del radar: lo que dijimos, lo que persiste, lo que viene -->
  <section class="memory">
      {% if watch_resolved %}
      <div class="widget">
        <div class="widget-title">
          <span>{{ bi("Vigilancia de ayer","Yesterday's watchlist") }}</span>
          <span class="lbl">{{ n_hits }}/{{ watch_resolved|length }} {{ bi("confirmadas","confirmed") }}</span>
        </div>
        {% for w in watch_resolved %}
        <div class="wr {{ w.status }}">
          <span class="wr-ic">{% if w.status == 'hit' %}✓{% else %}○{% endif %}</span>
          <div>
            <div class="wr-t">{{ bi(w.text, w.text_en) }}</div>
            {% if w.evidence %}<div class="wr-ev">→ {{ bi(w.evidence, w.evidence_en) }}</div>{% endif %}
          </div>
        </div>
        {% endfor %}
      </div>
      {% endif %}
      {% if threads or has_moves %}
      <div class="widget">
        <div class="widget-title">
          <span>{{ bi("Memoria del radar","Radar memory") }}</span>
          <span class="lbl">{{ bi("Continuidad","Continuity") }}</span>
        </div>
        {% for t in threads %}
        <div class="thr">
          <span class="thr-d">{{ bi("DÍA","DAY") }} {{ t.days }}</span>
          <div>
            <div class="thr-t">{{ bi(t.label, t.label_en) }}</div>
            {% if t.lead %}<div class="thr-l">{{ bi(t.lead, t.lead_en) }}</div>{% endif %}
          </div>
        </div>
        {% endfor %}
        {% if not threads %}
        <div class="none">{{ bi("Ninguna narrativa encadena 3 o más días.","No story has run for 3+ days.") }}</div>
        {% endif %}
        {% for e in deltas.new_entrants %}
        <div class="mv"><span class="mv-b new">{{ bi("Nuevo","New") }}</span><span class="nm">{{ e }}</span>
          <span class="dt">{{ bi("primera aparición","first appearance") }}</span></div>
        {% endfor %}
        {% for r in deltas.returning %}
        <div class="mv"><span class="mv-b ret">{{ bi("Vuelve","Back") }}</span><span class="nm">{{ r.entity }}</span>
          <span class="dt">{{ bi("tras " ~ r.silent_days ~ " días en silencio", "after " ~ r.silent_days ~ " silent days") }}</span></div>
        {% endfor %}
        {% for s in deltas.streaks %}
        <div class="mv"><span class="mv-b str">{{ bi("Racha","Streak") }}</span><span class="nm">{{ s.entity }}</span>
          <span class="dt">{{ bi(s.days ~ " días seguidos", s.days ~ " days in a row") }}</span></div>
        {% endfor %}
      </div>
      {% endif %}
      {% if risks or watch_list %}
      <div class="widget">
        <div class="widget-title">
          <span>{{ bi("Riesgos y vigilancia","Risks and watch") }}</span>
          <span class="lbl">{{ bi("Próximos días","Coming days") }}</span>
        </div>
        {% for r in risks %}<div class="rk">{{ bi(r, risks_en[loop.index0] if loop.index0 < risks_en|length else "") }}</div>{% endfor %}
        {% for w in watch_list %}<div class="rk w">{{ bi(w, watch_en[loop.index0] if loop.index0 < watch_en|length else "") }}</div>{% endfor %}
      </div>
      {% endif %}
  </section>

  {{ credits }}
  <footer>
    <span>{{ n_dropped }} {{ bi("items descartados por el filtro de relevancia","items dropped by the relevance filter") }}</span>
    <span>{{ sources_alive }}/{{ sources_total }} {{ bi("fuentes activas","active sources") }}{% if sources_dead %} · {{ bi("sin items","no items") }}: {{ sources_dead }}{% endif %}{% if x_layer and x_layer.status == 'killed' %} · X: kill switch{% elif x_layer and x_layer.status == 'disabled' %} · X: disabled{% elif x_layer and x_layer.status == 'ok' and x_layer.posts %} · X: {{ x_layer.posts }} posts{% endif %}</span>
  </footer>

</div>

<script>
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
      });
    });
  })();
</script>
{{ theme_js }}
</body>
</html>
""")


TICKER_COMPANIES = ("NVDA", "AMZN", "MSFT", "AAPL")


def _ticker_quotes(market) -> list[dict]:
    """Banda de mercados: macro + las cuatro grandes, con el mismo formato."""
    from src.market import _generate_sparkline
    if not isinstance(market, dict):
        return []
    out = []
    for m in (market.get("macro") or []):
        if not isinstance(m, dict):
            continue
        row = dict(m)
        if not row.get("sparkline_svg") and row.get("sparkline_points"):
            row["sparkline_svg"] = _generate_sparkline(row.get("sparkline_points") or [], positive=bool(row.get("positive")))
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
        })
    return out


LEAD_BLOCK = 1  # #1 Hero a altura completa en opening; #2..#12 van a la rejilla de cards completas
ALSO_MAX = 6  # medios listados en "Tambien en" antes de resumir con +N


def render_index(items, briefing=None, snapshot=None, market=None, nav="daily", root="", archive=None):
    briefing = briefing or {}
    snapshot = snapshot or {}

    if market is None:
        try:
            from src.market import get_market_overview
            market = get_market_overview()
        except Exception:
            market = {}

    enriched = []
    for raw in (items or []):
        it = dict(raw)
        it["score"] = score_value(it)
        it["score_cls"] = score_tier(it["score"])
        it["theme_key"] = (it.get("strategic_theme") or it.get("primary") or "other").strip() or "other"
        it["theme_label"] = human_theme(it["theme_key"])
        it["display_title"] = display_title(it)
        it["so_what"] = truncate_text(clean_text(it.get("so_what") or it.get("why") or ""), 230)
        it["power_shift"] = truncate_text(it.get("power_shift") or "", 120)
        it["watch_next"] = truncate_text(it.get("watch_next") or "", 120)
        it["theme_label_en"] = THEME_LABELS_EN.get(it["theme_key"], "Other signals")
        # Sin titular traducido, el original del feed (casi siempre en inglés).
        it["title_en"] = clean_text(it.get("title_en") or "") or clean_text(it.get("title") or "")
        it["so_what_en"] = truncate_text(clean_text(it.get("so_what_en") or ""), 230)
        it["power_shift_en"] = truncate_text(it.get("power_shift_en") or "", 120)
        it["watch_next_en"] = truncate_text(it.get("watch_next_en") or "", 120)
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

    enriched.sort(key=lambda x: x.get("score", 0), reverse=True)

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
    stream = signals[1:] if len(signals) > 1 else []

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
    deltas = memory.get("entity_deltas") or {}
    watch_resolved = memory.get("watch_resolved") or []
    threads = memory.get("threads") or []
    has_moves = bool(deltas.get("new_entrants") or deltas.get("returning") or deltas.get("streaks"))

    thesis = clean_text(briefing.get("thesis") or "")
    if not thesis:
        sigs = briefing.get("signals") or []
        if sigs:
            thesis = clean_text(sigs[0])
        elif signals:
            thesis = signals[0]["display_title"]
        else:
            thesis = "Sin movimientos de frontera hoy."

    health = snapshot.get("source_health") or {}
    dead = health.get("dead") or []

    return TEMPLATE.render(
        generated_at=snapshot.get("date") or radar_today_str(),
        activity=snapshot.get("activity") or {"label": "ACTIVO", "class": "active"},
        thesis=thesis,
        signals=signals,
        ticker_quotes=_ticker_quotes(market),
        pulse=snapshot.get("pulse") or {},
        movers=snapshot.get("movers") or [],
        rest=signals[LEAD_BLOCK:],
        lead_n=LEAD_BLOCK,
        key_signals=[clean_text(x) for x in (briefing.get("signals") or []) if isinstance(x, str)][:3],
        key_signals_en=[clean_text(x) for x in (briefing.get("signals_en") or []) if isinstance(x, str)][:3],
        top_entities=[e.get("entity") for e in (snapshot.get("top_entities") or []) if isinstance(e, dict) and e.get("entity")][:6],
        hero=hero,
        stream=stream,
        context=context,
        theme_tabs=theme_tabs,
        show_new_tab=show_new_tab,
        n_new=n_new,
        n_signals=len(signals),
        n_context=len(context),
        n_dropped=snapshot.get("dropped_noise", 0),
        degraded=bool(snapshot.get("degraded")),
        watch_resolved=watch_resolved,
        n_hits=sum(1 for w in watch_resolved if w.get("status") == "hit"),
        threads=threads,
        deltas=deltas,
        has_moves=has_moves,
        risks=(briefing.get("risks") or [])[:3],
        watch_list=(briefing.get("watch") or [])[:3],
        sources_alive=health.get("alive", 0),
        sources_total=health.get("configured", 0),
        sources_dead=", ".join(dead[:4]) if dead else "",
        market=market,
        nav=nav or "daily",
        root=root or "",
        archive=archive,
        html_attrs=Markup(HTML_ATTRS),
        brand_head=Markup(BRAND_HEAD),
        seo=seo_head("RADAR.IA · Radar diario de la carrera hacia la AGI" if not archive else f"RADAR.IA · Edición del {snapshot.get('date') or ''}",
                     path="" if not archive else f"d/{snapshot.get('date') or ''}.html"),
        credits=brand_credits(),
        thesis_en=clean_text(briefing.get("thesis_en") or ""),
        risks_en=(briefing.get("risks_en") or [])[:3],
        watch_en=(briefing.get("watch_en") or [])[:3],
        activity_en=ACTIVITY_EN.get(str((snapshot.get("activity") or {}).get("label") or ""), ""),
        brand_css=Markup(BRAND_CSS),
        brand_header=brand_header(nav or "daily", root or ""),
        theme_js=Markup(THEME_JS),
        x_layer=snapshot.get("x_layer") or (snapshot.get("source_health") or {}).get("x") or {},
    )
