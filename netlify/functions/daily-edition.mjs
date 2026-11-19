/**
 * Programador de la edicion diaria de RADAR.IA (Netlify Scheduled Function).
 *
 * El programador de GitHub retrasaba las tareas de este repo 8-9 horas (la de
 * las 04:37 arrancaba hacia las 13:10). Netlify cumple la hora; esta funcion
 * solo pide a GitHub que lance el workflow, que arranca en segundos.
 *
 * Necesita la variable de entorno GITHUB_DISPATCH_TOKEN en Netlify: un token
 * fine-grained con acceso solo a este repositorio y permiso "Actions: Read and
 * write". El token nunca esta en el codigo.
 */
import { dispatchRequest, madridTime, slotFor } from '../lib/scheduler-core.mjs';

export default async () => {
  const now = new Date();
  const slot = slotFor(now);
  const { hour, minute } = madridTime(now);
  const at = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')} Madrid`;
  if (!slot) {
    console.log(`daily-edition: ${at}, fuera de los huecos de lanzamiento; no hace nada.`);
    return new Response('skip');
  }
  const token = (process.env.GITHUB_DISPATCH_TOKEN || '').trim();
  if (!token) {
    console.error('daily-edition: falta GITHUB_DISPATCH_TOKEN en las variables de entorno de Netlify.');
    return new Response('missing token', { status: 500 });
  }
  const { url, init } = dispatchRequest(token);
  const res = await fetch(url, init);
  if (res.status !== 204) {
    console.error(`daily-edition: GitHub respondio ${res.status}: ${(await res.text()).slice(0, 300)}`);
    return new Response('dispatch failed', { status: 502 });
  }
  console.log(`daily-edition: ${at}, workflow lanzado.`);
  return new Response('dispatched');
};

// UTC: 02:37/03:37 son las 04:37 de Madrid (verano/invierno) y 04:37/05:37 las
// 06:37. La funcion descarta las dos que no tocan segun el horario vigente.
export const config = { schedule: '37 2,3,4,5 * * *' };
