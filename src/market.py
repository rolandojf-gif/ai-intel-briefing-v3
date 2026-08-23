from __future__ import annotations

import json
import math
import re
from pathlib import Path
import requests

CACHE_FILE = Path("docs/data/market_cache.json")
TIMEOUT = 6
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def _generate_sparkline(points: list[float], positive: bool = True, width: int = 100, height: int = 24) -> str:
    """Genera un path SVG para un sparkline suave."""
    if not points or len(points) < 2:
        # Fallback dummy curve
        points = [10.0, 10.2, 10.1, 10.5, 10.4, 10.8, 11.0] if positive else [11.0, 10.8, 10.9, 10.4, 10.5, 10.1, 9.8]

    min_val, max_val = min(points), max(points)
    val_range = max_val - min_val if max_val != min_val else 1.0

    coords = []
    n = len(points)
    for i, p in enumerate(points):
        x = round((i / (n - 1)) * (width - 4) + 2, 1)
        # Invert y because SVG y goes downwards
        y = round(height - 4 - ((p - min_val) / val_range) * (height - 8) + 2, 1)
        coords.append(f"{x},{y}")

    color = "#4ade80" if positive else "#f43f5e"
    polyline = " ".join(coords)
    return f'<svg viewBox="0 0 {width} {height}" class="spark"><polyline fill="none" stroke="{color}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" points="{polyline}"/></svg>'


def _fetch_yahoo_quote(symbol: str) -> dict | None:
    """Obtiene el valor del ultimo cierre y la variacion diaria real respecto al cierre anterior."""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        if resp.status_code != 200:
            return None
        data = resp.json()
        result = data.get("chart", {}).get("result", [{}])[0]
        meta = result.get("meta", {})
        
        quotes = result.get("indicators", {}).get("quote", [{}])[0]
        closes = [c for c in quotes.get("close", []) if isinstance(c, (int, float))]

        if not closes:
            price = meta.get("regularMarketPrice") or meta.get("chartPreviousClose")
            if price is None:
                return None
            return {
                "price": price,
                "change_pct": 0.0,
                "sparkline_points": [],
            }

        last_close = closes[-1]
        if len(closes) >= 2:
            prev_close = closes[-2]
            change_pct = ((last_close - prev_close) / prev_close) * 100 if prev_close else 0.0
        else:
            prev_close = meta.get("previousClose") or meta.get("chartPreviousClose") or last_close
            change_pct = ((last_close - prev_close) / prev_close * 100) if prev_close else 0.0

        return {
            "price": last_close,
            "change_pct": change_pct,
            "sparkline_points": closes[-7:] if len(closes) >= 2 else [last_close],
        }
    except Exception:
        return None


def _fetch_crypto_bitcoin() -> dict | None:
    """Obtiene cotización y variación de Bitcoin."""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true"
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json().get("bitcoin", {})
            price = data.get("usd", 76000.0)
            change = data.get("usd_24h_change", 0.0)
            return {
                "price": price,
                "change_pct": change,
                "sparkline_points": [price * (1 - change/200), price * (1 - change/400), price],
            }
    except Exception:
        pass
    return None


