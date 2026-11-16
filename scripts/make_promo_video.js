#!/usr/bin/env node
/**
 * Video de presentacion de RADAR.IA (~40 s, 1920x1080) para redes.
 *
 *   node scripts/make_promo_video.js [url] [es|en] [salida.mp4]
 *
 * Graba la web real con Chromium: claro -> oscuro, portada, señales, memoria,
 * ingles -> español, filtro por tema y semanal, con cursor y rotulos propios.
 * No toca la web: los rotulos y el cursor se inyectan solo en esta sesion.
 *
 * Requiere playwright (NODE_PATH) y ffmpeg. Captura con el screencast de
 * Chrome (JPEG por fotograma) en vez del video de Playwright, que comprime
 * demasiado el texto.
 */
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { chromium } = require('playwright');

const BASE = process.argv[2] || 'https://aievolve.netlify.app/';
const LANG = process.argv[3] === 'en' ? 'en' : 'es';
const OUT = path.resolve(process.argv[4] || `radar-ia-${LANG}.mp4`);
const VIEW = { width: 1280, height: 720 };
const SCALE = 1.5; // 1920x1080 de salida con la interfaz a buen tamaño

const T = {
  es: {
    tag: 'El radar diario de la carrera hacia la AGI',
    top: 'Cada mañana: mercados, pulso de la carrera y la tesis del día',
    dark: 'Modo claro y oscuro',
    lead: 'La señal del día, con su análisis',
    cards: 'Cada señal: por qué importa, quién gana y qué vigilar',
    memory: 'Memoria del radar: qué persiste y quién mueve la carrera',
    lang: 'En inglés y en español',
    filter: 'Filtra por tema: agentes, chips, China, modelos…',
    weekly: 'Resumen semanal y archivo con buscador',
    end: 'Gratis · sin registro · actualizado cada día',
  },
  en: {
    tag: 'The daily radar of the race towards AGI',
    top: 'Every morning: markets, race pulse and the thesis of the day',
    dark: 'Light and dark mode',
    lead: 'The signal of the day, with its analysis',
    cards: 'Every signal: why it matters, who gains and what to watch',
    memory: 'Radar memory: what persists and who moves the race',
    lang: 'In English and Spanish',
    filter: 'Filter by theme: agents, chips, China, models…',
    weekly: 'Weekly digest and a searchable archive',
    end: 'Free · no sign-up · updated every day',
  },
}[LANG];

