import { normalizeEdition } from './model.mjs';

export const SOURCE_HOME = 'https://aievolve.netlify.app';
export const RAW_HOME = 'https://raw.githubusercontent.com/rolandojf-gif/ai-intel-briefing-v3/main/docs';
export const CACHE_KEY = 'nexus-newtab-v1:edition';
export const FRESH_MS = 3 * 60 * 60 * 1000;
export const LOOKBACK_DAYS = 20;
export const FETCH_BATCH = 7;
export const LATEST_URLS = [`${SOURCE_HOME}/newtab/latest.json`, `${RAW_HOME}/newtab/latest.json`];

export function recentDates(now = new Date(), count = LOOKBACK_DAYS + 1) {
  const base = new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate(), 12));
  return Array.from({length: count}, (_, offset) => {
    const d = new Date(base.getTime() - offset * 86400000);
    return [d.getUTCFullYear(), String(d.getUTCMonth() + 1).padStart(2, '0'), String(d.getUTCDate()).padStart(2, '0')].join('-');
  });
}

export function sourceUrls(date) {
  return [`${SOURCE_HOME}/data/${date}.json`, `${RAW_HOME}/data/${date}.json`];
}

export const store = {
  async read() {
    try {
      if (typeof chrome !== 'undefined' && chrome.storage?.local) {
        return (await chrome.storage.local.get(CACHE_KEY))[CACHE_KEY] || null;
      }
      return JSON.parse(localStorage.getItem(CACHE_KEY) || 'null');
    } catch { return null; }
  },
  async write(value) {
    try {
      if (typeof chrome !== 'undefined' && chrome.storage?.local) {
        await chrome.storage.local.set({[CACHE_KEY]: value});
      } else {
        localStorage.setItem(CACHE_KEY, JSON.stringify(value));
      }
    } catch (error) { console.warn('NEXUS: cache not written', error); }
  }
};

async function retrieve(url, timeoutMs = 3500) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {cache: 'no-store', signal: controller.signal});
    if (!response.ok) return null;
    return normalizeEdition(await response.json());
  } catch { return null; }
  finally { clearTimeout(timer); }
}

/** Finds newest valid edition; starts at today and searches back up to 20 days.
 * Prioritizes Netlify, then falls back to raw GitHub, and never calls an AI API.
 */
export async function fetchLatest(now = new Date(), get = retrieve) {
  // Prefer the daily NEXUS feed. This may be RSS-only or a Gemini edition.
  const latest = await Promise.all(LATEST_URLS.map(async (url, index) => {
    try {
      const edition = await get(url);
      return edition ? {edition, source: index === 0 ? 'Netlify' : 'GitHub'} : null;
    } catch { return null; }
  }));
  const preferred = latest.filter(Boolean).sort((a, b) => b.edition.date.localeCompare(a.edition.date))[0];
  const dates = recentDates(now);
  // Fast path: today's publication is already available.
  if (preferred?.edition.date === dates[0]) return preferred;

  // Backward compatibility and race protection during Netlify deployment.
  for (let i = 0; i < dates.length; i += FETCH_BATCH) {
    const batch = dates.slice(i, i + FETCH_BATCH);
    const results = await Promise.all(batch.map(async date => {
      for (const [sourceIndex, url] of sourceUrls(date).entries()) {
        try {
          const edition = await get(url);
          if (edition && edition.date === date)
            return {edition, source: sourceIndex === 0 ? 'Netlify' : 'GitHub'};
        } catch { /* try the other origin */ }
      }
      return null;
    }));
    const newest = results.find(Boolean);
    if (newest && (!preferred || newest.edition.date > preferred.edition.date)) return newest;
    // No need to keep searching past a known newer publication.
    if (preferred && batch[batch.length - 1] <= preferred.edition.date) break;
    if (newest) return newest;
  }
  if (preferred) return preferred;
  throw new Error('No se ha podido recuperar una edición válida de los últimos 21 días.');
}
