import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {normalizeEdition, filterItems, safeHttpUrl, daysOld, formatEditionDate} from '../src/model.mjs';
import {recentDates, sourceUrls, fetchLatest, FRESH_MS} from '../src/feed.mjs';

const fixture = JSON.parse(fs.readFileSync(new URL('./fixtures/2026-10-10.json', import.meta.url), 'utf8'));

test('parsea el JSON de briefing v3 y preserva fuentes reales', () => {
  const edition=normalizeEdition(fixture);
  assert.equal(edition.date,'2026-10-10');
  assert.equal(edition.items.length,10);
  assert.equal(edition.items[0].title,'Anthropic limita el acceso a internet en sus evaluaciones de agentes');
  assert.equal(edition.items[0].why.startsWith('Los avances'),true);
  assert.equal(edition.xStatus,'killed');
  assert.equal(filterItems(edition,'china_stack').length,1);
  assert.equal(filterItems(edition,'other').length,0);
});

test('descarta enlaces peligrosos, contenido sin URL y duplicados', () => {
  const copy=structuredClone(fixture);
  copy.items=[{title_es:'malicioso',url:'javascript:alert(1)'},{title_es:'uno',link:'https://example.org/a'},{title_es:'repetido',link:'https://example.org/a'},{title_es:'sin enlace'}];
  assert.equal(normalizeEdition(copy).items.length,1);
  assert.equal(safeHttpUrl('data:text/html,hi'),'');
  assert.equal(safeHttpUrl('//example.org/relative'),'');
  assert.equal(safeHttpUrl('http://example.org/path'),'http://example.org/path');
});

test('falla explícitamente ante feeds vacíos o defectuosos', () => {
  assert.throws(()=>normalizeEdition({date:'2026-10-10',items:[]}),/no contiene noticias/);
  assert.throws(()=>normalizeEdition({date:'nada',items:[]}),/fecha válida/);
});

test('busca cronológicamente la edición más reciente; Netlify prioritario', async () => {
  const calls=[];const edition=normalizeEdition(fixture);
  const result=await fetchLatest(new Date('2026-10-12T07:00:00'),async url=>{
    calls.push(url);
    return url.endsWith('2026-10-10.json')?edition:null;
  });
  assert.equal(result.edition.date,'2026-10-10');
  assert.equal(result.source,'Netlify');
  assert.equal(calls.includes(sourceUrls('2026-10-12')[0]),true);
});

test('una edición GitHub más reciente prevalece sobre Netlify desactualizado', async () => {
  const newer=normalizeEdition(fixture);
  const older=normalizeEdition({...fixture,date:'2026-10-09'});
  const result=await fetchLatest(new Date('2026-10-10T13:00:00'),async url => {
    if (url.startsWith('https://raw.githubusercontent.com/') && url.endsWith('/2026-10-10.json')) return newer;
    if (url.startsWith('https://aievolve.netlify.app/') && url.endsWith('/2026-10-09.json')) return older;
    return null;
  });
  assert.equal(result.edition.date,'2026-10-10');
  assert.equal(result.source,'GitHub');
});

test('recurre a GitHub si Netlify no responde',async()=>{
  const edition=normalizeEdition(fixture);
  const {source}=await fetchLatest(new Date('2026-10-10T07:00:00'),async url=>url.startsWith('https://raw.githubusercontent.com/')&&url.endsWith('/2026-10-10.json')?edition:null);
  assert.equal(source,'GitHub');
});

test('fecha, cadencia de caché y recorrido son consistentes',()=>{
  assert.deepEqual(recentDates(new Date('2026-10-10T07:00:00'),3),['2026-10-10','2026-10-09','2026-10-08']);
  assert.equal(FRESH_MS,10800000);
  assert.equal(daysOld('2026-10-10',new Date('2026-10-10T20:00:00Z')),0);
  assert.match(formatEditionDate('2026-10-10'),/10 de octubre de 2026/);
});

test('manifest mínimo: sin historial ni permisos sobre todos los sitios',()=>{
  const m=JSON.parse(fs.readFileSync(new URL('../manifest.json',import.meta.url),'utf8'));
  assert.equal(m.chrome_url_overrides.newtab,'newtab.html');
  assert.deepEqual(m.permissions,['storage']);
  assert.equal(m.host_permissions.includes('<all_urls>'),false);
  assert.equal(m.host_permissions.some(s=>s.includes('anthropic.com')),false);
});


test('conserva todas las noticias de una edición amplia (sin recorte a 48)', () => {
  const copy = structuredClone(fixture);
  copy.items = Array.from({length:80}, (_, n) => ({
    title_es: `Señal número ${n+1}`,
    link: `https://example.org/news/${n+1}`,
    verdict: 'signal',
    llm_theme: 'agents_automation'
  }));
  const edition = normalizeEdition(copy);
  assert.equal(edition.items.length,80);
  assert.equal(edition.generatedCount,80);
  assert.equal(filterItems(edition,'agents_automation').length,80);
});

test('la portada no limita a 20 las noticias secundarias', () => {
  const app=fs.readFileSync(new URL('../app.js',import.meta.url),'utf8');
  assert.match(app,/const list = items;/);
  assert.doesNotMatch(app,/items\.slice\(0, 20\)/);
  assert.match(app,/renderBelowfold\(matches\.slice\(6\),state\.filter\)/);
});


test('distingue las ediciones RSS de los análisis de Gemini', () => {
  const rss = normalizeEdition({...fixture, edition_type:'rss',analysis_date:'2026-10-08'});
  assert.equal(rss.editionType,'rss');
  assert.equal(rss.analysisDate,'2026-10-08');
  const analysis = normalizeEdition(fixture);
  assert.equal(analysis.editionType,'analysis');
});

test('prefiere newtab/latest.json cuando contiene la edición actual', async () => {
  const current=normalizeEdition({...fixture,date:'2026-10-11',edition_type:'rss',analysis_date:'2026-10-10'});
  const calls=[];
  const result=await fetchLatest(new Date('2026-10-11T09:00:00'), async url => {
    calls.push(url);
    return url.includes('/newtab/latest.json') ? current : null;
  });
  assert.equal(result.edition.editionType,'rss');
  assert.equal(result.edition.date,'2026-10-11');
  assert.equal(calls.some(url=>url.includes('/data/')) ,false);
});

test('sigue funcionando con el archivo original antes del merge', async () => {
  const old=normalizeEdition(fixture);
  const result=await fetchLatest(new Date('2026-10-11T09:00:00'), async url =>
    url.endsWith('/data/2026-10-10.json') ? old : null);
  assert.equal(result.edition.date,'2026-10-10');
});

test('also lists the other outlets of a merged story, safely', async () => {
  const { normalizeItem } = await import('../src/model.mjs');
  const it = normalizeItem({title_es: 'X', link: 'https://a.com/1', source: 'Reuters AI',
    related: [{source: 'Bloomberg Tech', url: 'https://b.com/2'}, {source: 'Malo', url: 'javascript:alert(1)'}],
    other_sources: ['Bloomberg Tech', 'Stratechery', 'Reuters AI']}, 0);
  assert.deepEqual(it.also, [
    {label: 'Bloomberg Tech', href: 'https://b.com/2'},
    {label: 'Malo', href: ''},
    {label: 'Stratechery', href: ''},
  ]);
});
