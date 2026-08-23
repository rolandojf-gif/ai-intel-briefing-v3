"""Push del briefing a Telegram: tesis + hasta 7 señales.

Se llama desde CI después de generar el snapshot. Sin TELEGRAM_BOT_TOKEN o
TELEGRAM_CHAT_ID no hace nada (local y PRs no spamean).
"""
from __future__ import annotations

import html
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

SITE_URL = "https://earnest-pie-01548d.netlify.app"
MONTHS = (
    "", "ene", "feb", "mar", "abr", "may", "jun",
    "jul", "ago", "sep", "oct", "nov", "dic",
)
TELEGRAM_LIMIT = 4096
N_SIGNALS = 7


def esc(s: str, quote: bool = False) -> str:
    return html.escape(s or "", quote=quote)


def clip(s: str, n: int) -> str:
    s = " ".join((s or "").split())
    if len(s) <= n:
        return s
    return s[: n - 1].rstrip() + "…"


def date_label(date: str) -> str:
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
        return f"{dt.day} {MONTHS[dt.month]}"
    except ValueError:
        return date


def item_title(it: dict) -> str:
    return (it.get("title_es") or it.get("title") or "").strip()


def item_url(it: dict) -> str:
    raw = (it.get("url") or it.get("link") or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return raw
    return ""


def pick_signals(snap: dict, n: int = N_SIGNALS) -> list[dict]:
    items = [it for it in (snap.get("items") or []) if isinstance(it, dict)]
    signals = [it for it in items if it.get("layer") == "signal"] or items
    fresh = [it for it in signals if not it.get("is_repeat")]
    rest = [it for it in signals if it.get("is_repeat")]
    picked = []
    seen = set()
    for it in fresh + rest:
        title = item_title(it)
        if not title:
            continue
        key = title.casefold()
        if key in seen:
            continue
        seen.add(key)
        picked.append(it)
        if len(picked) >= n:
            break
    return picked


def format_message(snap: dict, site_url: str = SITE_URL) -> str:
    date = snap.get("date") or ""
    briefing = snap.get("briefing") or {}
    thesis = clip((briefing.get("thesis") or "").strip(), 400)
    if not thesis:
        sigs = briefing.get("signals") or []
        thesis = clip(sigs[0], 400) if sigs else "Sin movimientos de frontera hoy."

    lines = [f"<b>Radar · {esc(date_label(date))}</b>", "", f"<i>{esc(thesis)}</i>", ""]
    for i, it in enumerate(pick_signals(snap), 1):
        title = clip(item_title(it), 140)
        so = clip((it.get("so_what") or it.get("why") or "").strip(), 180)
        src = (it.get("source") or "").strip()
        url = item_url(it)
        lines.append(f"<b>{i}. {esc(title)}</b>")
        if so:
            lines.append(esc(so))
        if url:
            label = esc(src or "abrir")
            lines.append(f'<a href="{esc(url, quote=True)}">{label}</a>')
        elif src:
            lines.append(esc(src))
        lines.append("")

    radar = (site_url or SITE_URL).rstrip("/")
    lines.append(f'<a href="{esc(radar, quote=True)}">Abrir el radar</a>')
    text = "\n".join(lines).strip()
    if len(text) > TELEGRAM_LIMIT:
        text = text[: TELEGRAM_LIMIT - 1] + "…"
    return text


def send_telegram(token: str, chat_id: str, text: str, timeout: int = 20) -> dict:
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram HTTP {e.code}: {body}") from e


def load_snapshot(data_dir: Path, date: str | None = None) -> dict | None:
    data_dir = Path(data_dir)
    if date:
        path = data_dir / f"{date}.json"
    else:
        today = datetime.now().strftime("%Y-%m-%d")
        path = data_dir / f"{today}.json"
        if not path.exists():
            dated = sorted(
                p for p in data_dir.glob("*.json")
                if len(p.stem) == 10 and p.stem[4] == "-" and p.stem[7] == "-"
            )
            path = dated[-1] if dated else path
    if not path.exists():
        return None
    try:
        snap = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return snap if isinstance(snap, dict) else None


def notify_today(
    data_dir: Path = Path("docs/data"),
    date: str | None = None,
    *,
    token: str | None = None,
    chat_id: str | None = None,
    site_url: str | None = None,
    send=None,
) -> str:
    token = (token if token is not None else os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (chat_id if chat_id is not None else os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat_id:
        print("TELEGRAM skip: falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID")
        return "skipped"

    snap = load_snapshot(data_dir, date)
    if not snap:
        print("TELEGRAM skip: no hay snapshot")
        return "missing"

    text = format_message(snap, site_url or os.getenv("SITE_URL") or SITE_URL)
    sender = send or send_telegram
    sender(token, chat_id, text)
    print(f"TELEGRAM sent ({len(text)} chars) date={snap.get('date')}")
    return "sent"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    date = args[0] if args else None
    status = notify_today(date=date)
    return 0 if status in {"sent", "skipped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
