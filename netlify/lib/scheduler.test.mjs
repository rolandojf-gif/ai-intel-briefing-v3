import test from 'node:test';
import assert from 'node:assert/strict';
import { dispatchRequest, madridTime, slotFor } from './scheduler-core.mjs';

const at = (iso) => new Date(iso);

test('en invierno (CET) solo disparan las 03:37 y 05:37 UTC', () => {
  assert.deepEqual(madridTime(at('2026-11-19T03:37:00Z')), { hour: 4, minute: 37 });
  assert.equal(slotFor(at('2026-11-19T02:37:00Z')), null);   // 03:37 Madrid
  assert.deepEqual(slotFor(at('2026-11-19T03:37:00Z')), { hour: 4, minute: 37 });
  assert.equal(slotFor(at('2026-11-19T04:37:00Z')), null);   // 05:37 Madrid
  assert.deepEqual(slotFor(at('2026-11-19T05:37:00Z')), { hour: 6, minute: 37 });
});

test('en verano (CEST) solo disparan las 02:37 y 04:37 UTC', () => {
  assert.deepEqual(slotFor(at('2026-07-01T02:37:00Z')), { hour: 4, minute: 37 });
  assert.equal(slotFor(at('2026-07-01T03:37:00Z')), null);
  assert.deepEqual(slotFor(at('2026-07-01T04:37:00Z')), { hour: 6, minute: 37 });
  assert.equal(slotFor(at('2026-07-01T05:37:00Z')), null);
});

test('tolera unos minutos de retraso de Netlify, no mas', () => {
  assert.ok(slotFor(at('2026-11-19T03:44:00Z')));
  assert.equal(slotFor(at('2026-11-19T03:55:00Z')), null);
});

test('la peticion a GitHub lanza daily.yml en main como programada', () => {
  const { url, init } = dispatchRequest('tok');
  assert.equal(url, 'https://api.github.com/repos/rolandojf-gif/ai-intel-briefing-v3/actions/workflows/daily.yml/dispatches');
  assert.equal(init.method, 'POST');
  assert.equal(init.headers.Authorization, 'Bearer tok');
  const body = JSON.parse(init.body);
  assert.equal(body.ref, 'main');
  assert.equal(body.inputs.from_scheduler, 'true');
  assert.equal(body.inputs.force_gemini, 'true');
});
