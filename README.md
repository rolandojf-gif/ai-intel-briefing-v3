# ai-intel-briefing-v3

Daily AI intel briefing generator from RSS and X sources.

## Run

```bash
python -m src.main
```

Outputs:
- `docs/data/YYYY-MM-DD.json`
- `docs/index.html`
- `docs/weekly.html`

## Test

```bash
python -m unittest discover -s tests -v
```

## Product direction

The site is designed as a strategic radar, not a raw feed:
- Daily shows the lead signal, conviction, theme radar, entity momentum, filters, search, local saves, and shareable source snippets.
- Weekly shows trend momentum, narrative rotation, breakouts, new entrants, and source/entity concentration.
- Scoring prioritizes hard signals such as API availability, pricing, compute, capex, policy, and shipped model changes over promotional noise.

## X Sources (free)

X ingestion is API-free:
- first tries public RSS mirror (`https://xcancel.com`)
- falls back to public profile scraping via `r.jina.ai` when RSS is unavailable

Supported source styles:
- user timeline (`type: x` + `username`)
- recent search (`type: x` + `query`)

Optional environment variables:
- `X_RSS_MIRRORS` (comma-separated mirror list, first healthy one is used)
- `X_RSS_TIMEOUT_SECONDS` (default `12`)
- `X_CACHE_FILE` (path for persistent X cache; default `docs/data/YYYY-MM-DD.x_cache.json`)
- `X_CACHE_FORCE_REFRESH=1` (ignores cache for current run)
- `X_CACHE_DISABLE=1` (turns cache off)

Example:

```bash
X_RSS_MIRRORS=https://xcancel.com,https://nitter.net
```
