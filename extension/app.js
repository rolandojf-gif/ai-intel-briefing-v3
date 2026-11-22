import { normalizeEdition, filterItems, describeTheme, formatEditionDate, daysOld } from './src/model.mjs';
import { SOURCE_HOME, FRESH_MS, store, fetchLatest } from './src/feed.mjs';
import { normalizeMarket, marketStore, fetchLatestMarket, marketCacheFresh } from './src/market.mjs';

const byId = id => document.getElementById(id);
const BAND_COMPANIES = ['NVDA', 'AMZN', 'MSFT', 'AAPL'];  // igual que TICKER_COMPANIES en src/render.py
const RECHECK_MS = 10 * 60 * 1000;  // con la edicion de hoy en cache, recomprobar cada 10 min como mucho

function setupTheme() {
  const buttons = document.querySelectorAll('[data-theme-set]');
  const current = () => { try { return localStorage.getItem('theme') || 'auto'; } catch { return 'auto'; } };
  const paint = () => buttons.forEach(b => b.setAttribute('aria-pressed', String(b.dataset.themeSet === current())));
  buttons.forEach(b => b.addEventListener('click', () => {
    const t = b.dataset.themeSet;
    try { if (t === 'auto') localStorage.removeItem('theme'); else localStorage.setItem('theme', t); } catch { /* sin almacenamiento */ }
    if (t === 'auto') document.documentElement.removeAttribute('data-theme');
    else document.documentElement.setAttribute('data-theme', t);
    paint();
  }));
  paint();
}
const state = {edition:null, filter:'all', busy:false, source:'', cacheAge:0, market:null, marketBusy:false};

function el(tag, className = '', content = '') {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content) node.textContent = content;
  return node;
}
function append(parent, ...children) {
  for (const child of children) if (child) parent.append(child);
  return parent;
}
function link(article, className = '', label = article.title) {
  const anchor = el('a', className, label);
  anchor.href = article.href;
  anchor.rel = 'noopener noreferrer';
  return anchor;
}
function alsoLine(article) {
  if (!article.also?.length) return null;
  const line = el('p', 'also', 'También en: ');
  article.also.forEach((a, i) => {
    if (i) line.append(' · ');
    if (a.href) { const x = el('a', '', a.label); x.href = a.href; x.rel = 'noopener noreferrer'; line.append(x); }
    else line.append(el('span', '', a.label));
  });
  return line;
}
const EVIDENCE_META = {
  confirmed: ['Confirmado', 'Confirmado por fuente primaria'],
  reported: ['Según la fuente', 'Reportado por medio externo'],
  inference: ['Inferencia', 'Lectura editorial basada en la fuente'],
  speculation: ['Hipótesis', 'Hipótesis, rumor o anuncio en curso'],
  unverified: ['Sin verificar', 'Sin evidencia verificable en la fuente'],
};
function evidencePill(article) {
  const entry = EVIDENCE_META[article?.evidenceKind];
  if (!entry) return null;
  const pill = el('span', `ev-pill ev-${article.evidenceKind}`, entry[0]);
  pill.title = entry[1];
  return pill;
}
function sectionHead(text, subtitle = '') {
  const bar = el('div', 'section-heading');
  bar.append(el('span', '', text));
  if (subtitle) bar.append(el('span', 'section-subtitle', subtitle));
  return bar;
}
function setStatus(message, kind = '') {
  const connection = byId('connection-label');
  connection.textContent = message;
  connection.className = `connection-label ${kind}`;
}
function showMessage(message, type = '') {
  const node = byId('message');
  node.textContent = message;
  node.className = `message ${type}`;
  node.hidden = false;
}

