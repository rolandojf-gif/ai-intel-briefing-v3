# NEXUS DAILY · New Tab (0.4)

**Periódico personal en cada pestaña nueva de Chrome, con la marca de Radar.IA** (la misma de moloch.sh y brain.gym: papel con cuadrícula, tinta, naranja y lima, tema claro/oscuro/auto).

Vive en este repositorio, junto al pipeline que la alimenta: `extension/`.

## Instalar o actualizar en Chrome (sin npm ni build)

1. Descarga el repositorio: en GitHub, **Code → Download ZIP**, o `git clone` / `git pull` si ya lo tienes.
2. Mueve la carpeta a un sitio fijo (por ejemplo `~/Extensiones/ai-intel-briefing-v3`). Chrome lee la extensión de esa carpeta: si la borras o la mueves, desaparece.
3. Abre `chrome://extensions`, activa **Modo desarrollador** y pulsa **Cargar descomprimida**.
4. Elige la carpeta **`extension`** del repositorio (la que contiene `manifest.json`).
5. Abre una pestaña nueva y, si Chrome pregunta, pulsa **Mantener**.

Para actualizarla después: `git pull` (o vuelve a descargar el ZIP en la misma carpeta) y pulsa ↻ en su tarjeta de `chrome://extensions`.

## Cómo funciona

- Prioriza `https://aievolve.netlify.app/newtab/latest.json` con respaldo en GitHub. Si ese feed aún no está publicado, busca la edición más reciente entre los últimos 21 días de `https://aievolve.netlify.app/data/YYYY-MM-DD.json`.
- Si Netlify está caído, intenta obtener la misma edición desde los archivos públicos del repositorio GitHub.
- Guarda localmente la última edición válida, la pinta al instante y busca la nueva en segundo plano en cada pestaña (solo se lo salta si ya tiene la de hoy desde hace menos de 10 minutos). Hasta la 0.3 no comprobaba nada durante 3 horas y enseñaba ediciones viejas.
- Usa `title_es`, `summary`, `so_what`, `briefing.thesis`, `briefing.signals`, `briefing.watch`, `briefing.risks`, `image_url`, `source` y `link` tal cual los entrega el briefing.
- Los artículos siempre enlazan a sus fuentes; la extensión no inventa noticias.
- **Muestra todos los artículos válidos** de `items` (titular principal + 5 breves + el resto en la sección inferior), sin topes de 26/48 noticias. Se descartan únicamente elementos sin enlace HTTP(S), sin título o URLs repetidas.
- Si falla la red muestra la edición almacenada y avisa de ello.
- Tras fusionar el PR #17 de `ai-intel-briefing-v3`, GitHub Actions ejecutará una tarea diaria: Gemini en días alternos (anclaje 10/10/2026) y noticias RSS nuevas en los días intermedios. La página distingue el tipo de edición; nunca atribuye análisis de IA a una selección RSS.

## Privacidad y gasto

- Permisos: `storage`, acceso a **solo dos fuentes HTTP**: el dominio Netlify del briefing y los ficheros públicos de GitHub (`raw.githubusercontent.com`).
- **Sin acceso al historial**, sin login de X, sin lectura de pestañas, sin cookies ni extracción de páginas privadas.
- **Cero llamadas nuevas a modelos de IA** al abrir la pestaña. Se mantiene, sin alterar, el coste preexistente de Gemini en el briefing.
- No requiere alojar esta extensión ni contratar otra API.

## Código y arquitectura

- `manifest.json`: extensión Chrome Manifest V3, sustitución de `newtab`.
- `newtab.html` + `styles.css`: estructura y maquetación tipográfica editorial.
- `app.js`: interfaz de lectura, filtros, regeneración DOM y estado de caché.
- `src/model.mjs`: contrato de datos del JSON de AI Intel Briefing v3.
- `src/feed.mjs`: Netlify, fallback GitHub y almacenamiento Chrome.
- `tests/`: pruebas funcionales con `node --test tests/*.test.mjs`.

## Limitación actual deliberada

El primer archivo `docs/newtab/latest.json` aparecerá después de la primera ejecución programada (domingo 11 de octubre de 2026, RSS). Hasta entonces, la extensión usa los JSON históricos. Cuando exista el nuevo feed, lo preferirá y seguirá conservando el respaldo.

## Inspiración y licencia

Diseño editorial inspirado en [ThariqS/ai-newtab](https://github.com/ThariqS/ai-newtab) (MIT). Implementación original y simplificada, sin incorporar su agente Claude Managed Agents ni su código TSX. Licencia MIT.

## P0.3 — Mercados (sin coste de IA)

- Banda compacta bajo la cabecera: S&P Futures, Nasdaq Futures, BTC, ETH y VIX.
- Tabla editorial tras las noticias: NVIDIA, SMCI, TSMC, Microsoft, Alphabet, ASML, Palantir y Amazon, con líneas de tendencia calculadas de datos reales.
- El contenido llega de `docs/newtab/market.json`, publicado por el briefing en GitHub Actions y descargado desde Netlify/GitHub como archivo estático.
- **No consulta Yahoo ni CoinGecko desde Chrome**, ni utiliza Gemini/Claude/OpenRouter.
- `market.json` registra la hora de obtención, no se presenta como tiempo real. Si la fuente falla, conserva los últimos datos y mantiene su fecha.
- La sección se oculta si no hay captura disponible, sin deformar la portada.
- Requiere el PR correspondiente de `ai-intel-briefing-v3` fusionado para ver cifras; hasta entonces la extensión funciona normalmente sin mercados.
