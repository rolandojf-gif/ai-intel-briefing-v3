"""Marca compartida con moloch.sh y brain.gym: mismo sistema, misma familia.

Tokens copiados de esas dos webs (papel con cuadricula, tinta, naranja y lima,
bordes de 2px y sombras duras desplazadas), con su tema claro/oscuro/auto.
Diario, semanal y archivo cargan de aqui la cabecera, las fuentes y la base:
cambiar la marca es cambiar este fichero.

Las paginas antiguas usan nombres de variable propios (--bg, --txt, --dim,
--accent...). Se mapean a los tokens de marca para no reescribir cada regla.
"""
from __future__ import annotations

from markupsafe import Markup

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700'
    '&family=JetBrains+Mono:wght@400;600;700&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">\n'
)

# Icono: radar en tinta sobre el cuadrado naranja de la marca.
FAVICON = (
    '<meta name="theme-color" content="#F4F3EF" media="(prefers-color-scheme: light)"/>\n'
    '<meta name="theme-color" content="#0F0F0E" media="(prefers-color-scheme: dark)"/>\n'
    '<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 32 32\'%3E'
    '%3Crect x=\'1\' y=\'1\' width=\'30\' height=\'30\' fill=\'%23FF5722\' stroke=\'%23121211\' stroke-width=\'2\'/%3E'
    '%3Ccircle cx=\'16\' cy=\'16\' r=\'10\' fill=\'none\' stroke=\'%23121211\' stroke-width=\'2.4\'/%3E'
    '%3Cpath d=\'M16 16V6A10 10 0 0 1 25.5 12.9Z\' fill=\'%23121211\'/%3E%3Ccircle cx=\'11\' cy=\'19.5\' r=\'2\' fill=\'%23121211\'/%3E%3C/svg%3E"/>\n'
)

# Antes de pintar: aplica el tema guardado para que no parpadee.
# Por defecto: ingles y tema claro (van como atributos fijos en <html>, ver
# HTML_ATTRS). Este script solo aplica lo que el visitante haya elegido.
HTML_ATTRS = 'lang="en" data-lang="en" data-theme="light"'
THEME_INIT = (
    "<script>(function(){try{var d=document.documentElement,t=localStorage.getItem('theme'),l=localStorage.getItem('lang');"
    "if(t==='dark')d.setAttribute('data-theme','dark');else if(t==='auto')d.removeAttribute('data-theme');"
    "if(l==='es'){d.removeAttribute('data-lang');d.lang='es';}}catch(e){}})();</script>\n"
)

HEAD = FONTS + FAVICON + THEME_INIT

ICON_SVG = (
    '<svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true">'
    '<circle cx="12" cy="12" r="9.5" fill="none" stroke="currentColor" stroke-width="2.2"/>'
    '<path d="M12 12V2.5A9.5 9.5 0 0 1 21.03 9.06Z" fill="currentColor"/>'
    '<circle cx="7.5" cy="15" r="1.7" fill="currentColor"/></svg>'
)

_LIGHT = (
    "--paper:#F4F3EF;--grid:rgba(18,18,17,.06);--ink:#121211;--text:#121211;--muted:#5B5A55;"
    "--card:#FFFFFF;--card-2:#FAF9F5;--line:#D9D7CF;--orange-ink:#C2410C;--logo-bg:#EDECE6;"
    "--open:#0E9F6E;--bad:#C81E3A;--warn:#B45309;"
)
_DARK = (
    "--paper:#0F0F0E;--grid:rgba(232,231,225,.045);--ink:#E8E7E1;--text:#E8E7E1;--muted:#9C9B95;"
    "--card:#181816;--card-2:#1E1E1C;--line:#34342F;--orange-ink:#FF8A5C;--logo-bg:#EDECE6;"
    "--open:#34D399;--bad:#FF5C7A;--warn:#FBBF24;"
)

