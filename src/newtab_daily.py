"""Publica NEXUS NEWTAB diariamente sin duplicar análisis de Gemini.

Gemini: cada dos días (anclaje 2026-10-10) reutilizando src.main.
RSS: días intermedios; no invoca al LLM ni modifica el briefing estratégico.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit, urlunsplit

import yaml

ANCHOR = date(2026, 10, 10)  # día de análisis Gemini existente
DATA = Path('docs/data')
NEWTAB = Path('docs/newtab')
FEEDS = Path('feeds/feeds.yaml')
MAX_RSS_ITEMS = 24
RECENT_HOURS = 72


def gemini_day(day: date) -> bool:
    """Calendario alterno continuo: no se reinicia los lunes ni cada mes."""
    return (day - ANCHOR).days % 2 == 0


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def publish(data: dict) -> None:
    day = data['date']
    atomic_json(NEWTAB / f'{day}.json', data)
    atomic_json(NEWTAB / 'latest.json', data)
    print(f'NEXUS: {data["edition_type"]} -> {NEWTAB / "latest.json"}')


def publish_analysis(day: date) -> None:
    path = DATA / f'{day.isoformat()}.json'
    source = json.loads(path.read_text(encoding='utf-8'))
    source['edition_type'] = 'analysis'
    source['analysis_date'] = source['date']
    publish(source)


def last_analysis() -> dict | None:
    for path in sorted(DATA.glob('????-??-??.json'), reverse=True):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if data.get('items') and data.get('briefing'):
                return data
        except (OSError, ValueError, TypeError):
            continue
    return None


def url_key(url: str) -> str:
    try:
        parts = urlsplit(url)
        if parts.scheme not in ('http', 'https') or not parts.netloc:
            return ''
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower().removeprefix('www.'), parts.path.rstrip('/'), '', ''))
    except ValueError:
        return ''


def title_key(title: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', title.casefold()).strip()[:150]


def previously_seen(day: date, days: int = 5) -> tuple[set[str], set[str]]:
    urls, titles = set(), set()
    for offset in range(1, days + 1):
        stamp = (day - timedelta(days=offset)).isoformat()
        for path in (DATA / f'{stamp}.json', NEWTAB / f'{stamp}.json'):
            try:
                items = json.loads(path.read_text(encoding='utf-8')).get('items', [])
            except (OSError, ValueError, TypeError):
                continue
            for item in items:
                key = url_key(item.get('link') or item.get('url') or '')
                if key:
                    urls.add(key)
                key = title_key(item.get('title') or '')
                if key:
                    titles.add(key)
    return urls, titles


def theme_for(item: dict) -> str:
    text = f"{item.get('title', '')} {item.get('summary', '')}".casefold()
    if any(term in text for term in ('agent', 'codex', 'automation', 'mcp', 'cursor')):
        return 'agents_automation'
    if any(term in text for term in ('china', 'chinese', 'huawei', 'deepseek', 'qwen', 'alibaba')):
        return 'china_stack'
    if any(term in text for term in ('chip', 'gpu', 'nvidia', 'datacenter', 'data center', 'tsmc')):
        return 'compute_chips_dc'
    if any(term in text for term in ('pricing', 'price', 'cost', 'revenue', 'capex', 'funding')):
        return 'model_economics'
    if any(term in text for term in ('regulation', 'tariff', 'sanction', 'export control')):
        return 'geopolitics_power'
    return 'frontier_capability'


def select_new(items: list[dict], day: date, *, now: datetime | None = None, seen: tuple[set[str], set[str]] | None = None) -> list[dict]:
    """Novedades con enlaces reales, sin duplicados ni posts antiguos."""
    from src.score import score_item
    from email.utils import parsedate_to_datetime

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    known_urls, known_titles = seen if seen is not None else previously_seen(day)
    chosen = []
    for item in items:
        url = (item.get('link') or '').strip()
        title = (item.get('title') or '').strip()
        key = url_key(url)
        title_id = title_key(title)
        if not (key and title_id) or key in known_urls or title_id in known_titles:
            continue
        published = item.get('published')
        if published:
            try:
                ts = datetime.fromisoformat(str(published).replace('Z', '+00:00'))
            except ValueError:
                try:
                    ts = parsedate_to_datetime(published)
                except (TypeError, ValueError, IndexError):
                    continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            elapsed = now - ts.astimezone(timezone.utc)
            if elapsed > timedelta(hours=RECENT_HOURS) or elapsed < -timedelta(hours=6):
                continue
        else:
            # Sin fecha fiable no se puede afirmar que una noticia sea nueva.
            continue
        scored = score_item(title, item.get('summary') or '', item.get('source') or '')
        score = int(scored.get('score') or 0)
        if score < 30:
            continue
        chosen.append({
            'title': title,
            'link': url,
            'published': published,
            'summary': item.get('summary') or '',
            'image_url': item.get('image_url') or '',
            'source': item.get('source') or 'RSS',
            'final_score': score,
            'score': score,
            'strategic_theme': theme_for(item),
            'verdict': 'rss',
            'layer': 'rss',
            'analysis_type': 'heuristic',
        })
        known_urls.add(key)
        known_titles.add(title_id)
    chosen.sort(key=lambda it: (it['final_score'], it.get('published') or ''), reverse=True)
    return chosen[:MAX_RSS_ITEMS]


def collect_rss() -> list[dict]:
    from src.fetch import fetch_rss
    config = yaml.safe_load(FEEDS.read_text(encoding='utf-8'))
    items = []
    for feed in config.get('sources', []):
        if feed.get('type') != 'rss' or not feed.get('url'):
            continue
        limit = min(int(feed.get('limit') or 8), 12)
        for item in fetch_rss(feed['url'], limit=limit, quiet=True):
            item['source'] = feed.get('name') or 'RSS'
            items.append(item)
    return items


def publish_rss(day: date) -> bool:
    chosen = select_new(collect_rss(), day)
    if not chosen:
        print('NEXUS: sin novedades RSS verificables; se mantiene la última edición (no se finge una nueva).')
        return False
    last = last_analysis()
    analysis_date = last.get('date') if last else None
    previous_thesis = (last or {}).get('briefing', {}).get('thesis') or ''
    result = {
        'date': day.isoformat(),
        'edition_type': 'rss',
        'analysis_date': analysis_date,
        'briefing': {'thesis': previous_thesis, 'signals': [], 'risks': [], 'watch': []},
        'counts': {'rss': len(chosen), 'signal': 0, 'context': 0},
        'items': chosen,
        'x_layer': {'status': 'disabled'},
        'source_health': {},
        'degraded': False,
    }
    publish(result)
    return True


def run(day: date, mode: str = 'auto') -> None:
    if mode not in ('auto', 'gemini', 'rss'):
        raise ValueError(f'Modo no válido: {mode}')
    # Ejecución manual: como antes, Gemini por defecto, pero opción sin coste.
    if mode == 'auto' and os.getenv('GITHUB_EVENT_NAME') == 'workflow_dispatch':
        analysis = os.getenv('FORCE_GEMINI', '1').strip() != '0'
    else:
        analysis = gemini_day(day) if mode == 'auto' else mode == 'gemini'
    if analysis:
        print(f'NEXUS: {day.isoformat()} edición con Gemini')
        from src.main import main
        main()
        publish_analysis(day)
    else:
        print(f'NEXUS: {day.isoformat()} edición RSS sin Gemini')
        try:
            publish_rss(day)
        finally:
            # Mercado se refresca incluso cuando no hay novedades RSS.
            # Una caída de mercado nunca sustituye la edición anterior.
            from src.newtab_market import refresh_market
            refresh_market()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['auto', 'gemini', 'rss'], default='auto')
    args = parser.parse_args()
    run(datetime.now().date(), args.mode)


if __name__ == '__main__':
    main()
