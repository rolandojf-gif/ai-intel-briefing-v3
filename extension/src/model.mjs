/** Pure data normalization for AI Intel Briefing v3; no network or Chrome globals. */
export function safeHttpUrl(raw) {
  if (typeof raw !== 'string' || !raw.trim()) return '';
  try {
    const url = new URL(raw);
    return (url.protocol === 'https:' || url.protocol === 'http:') ? url.href : '';
  } catch { return ''; }
}

export function normalizeItem(raw, index = 0) {
  if (!raw || typeof raw !== 'object') return null;
  const href = safeHttpUrl(raw.link || raw.url);
  const title = asText(raw.title_es || raw.title, 220);
  if (!href || !title) return null;
  return {
    id: String(index), href, title,
    source: asText(raw.source || 'Fuente original', 90),
    summary: asText(raw.summary || '', 480),
    why: asText(raw.so_what || raw.why || '', 280),
    powerShift: asText(raw.power_shift || '', 220),
    watchNext: asText(raw.watch_next || '', 220),
    image: safeHttpUrl(raw.image_url),
    score: Number.isFinite(Number(raw.final_score)) ? Number(raw.final_score) : 0,
    timestamp: raw.published || '',
    theme: asText(raw.llm_theme || raw.strategic_theme || raw.primary || 'other', 60),
    verdict: asText(raw.verdict || raw.layer || 'signal', 30),
    repeat: Boolean(raw.is_repeat),
    also: alsoSources(raw)
  };
}

/** Otros medios que cuentan la misma noticia (el radar los fusiona en una card). */
export function alsoSources(raw) {
  const out = [];
  const seen = new Set([asText(raw?.source || '', 90)]);
  for (const r of Array.isArray(raw?.related) ? raw.related : []) {
    const label = asText(r?.source, 60);
    if (label && !seen.has(label)) { seen.add(label); out.push({label, href: safeHttpUrl(r?.url)}); }
  }
  for (const name of Array.isArray(raw?.other_sources) ? raw.other_sources : []) {
    const label = asText(name, 60);
    if (label && !seen.has(label)) { seen.add(label); out.push({label, href: ''}); }
  }
  return out.slice(0, 6);
}

export function asText(raw, limit = 240) {
  return typeof raw === 'string' ? raw.trim().replace(/\s+/g, ' ').slice(0, limit) : '';
}

export function normalizeEdition(payload) {
  if (!payload || typeof payload !== 'object') throw new Error('La respuesta no contiene un JSON válido.');
  if (!/^\d{4}-\d{2}-\d{2}$/.test(payload.date || '')) throw new Error('La edición no tiene una fecha válida.');
  if (!Array.isArray(payload.items)) throw new Error('La edición no incluye una lista de noticias.');
  const urls = new Set();
  const items = [];
  for (const [index, raw] of payload.items.entries()) {
    const item = normalizeItem(raw, index);
    if (item && !urls.has(item.href)) {
      urls.add(item.href);
      items.push(item);
    }
  }
  if (items.length === 0) throw new Error('La edición no contiene noticias publicables.');
  const briefing = payload.briefing && typeof payload.briefing === 'object' ? payload.briefing : {};
  return {
    date: payload.date,
    editionType: payload.edition_type === 'rss' ? 'rss' : 'analysis',
    analysisDate: /^\d{4}-\d{2}-\d{2}$/.test(payload.analysis_date || '') ? payload.analysis_date : payload.date,
    items,
    thesis: asText(briefing.thesis, 500),
    signals: limitedStrings(briefing.signals, 5, 320),
    risks: limitedStrings(briefing.risks, 3, 320),
    watch: limitedStrings(briefing.watch, 4, 320),
    topEntities: Array.isArray(payload.top_entities) ? payload.top_entities.map(e => asText(e?.entity, 40)).filter(Boolean).slice(0, 6) : [],
    xStatus: asText(payload.x_layer?.status || payload.source_health?.x?.status || '', 30),
    generatedCount: items.length
  };
}

function limitedStrings(raw, maxItems, maxChars) {
  return Array.isArray(raw) ? raw.map(s => asText(s, maxChars)).filter(Boolean).slice(0, maxItems) : [];
}

export function filterItems(edition, theme = 'all') {
  const articles = edition?.items || [];
  if (theme === 'all') return articles;
  return articles.filter(item => item.theme === theme);
}

export function describeTheme(theme) {
  const names = {
    frontier_capability: 'FRONTERA IA', agents_automation: 'AGENTES',
    compute_chips_dc: 'CHIPS & COMPUTE', china_stack: 'CHINA',
    geopolitics_power: 'GEOPOLÍTICA', model_economics: 'ECONOMÍA IA',
    models: 'MODELOS', infra: 'INFRAESTRUCTURA', invest: 'MERCADOS',
    geopol: 'GEOPOLÍTICA', research: 'INVESTIGACIÓN', misc: 'TECNOLOGÍA', other: 'ANÁLISIS'
  };
  return names[theme] || 'INTELIGENCIA';
}

export function formatEditionDate(date) {
  const day = new Date(date + 'T12:00:00Z');
  return new Intl.DateTimeFormat('es-ES', {day:'numeric', month:'long', year:'numeric', timeZone:'UTC'}).format(day);
}

export function daysOld(iso, today = new Date()) {
  const day = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  const edition = Date.parse(`${iso}T00:00:00Z`);
  return Math.max(0, Math.round((day - edition) / 86400000));
}