BASE_CSS = """
  :root{""" + _LIGHT + """
    --orange:#FF5722;--lime:#CCFF00;--asphalt:#0F0F0E;--on-accent:#121211;
    --shadow-sm:2px 2px 0 var(--ink);--shadow:4px 4px 0 var(--ink);
    --f-body:'Inter',system-ui,-apple-system,'Segoe UI',sans-serif;
    --f-head:'Space Grotesk','Arial Narrow',Arial,sans-serif;
    --f-mono:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
    /* nombres antiguos de las paginas del radar -> tokens de marca */
    --bg:var(--paper);--txt:var(--text);--txt-dim:var(--text);--dim:var(--muted);--dimmer:var(--muted);
    --card-hover:var(--card-2);--line-2:var(--ink);--accent:var(--orange-ink);
    --accent-soft:rgba(204,255,0,.3);--accent-line:var(--ink);
    --green:var(--open);--rose:var(--bad);--amber:var(--warn);--violet:var(--orange-ink);
    --mono:var(--f-mono);--sans:var(--f-body);--disp:var(--f-head);--r:0px;
    color-scheme:light;
  }
  @media (prefers-color-scheme: dark){:root:not([data-theme="light"]){""" + _DARK + """color-scheme:dark}}
  :root[data-theme="dark"]{""" + _DARK + """color-scheme:dark}
  *{box-sizing:border-box}
  html{-webkit-text-size-adjust:100%}
  body{margin:0;min-height:100vh;background-color:var(--paper);color:var(--text);
       background-image:linear-gradient(var(--grid) 1px,transparent 1px),linear-gradient(90deg,var(--grid) 1px,transparent 1px);
       background-size:24px 24px;font:16px/1.5 var(--f-body)}
  a{color:inherit;text-decoration:none}
  img{max-width:100%}
  ::selection{background:var(--lime);color:#121211}

  /* -- Cabecera de marca -- */
  .topnav{display:flex;align-items:center;gap:16px;flex-wrap:wrap;padding:12px 24px;
          background:var(--paper);border-bottom:3px solid var(--ink);position:relative;z-index:5}
  .brand{display:flex;align-items:center;gap:12px;flex:0 0 auto}
  .brand-icon{width:44px;height:44px;display:grid;place-content:center;background:var(--orange);
              color:#121211;border:2px solid var(--ink);box-shadow:var(--shadow-sm)}
  .brand-text{display:flex;flex-direction:column}
  .brand-text strong{font:700 24px/1 var(--f-head);letter-spacing:-.02em;text-transform:uppercase}
  .brand-text strong em{color:var(--orange);font-style:normal}
  .brand-text small{font:400 11px/1.3 var(--f-mono);color:var(--muted);margin-top:4px}
  .navtabs{display:flex;border:2px solid var(--ink);box-shadow:var(--shadow);background:var(--card);
           margin:0 auto;overflow-x:auto;scrollbar-width:none;max-width:100%}
  .navtabs::-webkit-scrollbar{display:none}
  .navtab{display:flex;align-items:center;gap:8px;padding:9px 14px;border-right:2px solid var(--ink);
          font:600 12.5px/1.2 var(--f-mono);white-space:nowrap;text-transform:uppercase}
  .navtab:last-child{border-right:0}
  .navtab i{font-style:normal;color:var(--orange-ink);font-weight:700}
  .navtab:hover{background:rgba(204,255,0,.3)}
  .navtab[aria-current="page"]{background:var(--lime);color:#121211}
  .navtab[aria-current="page"] i{color:#121211}
  .seg{display:inline-flex;border:2px solid var(--ink);box-shadow:var(--shadow-sm);background:var(--card)}
  .seg-btn{font:700 11.5px/1.2 var(--f-mono);padding:8px 11px;border:0;border-right:2px solid var(--ink);
           background:transparent;color:var(--text);text-transform:uppercase;cursor:pointer}
  .seg-btn:last-child{border-right:0}
  .seg-btn:hover{background:rgba(204,255,0,.3)}
  .seg-btn[aria-pressed="true"]{background:var(--lime);color:#121211}

  /* Franja de estado (asfalto), como la de "Recogida" de moloch.sh */
  .strip{display:flex;align-items:center;gap:8px 18px;flex-wrap:wrap;padding:9px 24px;
         background:var(--asphalt);color:#E8E7E1;font:400 12.5px/1.4 var(--f-mono);border-bottom:2px solid var(--ink)}
  .strip b{font-weight:700;color:#fff}
  .strip .hl{color:var(--lime)}
  .strip .it{display:inline-flex;align-items:center;gap:7px}
  .strip .it::before{content:"";width:7px;height:7px;border-radius:50%;background:#34D399}
  .strip .it.warn::before{background:#FBBF24}
  .strip .it.bad::before{background:#FF5C7A}
  .strip .r{margin-left:auto}
  .strip a{color:var(--lime);border:1px solid var(--lime);padding:2px 8px}
  .strip a:hover{background:var(--lime);color:#121211}
  .data-links{display:inline-flex;align-items:center;gap:8px;flex-wrap:wrap}
  .data-links .dl-h{color:#9C9B95;text-transform:uppercase;font-size:11px;letter-spacing:.06em}

  /* Web hermana: MOLOCH.SH, el observatorio de modelos */
  .sister{display:inline-flex;align-items:center;gap:10px;padding:7px 12px;background:var(--orange);color:#121211;
          border:2px solid var(--ink);box-shadow:var(--shadow);font:700 12.5px/1.15 var(--f-mono);text-transform:uppercase}
  .sister small{display:block;font:400 10px/1.2 var(--f-mono);letter-spacing:.02em;text-transform:none}
  .sister:hover{transform:translate(1px,1px);box-shadow:var(--shadow-sm)}

  /* Etiqueta de seccion: cuadrado naranja + mono en mayusculas */
  .sec{display:flex;align-items:center;gap:10px;font:700 13px/1.2 var(--f-mono);
       text-transform:uppercase;letter-spacing:.08em;margin:0 0 6px}
  .sec::before{content:"";width:12px;height:12px;background:var(--orange);border:2px solid var(--ink);flex:0 0 auto}
  .sec-sub{font:400 11.5px/1.4 var(--f-mono);text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:0 0 14px}
  .kicker{font:700 12px/1.2 var(--f-mono);text-transform:uppercase;letter-spacing:.08em;color:var(--orange-ink)}
  .page-h1{font:700 clamp(30px,4.2vw,56px)/1 var(--f-head);letter-spacing:-.03em;text-transform:uppercase;margin:6px 0 12px}
  .lede{color:var(--muted);font-size:17px;max-width:72ch;margin:0}
  .lead h1.page-h1{font:700 clamp(30px,4.2vw,56px)/1 var(--f-head);letter-spacing:-.03em;margin:6px 0 12px}

  /* Bilingue: cada texto traducible va dos veces; se ve el del idioma activo. */
  /* !important: reglas de componente con display propio no deben reactivar el idioma oculto. */
  html:not([data-lang="en"]) .l-en{display:none!important}
  html[data-lang="en"] .l-es{display:none!important}
  .top-ctl{display:flex;gap:10px;flex-wrap:wrap}

  /* Firma, como en moloch.sh: nombre, una línea y enlaces en píldoras naranja neón */
  .credits{display:flex;align-items:center;justify-content:space-between;gap:14px 24px;flex-wrap:wrap;
           margin-top:40px;padding:16px 18px;background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow-sm)}
  .credits-id p{margin:0}
  .credits-by{font:400 13px var(--f-mono);color:var(--text);letter-spacing:.02em}
  .credits-by strong{font:700 19px var(--f-head);color:var(--text);letter-spacing:0;margin-left:2px;white-space:nowrap}
  .credits-tag{margin-top:4px!important;color:var(--muted);font-size:14px}
  .credits-links{display:flex;flex-wrap:wrap;gap:10px}
  .credits-links a{display:inline-flex;align-items:center;gap:8px;padding:8px 18px;border:1.5px solid var(--orange);border-radius:999px;
       color:var(--orange-ink);background:transparent;font:600 12px/1 var(--f-mono);text-transform:uppercase;letter-spacing:.14em;text-decoration:none;
       box-shadow:0 0 6px rgba(255,87,34,.35),inset 0 0 6px rgba(255,87,34,.12);transition:background .15s,color .15s,box-shadow .15s}
  .credits-links a:hover,.credits-links a:focus-visible{background:var(--orange);color:#121211;box-shadow:0 0 14px rgba(255,87,34,.75),0 0 2px var(--orange)}
  .credits-links .bmc-cup{font-size:15px;line-height:1}

  @media(max-width:900px){
    .navtabs{order:3;margin:0;width:100%}
    .navtab{flex:1;justify-content:center}
  }
  @media(max-width:640px){
    .topnav{padding:10px 16px;gap:10px}
    .strip{padding:9px 16px}
    .brand-text strong{font-size:20px}
    .strip .r{margin-left:0}
  }
"""

