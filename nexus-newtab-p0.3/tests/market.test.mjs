import {test} from 'node:test';
import assert from 'node:assert/strict';
import {normalizeMarket, fetchLatestMarket, marketCacheFresh, MARKET_URLS} from '../src/market.mjs';

const fixture = (time = '2026-10-10T08:00:00Z', value='229.28 US$')=>({
  kind:'market_snapshot',generated_at:time,
  macro:[{label:'NASDAQ F.',available:true,price_str:'31,108.75 US$',change_str:'+0.45%',positive:true,sparkline_points:[3,4,5]}],
  companies:[{name:'NVIDIA Corp.',ticker:'NVDA',exchange:'NASDAQ',available:true,price_str:value,change_str:'-0.52%',positive:false,sparkline_points:[5,4,3]}]
});

test('normaliza mercados; conserva datos reales y puntos para minigráficas',()=>{
  const market=normalizeMarket(fixture());
  assert.equal(market.macro.length,1);
  assert.equal(market.companies[0].ticker,'NVDA');
  assert.deepEqual(market.companies[0].sparkline,[5,4,3]);
  assert.equal(market.companies[0].positive,false);
});

test('no acepta feeds inválidos, todo s/d o timestamps ausentes',()=>{
  assert.throws(()=>normalizeMarket({kind:'market_snapshot',generated_at:'today',macro:[],companies:[]}));
  assert.throws(()=>normalizeMarket({kind:'market_snapshot',generated_at:'2026-10-10T08:00:00Z',macro:[{label:'VIX',available:false}],companies:[]}));
  assert.throws(()=>normalizeMarket({kind:'hello',generated_at:'2026-10-10T08:00:00Z',macro:[],companies:[]}));
});

test('elige GitHub si tiene una captura posterior a Netlify',async()=>{
  const get=async url=>({ok:true,json:async()=>url===MARKET_URLS[0]?fixture('2026-10-10T06:00:00Z'):fixture('2026-10-10T09:00:00Z')});
  const fetched=await fetchLatestMarket(get);
  assert.equal(fetched.source,'GitHub');
  assert.equal(fetched.market.generatedAt,'2026-10-10T09:00:00.000Z');
});

test('usa Netlify si GitHub no está disponible',async()=>{
  const get=async url=>url===MARKET_URLS[1]?{ok:false}: {ok:true,json:async()=>fixture()};
  assert.equal((await fetchLatestMarket(get)).source,'Netlify');
});

test('actualización de red limitada por caché de tres horas',()=>{
  assert.equal(marketCacheFresh({market:fixture(),fetchedAt:10000},10001),true);
  assert.equal(marketCacheFresh({market:fixture(),fetchedAt:10000},10000+3*60*60*1000),false);
});