// Markets are editorial context, never live prices. All markup is created from
// validated data: no arbitrary HTML or SVG returned by an external endpoint.
function makeSparkline(points, positive) {
  if (!Array.isArray(points) || points.length < 2) return null;
  const values = points.filter(x => Number.isFinite(x));
  if (values.length < 2) return null;
  const low=Math.min(...values), high=Math.max(...values);
  const span=(high-low)||1;
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  svg.setAttribute('viewBox','0 0 100 28');
  svg.setAttribute('class',`market-spark ${positive ? 'up' : 'down'}`);
  svg.setAttribute('aria-hidden','true');
  const line=document.createElementNS('http://www.w3.org/2000/svg','polyline');
  const coords=values.map((v,i)=>`${(2+(i/(values.length-1))*96).toFixed(1)},${(24-((v-low)/span)*20).toFixed(1)}`);
  line.setAttribute('points',coords.join(' '));
  line.setAttribute('fill','none');
  line.setAttribute('stroke','currentColor');
  line.setAttribute('stroke-width','1.8');
  line.setAttribute('stroke-linecap','round');
  line.setAttribute('stroke-linejoin','round');
  svg.append(line);
  return svg;
}

function marketDateLabel(iso) {
  return new Intl.DateTimeFormat('es-ES',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',timeZone:'Europe/Madrid'}).format(new Date(iso)).toUpperCase();
}

function renderMarkets() {
  const ticker=byId('market-ticker'), companies=byId('market-companies');
  const market=state.market;
  ticker.replaceChildren();
  companies.replaceChildren();
  if (!market) {ticker.hidden=true;companies.hidden=true;return;}
  ticker.hidden=false;
  const bandLabel=el('div','market-ticker-heading');
  append(bandLabel,el('strong','','MERCADOS'),el('span','',`DATOS CONSULTADOS ${marketDateLabel(market.generatedAt)} · NO TIEMPO REAL`));
  append(ticker,bandLabel);
  // Misma banda que la web: los indicadores macro + las cuatro grandes, en bucle.
  // El contenido va dos veces para que la rotacion no tenga corte; la segunda
  // copia queda fuera del arbol de accesibilidad.
  const byTicker=new Map(market.companies.map(c=>[c.ticker,c]));
  const quotes=[...market.macro, ...BAND_COMPANIES.map(t=>byTicker.get(t)).filter(Boolean)
    .map(c=>({...c,label:c.label.replace(/ Corp\.$| Inc\.$|\.com Inc\.$/,'')}))];
  const view=el('div','market-ticker-view');
  const track=el('div','market-ticker-track');
  track.style.setProperty('--n',String(quotes.length));
  for (const copy of [0,1]) {
    const band=el('div','market-ticker-quotes');
    if (copy) band.setAttribute('aria-hidden','true');
    quotes.forEach(q => {
      const item=el('div','ticker-quote');
      append(item,el('span','ticker-name',q.label),el('span','ticker-price',q.price));
      append(item,el('span',`ticker-change ${q.available ? q.positive ? 'up':'down' : 'unavailable'}`,q.change||'SIN DATO'));
      const spark=makeSparkline(q.sparkline,q.positive);
      if (spark) append(item,spark);
      append(band,item);
    });
    append(track,band);
  }
  append(view,track);
  append(ticker,view);
  const valid=market.companies;
  companies.hidden=state.filter!=='all'||valid.length===0;
  if (valid.length===0)return;
  append(companies,sectionHead('MERCADOS Y COMPAÑÍAS',`ÚLTIMA CONSULTA ${marketDateLabel(market.generatedAt)} · NO TIEMPO REAL`));
  const grid=el('div','market-company-grid');
  valid.forEach(q=>{
    const row=el('div','market-company');
    const identity=el('div','company-identity');
    append(identity,el('strong','company-name',q.label),el('span','company-ticker',[q.ticker,q.exchange].filter(Boolean).join(' · ')));
    append(row,identity);
    const spark=el('div','company-trend');
    const chart=makeSparkline(q.sparkline,q.positive);
    if(chart)append(spark,chart);
    append(row,spark);
    const price=el('div','company-values');
    append(price,el('strong','company-price',q.price),el('span',`company-change ${q.available ? q.positive?'up':'down':'unavailable'}`,q.change||'SIN DATO'));
    append(row,price);
    append(grid,row);
  });
  append(companies,grid);
  append(companies,el('p','market-disclaimer','Cotizaciones de referencia obtenidas por el briefing. Los futuros, las acciones y las criptomonedas pueden corresponder a distintos momentos de mercado.'));
}

async function refreshMarket() {
  if (state.marketBusy) return;
  state.marketBusy=true;
  try {
    const {market}=await fetchLatestMarket();
    if (!state.market || market.timestamp >= state.market.timestamp) {
      state.market=market;
    }
    await marketStore.write({market:state.market,fetchedAt:Date.now()});
    renderMarkets();
  } catch { /* keep any previously cached, labelled market snapshot */ }
  finally {state.marketBusy=false;}
}

function renderEditorial(edition) {
  const rail = byId('editorial');
  const rss = edition.editionType === 'rss';
  rail.replaceChildren(sectionHead(rss ? 'ÚLTIMO ANÁLISIS GEMINI' : 'EL EDITORIAL', rss ? `DEL ${formatEditionDate(edition.analysisDate).toUpperCase()}` : '01 / ANÁLISIS'));
  const h = el('h2', 'rail-headline', rss ? 'La tesis anterior' : 'La tesis del día');
  const thesis = el('p', 'rail-thesis', edition.thesis || 'Las señales que merecen atención en la carrera tecnológica.');
  append(rail, h, thesis);
  if (edition.signals.length) {
    append(rail, sectionHead('CLAVES DEL DÍA', 'SELECCIÓN'));
    const list = el('ol', 'signals-list');
    edition.signals.slice(0, 4).forEach(s => append(list, el('li', '', s)));
    append(rail, list);
  }
  const facts = el('div', 'rail-facts');
  append(facts, el('span', 'eyebrow', 'EL RADAR EN CIFRAS'), el('strong', 'big-number', String(edition.generatedCount)), el('span','small-note',rss ? 'noticias RSS nuevas · sin análisis Gemini' : 'señales y análisis publicados'));
  if (edition.xStatus === 'killed') append(facts, el('span', 'health-note', 'X no disponible en esta edición'));
  if (edition.topEntities.length) {
    const names = el('div', 'entities');
    edition.topEntities.forEach(name => append(names, el('span','entity-name',name)));
    append(facts, names);
  }
  append(rail, facts);
}

function renderLead(article, edition) {
  const lead = byId('lead');
  lead.replaceChildren();
  if (!article) return;
  const rss = edition.editionType === 'rss';
  append(lead, el('div', 'lead-kicker', (rss ? 'ACTUALIDAD RSS  /  ' : 'LA PORTADA  /  ') + describeTheme(article.theme)));
  const title = el('h1', 'lead-title');
  append(title, link(article));
  append(lead, title);
  if (article.summary) append(lead, el('p', 'lead-deck', article.summary));
  if (article.image) {
    const figure = el('figure', 'lead-image-wrap');
    const img = el('img','lead-image');
    img.src = article.image;
    img.alt = '';
    img.loading = 'eager';
    img.referrerPolicy = 'no-referrer';
    img.addEventListener('error', () => figure.remove());
    const caption = el('figcaption', '', `${article.source.toUpperCase()} · IMAGEN DE LA FUENTE`);
    append(figure, img, caption);
    append(lead, figure);
  }
  const meta = el('div', 'story-meta');
  const metaSrc = el('span', 'story-meta-src');
  append(metaSrc, el('span', '', article.source.toUpperCase()), evidencePill(article));
  append(meta, metaSrc, el('span', '', rss ? 'SIN ANÁLISIS DE IA' : `RELEVANCIA ${Math.round(article.score)}/100`));
  append(lead, meta);
  if (article.why) {
    const analysis = el('div','analysis-note');
    append(analysis, el('span','eyebrow','POR QUÉ IMPORTA'), el('p','',article.why));
    append(lead, analysis);
  }
  append(lead, alsoLine(article));
  append(lead, link(article, 'read-link', 'LEER LA FUENTE ORIGINAL ↗'));
}

function renderLatest(items, edition) {
  const latest = byId('latest');
  latest.replaceChildren(sectionHead('EN BREVE', 'LECTURA RÁPIDA'));
  if (!items.length) append(latest, el('p','rail-thesis','Sin más noticias en esta sección.'));
  items.slice(0, 5).forEach((article, index) => {
    const wrapper = el('article','brief-item');
    append(wrapper, el('span','brief-index', String(index + 1).padStart(2,'0')));
    const body = el('div','brief-body');
    const srcRow = el('div', 'brief-source');
    append(srcRow, el('span', '', article.source), evidencePill(article));
    append(body, el('div','eyebrow brief-category', describeTheme(article.theme)), link(article,'brief-title'), srcRow);
    append(wrapper, body);
    append(latest, wrapper);
  });
  if (edition.watch.length) {
    const sidebar = el('div', 'sidebar-watch');
    append(sidebar, sectionHead('EN EL RADAR'), el('p','',edition.watch[0]));
    append(latest, sidebar);
  }
}

function card(article, index) {
  const wrapper = el('article','news-card');
  const text = el('div','news-card-text');
  append(text, el('div','eyebrow', `${String(index+1).padStart(2,'0')}  /  ${describeTheme(article.theme)}`));
  const heading = el('h3','news-card-title'); append(heading,link(article));
  append(text, heading);
  if (article.why || article.summary) append(text, el('p','news-card-deck',article.why || article.summary));
  append(text, alsoLine(article));
  const srcRow = el('div', 'card-source');
  append(srcRow, el('span', '', article.source.toUpperCase()), evidencePill(article));
  append(text, srcRow);
  if (article.image) {
    const photo = el('a', 'news-card-image'); photo.href = article.href; photo.rel='noopener noreferrer';
    const img = el('img');img.src=article.image;img.alt='';img.loading='lazy';img.referrerPolicy='no-referrer';
    img.addEventListener('error',() => photo.remove());
    append(photo,img);append(wrapper,photo);
  }
  append(wrapper,text);
  return wrapper;
}

function renderBelowfold(items, filter) {
  const below = byId('belowfold'); below.replaceChildren();
  const list = items;
  if (!list.length) return;
  const title = filter === 'all' ? 'MÁS ALLÁ DEL TITULAR' : `TODAS LAS SEÑALES · ${describeTheme(filter)}`;
  append(below, sectionHead(title, `${list.length} ARTÍCULOS`));
  const grid = el('div','news-grid');
  list.forEach((item,i) => append(grid,card(item,i+1)));
  append(below,grid);
}

function renderWatch(edition) {
  const strip = byId('watch-strip'); strip.replaceChildren();
  if (!edition.watch.length && !edition.risks.length) return;
  const inner = el('div','watch-grid');
  if (edition.watch.length) {
    const b=el('div','watch-column');append(b,sectionHead('QUÉ VIGILAR', 'PRÓXIMOS DÍAS'));
    edition.watch.slice(0,3).forEach(x=>append(b,el('p','watch-item',x)));append(inner,b);
  }
  if (edition.risks.length) {
    const b=el('div','watch-column');append(b,sectionHead('PUNTOS DE FRICCIÓN', 'RIESGOS'));
    edition.risks.slice(0,3).forEach(x=>append(b,el('p','watch-item',x)));append(inner,b);
  }
  append(strip,inner);
}

function render() {
  if (!state.edition) return;
  const edition = state.edition;
  const matches = filterItems(edition,state.filter);
  if (!matches.length) {
    byId('content').hidden = true;
    showMessage('No hay noticias de esta categoría en la edición. Selecciona PORTADA para ver el resto.','empty');
    return;
  }
  byId('message').hidden = true;
  byId('content').hidden = false;
  byId('content').classList.toggle('filtered',state.filter!=='all');
  byId('edition-label').textContent = `${edition.editionType === 'rss' ? 'EDICIÓN RSS' : 'EDICIÓN GEMINI'} DEL ${formatEditionDate(edition.date).toUpperCase()}  ·  ${edition.generatedCount} ARTÍCULOS`;
  renderEditorial(edition);
  renderLead(matches[0],edition);
  renderLatest(matches.slice(1,6),edition);
  renderBelowfold(matches.slice(6),state.filter);
  renderWatch(edition);
  renderMarkets();
}

function setFilter(filter) {
  state.filter=filter;
  document.querySelectorAll('.nav-item').forEach(b=>b.classList.toggle('active',b.dataset.filter===filter));
  render();
  window.scrollTo({top:0,behavior:'instant'});
}

async function refresh() {
  if (state.busy) return;
  state.busy=true;
  const button=byId('refresh-btn');button.disabled=true;button.classList.add('busy');
  if (!state.edition) showMessage('Consultando el radar de inteligencia…');
  else setStatus('BUSCANDO UNA NUEVA EDICIÓN…');
  try {
    const {edition, source}=await fetchLatest();
    state.edition=edition;state.source=source;
    await store.write({edition,source,fetchedAt:Date.now()});
    setStatus(`FUENTE: ${source.toUpperCase()} · ${daysOld(edition.date)} DÍAS DESDE EDICIÓN`);
    render();
  } catch (error) {
    if (!state.edition) showMessage(`${error.message} · Pulsa ACTUALIZAR para reintentar.`, 'error');
    else setStatus('SIN CONEXIÓN · MOSTRANDO EDICIÓN GUARDADA','offline');
  } finally {
    state.busy=false;button.disabled=false;button.classList.remove('busy');
  }
}

async function boot() {
  setupTheme();
  const today=new Intl.DateTimeFormat('es-ES',{weekday:'long',day:'numeric',month:'long',year:'numeric'}).format(new Date());
  byId('today-date').textContent=today.charAt(0).toUpperCase()+today.slice(1);
  document.querySelectorAll('.nav-item').forEach(button => button.addEventListener('click',()=>setFilter(button.dataset.filter)));
  byId('refresh-btn').addEventListener('click',()=>{void refresh();void refreshMarket();});
  byId('open-source-btn').addEventListener('click',()=>{window.location.href=SOURCE_HOME+'/';});
  const marketCached=await marketStore.read();
  if (marketCached?.market) {
    try {
      state.market=normalizeMarket({
        kind:'market_snapshot',generated_at:marketCached.market.generatedAt,
        macro:marketCached.market.macro.map(q=>({label:q.label,available:q.available,price_str:q.price,change_str:q.change,positive:q.positive,sparkline_points:q.sparkline})),
        companies:marketCached.market.companies.map(q=>({name:q.label,ticker:q.ticker,exchange:q.exchange,available:q.available,price_str:q.price,change_str:q.change,positive:q.positive,sparkline_points:q.sparkline}))
      });
      renderMarkets();
    } catch { /* invalid cache */ }
  }
  const needsMarket=!marketCacheFresh(marketCached);
  if (needsMarket) void refreshMarket();
  const cached=await store.read();
  if (cached?.edition) {
    try {
      state.edition=cached.edition.items?.[0]?.href ? cached.edition : normalizeEdition(cached.edition);
      state.source=cached.source||'caché';
      setStatus(`FUENTE: ${state.source.toUpperCase()} · EDICIÓN EN CACHÉ`);
      render();
      // Antes no se comprobaba nada durante 3 horas (FRESH_MS) y una edicion
      // nueva no aparecia hasta pasado ese tiempo. Ahora la copia guardada se
      // pinta al instante y se busca la nueva en segundo plano: son ficheros
      // estaticos, sin coste. Solo se omite si es la de hoy y es muy reciente.
      const age = Date.now() - Number(cached.fetchedAt || 0);
      if (daysOld(state.edition.date) === 0 && age < RECHECK_MS) return;
    } catch { /* discard stale/incompatible cache */ }
  }
  await refresh();
}

boot().catch(error=>showMessage(`Error al iniciar la portada: ${error.message}`,'error'));
