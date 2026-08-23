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
    """Obtiene cotización y serie de precios vía API ligera de Yahoo Finance."""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        if resp.status_code != 200:
            return None
        data = resp.json()
        result = data.get("chart", {}).get("result", [{}])[0]
        meta = result.get("meta", {})
        price = meta.get("regularMarketPrice") or meta.get("chartPreviousClose")
        prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")
        
        quotes = result.get("indicators", {}).get("quote", [{}])[0]
        closes = [c for c in quotes.get("close", []) if isinstance(c, (int, float))]

        if price is None:
            return None

        change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0.0
        return {
            "price": price,
            "change_pct": change_pct,
            "sparkline_points": closes[-7:] if len(closes) >= 2 else [],
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
    """Obtiene el resumen macro y empresas IA para el panel de Discover."""
    macro_targets = [
        {"key": "sp500", "label": "S&P Futures", "symbol": "ES=F", "default_price": 7691.25, "default_change": 0.38},
        {"key": "nasdaq", "label": "NASDAQ F.", "symbol": "NQ=F", "default_price": 29387.75, "default_change": 0.30},
        {"key": "bitcoin", "label": "Bitcoin", "symbol": "BTC-USD", "default_price": 75920.99, "default_change": -1.80},
        {"key": "vix", "label": "VIX", "symbol": "^VIX", "default_price": 15.13, "default_change": -5.50},
    ]

    ai_companies = [
        {"name": "NVIDIA Corp.", "ticker": "NVDA", "exchange": "NASDAQ", "default_price": 128.50, "default_change": 2.45, "logo": "https://www.google.com/s2/favicons?domain=nvidia.com&sz=64"},
        {"name": "Super Micro Comp.", "ticker": "SMCI", "exchange": "NASDAQ", "default_price": 54.80, "default_change": 4.10, "logo": "https://www.google.com/s2/favicons?domain=supermicro.com&sz=64"},
        {"name": "TSMC Ltd.", "ticker": "TSM", "exchange": "NYSE", "default_price": 178.90, "default_change": 1.85, "logo": "https://www.google.com/s2/favicons?domain=tsmc.com&sz=64"},
        {"name": "Microsoft Corp.", "ticker": "MSFT", "exchange": "NASDAQ", "default_price": 448.20, "default_change": 0.65, "logo": "https://www.google.com/s2/favicons?domain=microsoft.com&sz=64"},
        {"name": "Alphabet Inc.", "ticker": "GOOGL", "exchange": "NASDAQ", "default_price": 182.40, "default_change": -0.35, "logo": "https://www.google.com/s2/favicons?domain=google.com&sz=64"},
        {"name": "ASML Holding", "ticker": "ASML", "exchange": "NASDAQ", "default_price": 890.30, "default_change": 1.15, "logo": "https://www.google.com/s2/favicons?domain=asml.com&sz=64"},
        {"name": "Palantir Tech.", "ticker": "PLTR", "exchange": "NYSE", "default_price": 32.10, "default_change": 3.20, "logo": "https://www.google.com/s2/favicons?domain=palantir.com&sz=64"},
        {"name": "Amazon.com Inc.", "ticker": "AMZN", "exchange": "NASDAQ", "default_price": 258.63, "default_change": -0.57, "logo": "https://www.google.com/s2/favicons?domain=amazon.com&sz=64"},
    ]

    macro_items = []
    for m in macro_targets:
        q = None
        if m["key"] == "bitcoin":
            q = _fetch_crypto_bitcoin() or _fetch_yahoo_quote(m["symbol"])
        else:
            q = _fetch_yahoo_quote(m["symbol"])

        if q:
            price = q["price"]
            change = q["change_pct"]
            points = q.get("sparkline_points") or []
        else:
            price = m["default_price"]
            change = m["default_change"]
            points = []

        is_pos = change >= 0
        formatted_price = f"{price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        if price > 1000:
            formatted_price = f"{price:,.2f} US$"
        else:
            formatted_price = f"{price:.2f}"

        macro_items.append({
            "label": m["label"],
            "price_str": formatted_price,
            "change_str": f"{change:+.2f}%",
            "positive": is_pos,
            "sparkline_svg": _generate_sparkline(points, positive=is_pos),
        })

    company_items = []
    for c in ai_companies:
        q = _fetch_yahoo_quote(c["ticker"])
        if q:
            price = q["price"]
            change = q["change_pct"]
        else:
            price = c["default_price"]
            change = c["default_change"]

        is_pos = change >= 0
        company_items.append({
            "name": c["name"],
            "ticker": c["ticker"],
            "exchange": c["exchange"],
            "price_str": f"{price:,.2f} US$",
            "change_str": f"{change:+.2f}%",
            "positive": is_pos,
            "logo": c["logo"],
        })

    return {
        "macro": macro_items,
        "companies": company_items,
    }
