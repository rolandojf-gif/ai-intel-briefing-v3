"""Publish a small, explicitly timestamped market snapshot for NEXUS NEWTAB.

Called with the existing market result on Gemini days; RSS days fetch quotes once.
Never calls an LLM, never invents price data, and retains the last good
snapshot if quote providers are unavailable.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import traceback

OUT_PATH = Path('docs/newtab/market.json')


def _quotes(rows: list[dict], *, companies: bool) -> list[dict]:
    keys = ('name', 'ticker', 'exchange', 'logo') if companies else ('label',)
    cleaned = []
    for raw in rows:
        available = bool(raw.get('available'))
        item = {key: str(raw.get(key) or '') for key in keys}
        item.update({
            'available': available,
            'price_str': str(raw.get('price_str') or 's/d') if available else 's/d',
            'change_str': str(raw.get('change_str') or '') if available else '',
            'positive': bool(raw.get('positive')),
            'sparkline_points': [float(v) for v in raw.get('sparkline_points', [])
                                 if isinstance(v, (int, float)) and not isinstance(v, bool)
                                 ][:24] if available else [],
        })
        cleaned.append(item)
    return cleaned


def publish_market(overview: dict | None, path: Path = OUT_PATH, now: datetime | None = None) -> bool:
    """Atomically publish quotes, but do not overwrite a good feed with no data."""
    if not isinstance(overview, dict):
        print('NEXUS MARKET: no market data; previous snapshot retained.')
        return False
    macro = _quotes(overview.get('macro') or [], companies=False)
    companies = _quotes(overview.get('companies') or [], companies=True)
    available = sum(int(item['available']) for item in macro + companies)
    if available == 0:
        print('NEXUS MARKET: zero valid quotes; previous snapshot retained.')
        return False
    checked = now or datetime.now(timezone.utc)
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=timezone.utc)
    payload = {
        'generated_at': checked.astimezone(timezone.utc).isoformat(),
        'kind': 'market_snapshot',
        'source': 'Yahoo Finance; CoinGecko fallback for crypto',
        'quotes_ok': available,
        'quotes_total': len(macro) + len(companies),
        'macro': macro,
        'companies': companies,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)
    print(f'NEXUS MARKET: published {available}/{payload["quotes_total"]} to {path}')
    return True


def refresh_market() -> bool:
    """RSS-only daily run: one market refresh, independent of RSS freshness."""
    try:
        from src.market import get_market_overview
        return publish_market(get_market_overview())
    except Exception:
        print('NEXUS MARKET: provider failed; previous snapshot retained.')
        traceback.print_exc()
        return False