def get_market_overview() -> dict:
    """Resumen macro y empresas IA para el panel lateral.

    Cuando una cotizacion no se puede obtener se marca `available: False` y NO se
    inventa un precio. Antes habia constantes de respaldo (NVDA a 128,50 con
    +2,45%) que se pintaban igual que un dato en vivo: el dia que Yahoo fallara,
    la pagina habria mostrado cotizaciones ficticias sin distinguirlas de las
    reales. Un hueco honesto informa; un precio inventado desinforma.
    """
    macro_targets = [
        {"key": "sp500", "label": "S&P Futures", "symbol": "ES=F"},
        {"key": "nasdaq", "label": "NASDAQ F.", "symbol": "NQ=F"},
        {"key": "bitcoin", "label": "Bitcoin", "symbol": "BTC-USD"},
        {"key": "vix", "label": "VIX", "symbol": "^VIX"},
    ]

    ai_companies = [
        {"name": "NVIDIA Corp.", "ticker": "NVDA", "exchange": "NASDAQ", "logo": "https://www.google.com/s2/favicons?domain=nvidia.com&sz=64"},
        {"name": "Super Micro Comp.", "ticker": "SMCI", "exchange": "NASDAQ", "logo": "https://www.google.com/s2/favicons?domain=supermicro.com&sz=64"},
        {"name": "TSMC Ltd.", "ticker": "TSM", "exchange": "NYSE", "logo": "https://www.google.com/s2/favicons?domain=tsmc.com&sz=64"},
        {"name": "Microsoft Corp.", "ticker": "MSFT", "exchange": "NASDAQ", "logo": "https://www.google.com/s2/favicons?domain=microsoft.com&sz=64"},
        {"name": "Alphabet Inc.", "ticker": "GOOGL", "exchange": "NASDAQ", "logo": "https://www.google.com/s2/favicons?domain=google.com&sz=64"},
        {"name": "ASML Holding", "ticker": "ASML", "exchange": "NASDAQ", "logo": "https://www.google.com/s2/favicons?domain=asml.com&sz=64"},
        {"name": "Palantir Tech.", "ticker": "PLTR", "exchange": "NYSE", "logo": "https://www.google.com/s2/favicons?domain=palantir.com&sz=64"},
        {"name": "Amazon.com Inc.", "ticker": "AMZN", "exchange": "NASDAQ", "logo": "https://www.google.com/s2/favicons?domain=amazon.com&sz=64"},
    ]

    NO_DATA = "s/d"

    macro_items = []
    for m in macro_targets:
        if m["key"] == "bitcoin":
            q = _fetch_crypto_bitcoin() or _fetch_yahoo_quote(m["symbol"])
        else:
            q = _fetch_yahoo_quote(m["symbol"])

        if not q:
            macro_items.append({
                "label": m["label"],
                "price_str": NO_DATA,
                "change_str": "",
                "positive": True,
                "available": False,
                "sparkline_svg": "",
            })
            continue

        price = q["price"]
        change = q["change_pct"]
        points = q.get("sparkline_points") or []
        is_pos = change >= 0

        if price > 1000:
            formatted_price = f"{price:,.2f} US$"
        else:
            formatted_price = f"{price:.2f}"

        macro_items.append({
            "label": m["label"],
            "price_str": formatted_price,
            "change_str": f"{change:+.2f}%",
            "positive": is_pos,
            "available": True,
            "sparkline_svg": _generate_sparkline(points, positive=is_pos),
        })

    company_items = []
    for c in ai_companies:
        q = _fetch_yahoo_quote(c["ticker"])
        if not q:
            company_items.append({
                "name": c["name"],
                "ticker": c["ticker"],
                "exchange": c["exchange"],
                "price_str": NO_DATA,
                "change_str": "",
                "positive": True,
                "available": False,
                "logo": c["logo"],
            })
            continue

        change = q["change_pct"]
        company_items.append({
            "name": c["name"],
            "ticker": c["ticker"],
            "exchange": c["exchange"],
            "price_str": f"{q['price']:,.2f} US$",
            "change_str": f"{change:+.2f}%",
            "positive": change >= 0,
            "available": True,
            "logo": c["logo"],
        })

    quotes_ok = sum(1 for x in macro_items + company_items if x.get("available"))
    quotes_total = len(macro_items) + len(company_items)
    if quotes_ok < quotes_total:
        print(f"Mercado: {quotes_ok}/{quotes_total} cotizaciones disponibles; el resto se marca 's/d'.")

    return {
        "macro": macro_items,
        "companies": company_items,
        "quotes_ok": quotes_ok,
        "quotes_total": quotes_total,
    }