THEME_JS = """<script>
  (function(){
    var btns = document.querySelectorAll('[data-theme-set]');
    function cur(){ try { return localStorage.getItem('theme') || 'light'; } catch(e){ return 'light'; } }
    function paint(){ var c = cur(); btns.forEach(function(b){ b.setAttribute('aria-pressed', String(b.getAttribute('data-theme-set') === c)); }); }
    btns.forEach(function(b){
      b.addEventListener('click', function(){
        var t = b.getAttribute('data-theme-set');
        try { localStorage.setItem('theme', t); } catch(e){}
        if (t === 'auto') document.documentElement.removeAttribute('data-theme');
        else document.documentElement.setAttribute('data-theme', t);
        paint();
      });
    });
    paint();

    var langBtns = document.querySelectorAll('[data-lang-set]');
    function curLang(){ try { return localStorage.getItem('lang') === 'es' ? 'es' : 'en'; } catch(e){ return 'en'; } }
    function paintLang(){ var c = curLang(); langBtns.forEach(function(b){ b.setAttribute('aria-pressed', String(b.getAttribute('data-lang-set') === c)); }); }
    langBtns.forEach(function(b){
      b.addEventListener('click', function(){
        var l = b.getAttribute('data-lang-set');
        try { localStorage.setItem('lang', l); } catch(e){}
        var d = document.documentElement;
        if (l === 'en') { d.setAttribute('data-lang', 'en'); d.lang = 'en'; } else { d.removeAttribute('data-lang'); d.lang = 'es'; }
        paintLang();
      });
    });
    paintLang();
  })();
</script>"""

