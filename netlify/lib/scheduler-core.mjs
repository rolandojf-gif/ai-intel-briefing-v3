// Logica pura del programador (sin red): se prueba con node --test.

export const REPO = 'rolandojf-gif/ai-intel-briefing-v3';
export const WORKFLOW = 'daily.yml';
// Horas de Madrid a las que se lanza la edicion: el primer intento y un
// reintento por si el primero falla. El segundo no repite si ya se publico.
export const MADRID_SLOTS = [{ hour: 4, minute: 37 }, { hour: 6, minute: 37 }];

/** Hora de Madrid (con horario de verano) para un instante dado. */
export function madridTime(date = new Date()) {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/Madrid', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(date);
  const get = (t) => Number(parts.find((p) => p.type === t).value);
  return { hour: get('hour'), minute: get('minute') };
}

/**
 * Netlify programa en UTC. El cron lanza la funcion a las :37 de las horas UTC
 * que pueden ser 04 o 06 en Madrid (en invierno y en verano); aqui se decide si
 * esta llamada cae de verdad en uno de los dos huecos de Madrid.
 */
export function slotFor(date = new Date(), toleranceMin = 10) {
  const { hour, minute } = madridTime(date);
  const now = hour * 60 + minute;
  return MADRID_SLOTS.find((s) => Math.abs(now - (s.hour * 60 + s.minute)) <= toleranceMin) || null;
}

export function dispatchRequest(token) {
  return {
    url: `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,
    init: {
      method: 'POST',
      headers: {
        Accept: 'application/vnd.github+json',
        Authorization: `Bearer ${token}`,
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'radar-ia-scheduler',
      },
      body: JSON.stringify({
        ref: 'main',
        inputs: { force_gemini: 'true', force_refresh: 'false', from_scheduler: 'true' },
      }),
    },
  };
}
