/** Market snapshots live alongside the briefing and contain no API secrets.
 * This module only downloads static JSON, never queries quote/LLM providers.
 */
import {asText} from './model.mjs';
import {SOURCE_HOME, RAW_HOME, FRESH_MS} from './feed.mjs';

export const MARKET_URLS = [`${SOURCE_HOME}/newtab/market.json`, `${RAW_HOME}/newtab/market.json`];
export const MARKET_CACHE_KEY = 'nexus-newtab-v1:market';

const MAX_POINTS = 24;
function normalizeQuote(raw, company = false) {
  if (!raw || typeof raw !== 'object') return null;
  const label = asText(company ? raw.name : raw.label, 68);
  if (!label) return null;
  const available = raw.available === true;
  const price = available ? asText(raw.price_str, 32) : 's/d';
  const change = available ? asText(raw.change_str, 20) : '';
  const sparkline = available && Array.isArray(raw.sparkline_points) ?
    raw.sparkline_points.filter(n => typeof n === 'number' && Number.isFinite(n)).slice(-MAX_POINTS) : [];
  return {label, available, price, change, positive: raw.positive === true,
    sparkline, ticker: company ? asText(raw.ticker, 10) : '',
    exchange: company ? asText(raw.exchange, 20) : ''};
}

export function normalizeMarket(payload) {
  if (!payload || payload.kind !== 'market_snapshot') throw new Error('No es una captura de mercado');
  const timestamp = Date.parse(payload.generated_at || '');
  if (!Number.isFinite(timestamp)) throw new Error('Fecha de mercado inválida');
  const macro = (Array.isArray(payload.macro) ? payload.macro : []).map(q => normalizeQuote(q)).filter(Boolean);
  const companies = (Array.isArray(payload.companies) ? payload.companies : []).map(q => normalizeQuote(q, true)).filter(Boolean);
  if (!macro.some(q => q.available) && !companies.some(q => q.available)) throw new Error('No hay cotizaciones válidas');
  return {generatedAt: new Date(timestamp).toISOString(), macro, companies, timestamp};
}

export const marketStore = {
  async read() {
    try {
      if (typeof chrome !== 'undefined' && chrome.storage?.local)
        return (await chrome.storage.local.get(MARKET_CACHE_KEY))[MARKET_CACHE_KEY] || null;
      return JSON.parse(localStorage.getItem(MARKET_CACHE_KEY) || 'null');
    } catch {return null;}
  },
  async write(value) {
    try {
      if (typeof chrome !== 'undefined' && chrome.storage?.local)
        await chrome.storage.local.set({[MARKET_CACHE_KEY]:value});
      else localStorage.setItem(MARKET_CACHE_KEY, JSON.stringify(value));
    } catch { /* cache is best-effort */ }
  }
};

export async function fetchLatestMarket(fetcher = fetch) {
  const results = await Promise.all(MARKET_URLS.map(async (url,index) => {
    const controller=new AbortController();
    const timer=setTimeout(() => controller.abort(),3500);
    try {
      const response=await fetcher(url,{cache:'no-store',signal:controller.signal});
      if (!response.ok) return null;
      const market=normalizeMarket(await response.json());
      return {market,source:index===0?'Netlify':'GitHub'};
    } catch {return null;}
    finally {clearTimeout(timer);}
  }));
  const valid=results.filter(Boolean).sort((a,b)=>b.market.timestamp-a.market.timestamp);
  if (!valid.length) throw new Error('Mercados no disponibles');
  return valid[0];
}

export function marketCacheFresh(record, now=Date.now()) {
  return !!(record?.market && Number.isFinite(record.fetchedAt) &&
    now-record.fetchedAt >= 0 && now-record.fetchedAt < FRESH_MS);
}