NAV = (("daily", "01", ("Diario", "Daily"), "index.html"),
       ("weekly", "02", ("Semanal", "Weekly"), "weekly.html"),
       ("archivo", "03", ("Archivo", "Archive"), "archivo.html"))


def header(nav: str = "daily", root: str = "") -> Markup:
    """Cabecera comun: marca, navegacion numerada y selector de tema."""
    current = ' aria-current="page"'
    tabs = "".join(
        f'<a class="navtab" href="{root}{href}"{current if key == nav else ""}><i>{num}</i> {str(bi(*label))}</a>'
        for key, num, label, href in NAV
    )
    return Markup(
        '<header class="topnav">'
        f'<a class="brand" href="{root}index.html" aria-label="Radar.IA, portada">'
        f'<span class="brand-icon">{ICON_SVG}</span>'
        '<span class="brand-text"><strong>Radar<em>.IA</em></strong>'
        '<small>' + str(bi('Radar estratégico de la carrera AGI', 'Strategic radar of the AGI race')) + '</small></span></a>'
        f'<nav class="navtabs" aria-label="Secciones">{tabs}</nav>'
        '<a class="sister" href="https://moloch-sh.netlify.app/" target="_blank" rel="noopener noreferrer">'
        '<span aria-hidden="true">&gt;_</span><span>MOLOCH.SH ↗<small>'
        + str(bi('Observatorio de modelos', 'Model observatory')) + '</small></span></a>'
        '<div class="top-ctl"><div class="seg" role="group" aria-label="Idioma">'
        '<button type="button" class="seg-btn" data-lang-set="es">ES</button>'
        '<button type="button" class="seg-btn" data-lang-set="en">EN</button></div>'
        '<div class="seg" role="group" aria-label="Tema">'
        '<button type="button" class="seg-btn" data-theme-set="auto">Auto</button>'
        '<button type="button" class="seg-btn" data-theme-set="light">' + str(bi('Claro', 'Light')) + '</button>'
        '<button type="button" class="seg-btn" data-theme-set="dark">' + str(bi('Oscuro', 'Dark')) + '</button>'
        '</div></div></header>'
    )


def bi(es, en="") -> Markup:
    """Texto en los dos idiomas; sin traduccion, solo el español."""
    es_t, en_t = str(es or ""), str(en or "")
    if not en_t or en_t == es_t:
        return Markup.escape(es_t)
    return Markup('<span class="l-es">{}</span><span class="l-en" lang="en">{}</span>').format(es_t, en_t)


BMC_URL = "https://buymeacoffee.com/rolandofernandez"