// Se ejecuta en cada pagina antes que su codigo: cursor, rotulo y tarjetas.
const OVERLAY = `(() => {
  const css = \`
    #pv-cur{position:fixed;left:0;top:0;width:22px;height:22px;margin:-3px 0 0 -3px;z-index:2147483646;pointer-events:none;
      transition:transform .08s linear;filter:drop-shadow(1px 2px 0 rgba(0,0,0,.45))}
    #pv-cur.down{transform:scale(.8)}
    #pv-ring{position:fixed;width:44px;height:44px;margin:-22px 0 0 -22px;border:3px solid #CCFF00;border-radius:50%;z-index:2147483645;
      pointer-events:none;opacity:0}
    #pv-ring.go{animation:pvr .55s ease-out}
    @keyframes pvr{from{opacity:.95;transform:scale(.3)}to{opacity:0;transform:scale(1.5)}}
    #pv-cap{position:fixed;left:50%;bottom:34px;transform:translate(-50%,24px);z-index:2147483644;pointer-events:none;opacity:0;
      background:#0F0F0E;color:#CCFF00;border:2px solid #E8E7E1;box-shadow:5px 5px 0 #FF5722;padding:11px 20px;max-width:86vw;
      font:700 19px/1.3 'JetBrains Mono',ui-monospace,Menlo,monospace;text-transform:uppercase;letter-spacing:.02em;text-align:center;
      transition:opacity .35s ease,transform .35s ease}
    #pv-cap.on{opacity:1;transform:translate(-50%,0)}
    #pv-card{position:fixed;inset:0;z-index:2147483647;pointer-events:none;opacity:0;transition:opacity .5s ease;display:grid;place-content:center;
      justify-items:center;gap:26px;background-color:#0F0F0E;color:#E8E7E1;
      background-image:linear-gradient(rgba(232,231,225,.06) 1px,transparent 1px),linear-gradient(90deg,rgba(232,231,225,.06) 1px,transparent 1px);background-size:24px 24px}
    #pv-card.on{opacity:1}
    #pv-card .row{display:flex;align-items:center;gap:22px}
    #pv-card .ic{width:96px;height:96px;display:grid;place-content:center;background:#FF5722;border:4px solid #E8E7E1;box-shadow:7px 7px 0 #E8E7E1;color:#121211}
    #pv-card .wm{font:700 92px/1 'Space Grotesk',Arial,sans-serif;letter-spacing:-.03em}
    #pv-card .wm em{color:#FF5722;font-style:normal}
    #pv-card .tg{font:700 25px/1.3 'JetBrains Mono',ui-monospace,monospace;text-transform:uppercase;color:#CCFF00;text-align:center;max-width:80vw}
    #pv-card .url{font:700 30px 'JetBrains Mono',ui-monospace,monospace;background:#CCFF00;color:#121211;border:3px solid #E8E7E1;padding:10px 20px;box-shadow:6px 6px 0 #FF5722}
  \`;
  const boot = () => {
    if (document.getElementById('pv-cur')) return;
    const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);
    const mk = (id, html) => { const d = document.createElement('div'); d.id = id; if (html) d.innerHTML = html; document.documentElement.appendChild(d); return d; };
    const cur = mk('pv-cur', '<svg viewBox="0 0 22 22" width="22" height="22"><path d="M3 2l15 8-6.5 1.8L8.6 19z" fill="#fff" stroke="#121211" stroke-width="1.8" stroke-linejoin="round"/></svg>');
    const ring = mk('pv-ring'); mk('pv-cap'); mk('pv-card');
    const pos = JSON.parse(sessionStorage.getItem('pv-pos') || '[640,360]');
    const place = (x, y) => { cur.style.left = x + 'px'; cur.style.top = y + 'px'; ring.style.left = x + 'px'; ring.style.top = y + 'px'; };
    place(pos[0], pos[1]);
    addEventListener('mousemove', e => { place(e.clientX, e.clientY); sessionStorage.setItem('pv-pos', JSON.stringify([e.clientX, e.clientY])); }, true);
    addEventListener('mousedown', () => { cur.classList.add('down'); ring.classList.remove('go'); void ring.offsetWidth; ring.classList.add('go'); }, true);
    addEventListener('mouseup', () => cur.classList.remove('down'), true);
    const keep = sessionStorage.getItem('pv-cap'); if (keep) window.__cap(keep);
  };
  window.__cap = (text) => { const c = document.getElementById('pv-cap'); if (!c) return; sessionStorage.setItem('pv-cap', text || '');
    if (!text) { c.classList.remove('on'); return; } c.textContent = text; c.classList.add('on'); };
  window.__card = (tag, url) => { const c = document.getElementById('pv-card'); if (!c) return; if (tag === null) { c.classList.remove('on'); return; }
    c.innerHTML = '<div class="row"><div class="ic"><svg viewBox="0 0 24 24" width="58" height="58"><circle cx="12" cy="12" r="9.5" fill="none" stroke="currentColor" stroke-width="2.2"/><path d="M12 12V2.5A9.5 9.5 0 0 1 21.03 9.06Z" fill="currentColor"/><circle cx="7.5" cy="15" r="1.7" fill="currentColor"/></svg></div><div class="wm">RADAR<em>.IA</em></div></div><div class="tg"></div>' + (url ? '<div class="url"></div>' : '');
    c.querySelector('.tg').textContent = tag; if (url) c.querySelector('.url').textContent = url; c.classList.add('on'); };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();`;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const work = fs.mkdtempSync(path.join(os.tmpdir(), 'radar-promo-'));
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: VIEW, deviceScaleFactor: SCALE, colorScheme: 'light', locale: 'en-US' });
  await context.addInitScript(OVERLAY);
  const page = await context.newPage();

  // Estado inicial fijo: ingles + claro, aunque la sesion tuviera otra cosa.
  await page.goto(BASE, { waitUntil: 'load' });
  await page.evaluate(() => { localStorage.setItem('lang', 'en'); localStorage.setItem('theme', 'light'); sessionStorage.clear(); });
  await page.goto(BASE, { waitUntil: 'load' });
  await page.evaluate((tag) => { const c = document.getElementById('pv-card'); c.style.transition = 'none'; window.__card(tag); void c.offsetWidth; c.style.transition = ''; }, T.tag);
  await sleep(1500); // fuentes e imagenes

  const cdp = await context.newCDPSession(page);
  const frames = [];
  let n = 0;
  cdp.on('Page.screencastFrame', ({ data, metadata, sessionId }) => {
    const file = path.join(work, `f${String(++n).padStart(6, '0')}.jpg`);
    fs.writeFileSync(file, Buffer.from(data, 'base64'));
    frames.push({ file, t: metadata.timestamp, wall: Date.now() });
    cdp.send('Page.screencastFrameAck', { sessionId }).catch(() => {});
  });
  await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 92, maxWidth: VIEW.width * SCALE, maxHeight: VIEW.height * SCALE, everyNthFrame: 1 });

  const cap = (text) => page.evaluate((t) => window.__cap(t), text);
  const scrollTo = (sel, offset, ms) => page.evaluate(async ({ sel, offset, ms }) => {
    const el = sel ? document.querySelector(sel) : null;
    const to = Math.max(0, el ? el.getBoundingClientRect().top + scrollY - offset : 0);
    const from = scrollY, t0 = performance.now();
    await new Promise((done) => { const step = (now) => { const t = Math.min(1, (now - t0) / ms), e = t * t * (3 - 2 * t);
      scrollTo(0, from + (to - from) * e); if (t < 1) requestAnimationFrame(step); else done(); }; requestAnimationFrame(step); });
  }, { sel, offset, ms });
  const moveTo = async (sel, nth = 0) => {
    const box = await page.locator(sel).nth(nth).boundingBox();
    if (!box) return null;
    const p = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
    await page.mouse.move(p.x, p.y, { steps: 28 });
    return p;
  };
  const click = async (sel, nth = 0) => { if (await moveTo(sel, nth)) { await sleep(220); await page.mouse.down(); await sleep(90); await page.mouse.up(); } };

  // 1 · Cabecera
  await sleep(1900);
  await page.evaluate(() => window.__card(null));
  await sleep(700);
  await cap(T.top);
  await page.mouse.move(760, 520, { steps: 30 });
  await sleep(2300);

  // 2 · Modo oscuro
  await cap(T.dark);
  await click('[data-theme-set="dark"]');
  await sleep(2100);

  // 3 · Portada
  await cap(T.lead);
  await page.mouse.move(520, 400, { steps: 20 });
  await scrollTo('.opening', 24, 1500);
  await sleep(2400);

  // 4 · Señales
  await cap(T.cards);
  await scrollTo('.below .grid', 20, 1600);
  await moveTo('.below .card:not(.dup) .card-title');
  await sleep(1300);
  await scrollTo('.below .grid', -300, 1500);
  await sleep(700);

  // 5 · Memoria
  await cap(T.memory);
  await scrollTo('.memory', 60, 1700);
  await page.mouse.move(640, 380, { steps: 20 });
  await sleep(2300);

  // 6 · Idioma
  await scrollTo(null, 0, 1300);
  await cap(T.lang);
  await click('[data-lang-set="es"]');
  await sleep(2400);

  // 7 · Filtro
  await cap(T.filter);
  await click('#tabs .tab[data-filter="agents_automation"]');
  await sleep(700);
  await scrollTo('#deck', 90, 1100);
  await sleep(1400);
  await scrollTo(null, 0, 800);

  // 8 · Semanal
  await cap(T.weekly);
  await click('.navtabs .navtab', 1);
  await page.waitForLoadState('load');
  await sleep(1300);
  await page.mouse.move(700, 430, { steps: 22 });
  await scrollTo('.grid', 40, 1300);
  await sleep(1000);

  // 9 · Cierre
  await cap('');
  await page.evaluate(({ tag, url }) => window.__card(tag, url), { tag: T.end, url: new URL(BASE).host || 'aievolve.netlify.app' });
  await sleep(3200);

  const stoppedAt = Date.now();
  await cdp.send('Page.stopScreencast');
  await sleep(200);
  await browser.close();

  // Lista con la duracion real de cada fotograma -> 30 fps constantes.
  const lines = ['ffconcat version 1.0'];
  frames.forEach((f, i) => {
    // Con la pantalla quieta Chrome no manda fotogramas: el ultimo dura hasta que se paro la captura.
    const d = i + 1 < frames.length ? Math.max(0.001, frames[i + 1].t - f.t) : Math.max(0.04, (stoppedAt - f.wall) / 1000);
    lines.push(`file '${f.file}'`, `duration ${d.toFixed(4)}`);
  });
  lines.push(`file '${frames[frames.length - 1].file}'`);
  const list = path.join(work, 'frames.txt');
  fs.writeFileSync(list, lines.join('\n') + '\n');
  const last = frames[frames.length - 1];
  const total = last.t - frames[0].t + (stoppedAt - last.wall) / 1000;
  const ff = spawnSync('ffmpeg', ['-y', '-f', 'concat', '-safe', '0', '-i', list,
    '-vf', `fps=30,scale=${VIEW.width * SCALE}:${VIEW.height * SCALE}:flags=lanczos,format=yuv420p`,
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '19', '-profile:v', 'high', '-movflags', '+faststart', '-an', OUT], { encoding: 'utf8' });
  if (ff.status !== 0) { console.error(ff.stderr.slice(-2000)); process.exit(1); }
  fs.rmSync(work, { recursive: true, force: true });
  console.log(`${path.basename(OUT)}: ${frames.length} fotogramas en ${total.toFixed(1)} s (${(frames.length / total).toFixed(1)} fps de captura)`);
})();