LINKEDIN_URL = "https://www.linkedin.com/in/rolando-fernandez-jara"
GITHUB_URL = "https://github.com/rolandojf-gif"


def credits() -> Markup:
    """Firma con enlaces (LinkedIn, GitHub, café), igual que en moloch.sh."""
    return Markup(
        '<div class="credits"><div class="credits-id">'
        '<p class="credits-by">© 2026 RADAR.IA · {} <strong>Rolando Fernández</strong></p>'
        '<p class="credits-tag">{}</p></div>'
        '<nav class="credits-links" aria-label="Rolando Fernández">'
        '<a href="{}" target="_blank" rel="noopener">LinkedIn</a>'
        '<a href="{}" target="_blank" rel="noopener">GitHub</a>'
        '<a class="bmc" href="{}" target="_blank" rel="noopener"><span class="bmc-cup" aria-hidden="true">☕</span> {}</a>'
        '</nav></div>'
    ).format(bi("por", "by"), bi("Radar diario de la carrera hacia la AGI, con fuentes y análisis.", "A daily radar of the race towards AGI, with sources and analysis."),
             LINKEDIN_URL, GITHUB_URL, BMC_URL, bi("Invítame a un café", "Buy me a coffee"))


# -- SEO ------------------------------------------------------------------
SITE_URL = "https://aievolve.netlify.app/"
SITE_NAME = "RADAR.IA"
GOOGLE_VERIFICATION = "yh8wm8HsAeqP892U5UGczQs-RLnGuNHx7WGfNntGduk"
# Token de Cloudflare Web Analytics. Vacio = sin beacon. Al crear el sitio en
# Cloudflare se pega aqui y las tres paginas empiezan a medir.
CLOUDFLARE_TOKEN = "ddd22b1c510f4ef2a210078c77c6d2d5"
OG_IMAGE = SITE_URL + "og.png"
DEFAULT_DESCRIPTION = ("Radar diario de la carrera hacia la AGI: modelos frontier, agentes, chips y compute, "
                       "China y economía de la IA. Solo lo que cambia algo, con fuente y análisis.")


def seo_head(title: str, path: str = "", description: str = DEFAULT_DESCRIPTION, robots: str = "index, follow, max-image-preview:large") -> Markup:
    url = SITE_URL + path
    esc = Markup.escape
    parts = [
        f'<title>{esc(title)}</title>',
        f'<meta name="description" content="{esc(description)}"/>',
        f'<meta name="robots" content="{robots}"/>',
        f'<link rel="canonical" href="{url}"/>',
        f'<meta name="google-site-verification" content="{GOOGLE_VERIFICATION}"/>',
        '<meta property="og:type" content="website"/>',
        f'<meta property="og:site_name" content="{SITE_NAME}"/>',
        '<meta property="og:locale" content="es_ES"/><meta property="og:locale:alternate" content="en_US"/>',
        f'<meta property="og:title" content="{esc(title)}"/>',
        f'<meta property="og:description" content="{esc(description)}"/>',
        f'<meta property="og:url" content="{url}"/>',
        f'<meta property="og:image" content="{OG_IMAGE}"/>',
        '<meta property="og:image:width" content="1200"/><meta property="og:image:height" content="630"/>',
        '<meta name="twitter:card" content="summary_large_image"/>',
        f'<meta name="twitter:title" content="{esc(title)}"/>',
        f'<meta name="twitter:description" content="{esc(description)}"/>',
        f'<meta name="twitter:image" content="{OG_IMAGE}"/>',
        '<script type="application/ld+json">{"@context":"https://schema.org","@type":"WebSite",'
        f'"@id":"{SITE_URL}#website","url":"{SITE_URL}","name":"{SITE_NAME}",'
        '"description":"Radar diario de la carrera hacia la AGI, con fuentes y análisis.",'
        '"inLanguage":["es","en"],"isAccessibleForFree":true,'
        '"author":{"@type":"Person","name":"Rolando Fernández"}}</script>',
    ]
    if CLOUDFLARE_TOKEN:
        parts.append('<script type="module" src="https://static.cloudflareinsights.com/beacon.min.js" '
                     f'data-cf-beacon=\'{{"token": "{CLOUDFLARE_TOKEN}"}}\'></script>')
    return Markup("\n".join(parts) + "\n")
