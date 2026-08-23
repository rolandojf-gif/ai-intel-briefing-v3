"""Capa de memoria del radar.

Un radar sin memoria es un lector de RSS: cada día empieza de cero y nada de lo
que dijo ayer tiene consecuencias. Este módulo añade continuidad:

  - resolve_watchlist  — lo que ayer dijo que vigilaras, comprobado hoy
  - entity_deltas      — quién entra nuevo, quién vuelve tras silencio, rachas
  - detect_threads     — narrativas que persisten varios días ("Día 4: ...")

Todo es determinista: no depende del LLM, así que sigue funcionando aunque
Gemini falle. Es la parte del producto que debe ser siempre fiable.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


# -- Carga de historico ------------------------------------------------------

def _is_snapshot(p: Path) -> bool:
    if not p.is_file() or p.suffix.lower() != ".json":
        return False
    try:
        datetime.strptime(p.stem, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def load_history(data_dir: Path, today: str, days: int = 10) -> list[dict]:
    """Snapshots de los `days` dias previos a `today`, del mas viejo al mas nuevo."""
    if not data_dir.exists():
        return []
    paths = sorted((p for p in data_dir.glob("*.json") if _is_snapshot(p)), key=lambda p: p.stem)
    paths = [p for p in paths if p.stem < today][-days:]

    out = []
    for p in paths:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("date", p.stem)
                out.append(data)
        except Exception:
            continue
    return out


def _entities_of(snapshot: dict) -> set[str]:
    ents: set[str] = set()
    for it in (snapshot.get("items") or []):
        if not isinstance(it, dict):
            continue
        for e in (it.get("entities") or []):
            if isinstance(e, str) and e.strip():
                ents.add(e.strip())
    return ents


# -- Watchlist: lo que dijimos ayer, comprobado hoy --------------------------

_STOPWORDS = {
    "para", "sobre", "como", "entre", "desde", "hasta", "cuando", "donde", "este",
    "esta", "estos", "estas", "todo", "toda", "más", "menos", "vigilar", "seguir",
    "confirmar", "watch", "the", "and", "for", "with",
}


def _keyterms(text: str) -> set[str]:
    """Terminos con carga semantica: nombres propios, modelos, siglas, cifras."""
    terms: set[str] = set()
    for m in re.findall(r"\b[A-Z][A-Za-z0-9]*(?:[-. ]?[A-Z0-9][A-Za-z0-9]*)*\b", text or ""):
        t = m.strip()
        if len(t) >= 3 and t.lower() not in _STOPWORDS:
            terms.add(t.lower())
    for m in re.findall(r"\b[a-zA-Z]?\d+(?:\.\d+)?\b", text or ""):
        if len(m) >= 2:
            terms.add(m.lower())
    return terms


def resolve_watchlist(history: list[dict], today_items: list[dict]) -> list[dict]:
    """Comprueba los `watch` del ultimo dia contra las senales de hoy.

    Devuelve [{text, status: hit|open, evidence}]. Heuristica deliberadamente
    conservadora: solo marca `hit` con solape claro de terminos, para que un
    check signifique algo.
    """
    if not history:
        return []

    prev = history[-1]
    prev_watch = [w for w in ((prev.get("briefing") or {}).get("watch") or []) if isinstance(w, str)]
    if not prev_watch:
        return []

    today_index: list[tuple[set[str], dict]] = []
    for it in today_items:
        blob = " ".join([
            str(it.get("title_es") or ""),
            str(it.get("title") or ""),
            str(it.get("so_what") or ""),
            " ".join(str(e) for e in (it.get("entities") or [])),
        ])
        today_index.append((_keyterms(blob), it))

    resolved = []
    for w in prev_watch[:4]:
        wterms = _keyterms(w)
        if not wterms:
            resolved.append({"text": w, "status": "open", "evidence": ""})
            continue

        best, best_overlap = None, 0
        for terms, it in today_index:
            overlap = len(wterms & terms)
            if overlap > best_overlap:
                best, best_overlap = it, overlap

        # Exigimos 2+ terminos coincidentes: 1 solo produce falsos positivos.
        if best is not None and best_overlap >= 2:
            resolved.append({
                "text": w,
                "status": "hit",
                "evidence": (best.get("title_es") or best.get("title") or "")[:110],
            })
        else:
            resolved.append({"text": w, "status": "open", "evidence": ""})

    return resolved


# -- Deltas de entidad -------------------------------------------------------

def entity_deltas(history: list[dict], today_items: list[dict]) -> dict[str, Any]:
    """Quien es nuevo, quien vuelve tras silencio y quien encadena dias."""
    today_ents: set[str] = set()
    for it in today_items:
        for e in (it.get("entities") or []):
            if isinstance(e, str) and e.strip():
                today_ents.add(e.strip())

    if not today_ents:
        return {"new_entrants": [], "returning": [], "streaks": []}

    per_day = [_entities_of(s) for s in history]
    seen_ever = set().union(*per_day) if per_day else set()

    new_entrants = sorted(e for e in today_ents if e not in seen_ever)

    returning = []
    for e in today_ents:
        if e not in seen_ever:
            continue
        silent = 0
        for day_ents in reversed(per_day):
            if e in day_ents:
                break
            silent += 1
        if silent >= 3:
            returning.append({"entity": e, "silent_days": silent})
    returning.sort(key=lambda x: -x["silent_days"])

    streaks = []
    for e in today_ents:
        run = 1  # hoy
        for day_ents in reversed(per_day):
            if e in day_ents:
                run += 1
            else:
                break
        if run >= 3:
            streaks.append({"entity": e, "days": run})
    streaks.sort(key=lambda x: -x["days"])

    return {
        "new_entrants": new_entrants[:5],
        "returning": returning[:4],
        "streaks": streaks[:5],
    }


# -- Threads: narrativas que persisten ---------------------------------------

_THEME_LABELS = {
    "frontier_capability": "Capacidad frontier",
    "agents_automation": "Agentes y automatización",
    "compute_chips_dc": "Compute y chips",
    "model_economics": "Economía de modelos",
    "model_economics_pricing": "Economía de modelos",
    "china_stack": "Stack chino",
    "geopolitics_power": "Geopolítica y poder",
    "other": "Otras señales",
}


def theme_label(theme: str) -> str:
    key = (theme or "other").strip()
    return _THEME_LABELS.get(key, key.replace("_", " ").capitalize())


def detect_threads(history: list[dict], today_items: list[dict], min_days: int = 3) -> list[dict]:
    """Detecta temas que llevan `min_days` o mas dias consecutivos con senal.

    Un thread es lo que permite decir "Dia 4 de la guerra de margenes": convierte
    items sueltos en una narrativa que el lector sigue.
    """
    def themes_of(items: list[dict]) -> set[str]:
        """Temas DOMINANTES del dia, no meramente presentes.

        Si contamos presencia, cualquier dia con 15 items toca todos los temas y
        todo aparece como thread de N dias: informativamente inutil. Un thread
        solo cuenta si el tema estaba entre las senales principales del dia.
        """
        pool = [it for it in (items or []) if isinstance(it, dict)]
        if not pool:
            return set()

        signals = [it for it in pool if it.get("layer") == "signal"]
        if signals:
            pool = signals
        else:
            # Snapshots antiguos (sin capa de veredicto): usar el top por score.
            pool = sorted(pool, key=lambda x: x.get("final_score") or x.get("score") or 0,
                          reverse=True)[:4]

        out = set()
        for it in pool:
            t = (it.get("strategic_theme") or "").strip()
            if t and t != "other":
                out.add(t)
        return out

    today_themes = themes_of(today_items)
    if not today_themes:
        return []

    per_day = [themes_of(s.get("items") or []) for s in history]

    threads = []
    for t in today_themes:
        run = 1
        for day_themes in reversed(per_day):
            if t in day_themes:
                run += 1
            else:
                break
        if run >= min_days:
            lead = next(
                (it for it in today_items if (it.get("strategic_theme") or "") == t),
                None,
            )
            threads.append({
                "theme": t,
                "label": theme_label(t),
                "days": run,
                "lead": (lead.get("title_es") or lead.get("title") or "")[:110] if lead else "",
            })

    threads.sort(key=lambda x: -x["days"])
    return threads[:4]


# -- Nivel de actividad del dia ----------------------------------------------

def activity_level(signals: list[dict], degraded: bool = False) -> tuple[str, str]:
    """(label, css_class) - honesto sobre cuanto ha pasado hoy.

    La variabilidad es intencionada: si todos los dias fueran ALERTA, el estado
    dejaria de informar. Solo cuentan items juzgados como `signal`: sin el gate
    no podemos afirmar que haya actividad relevante.
    """
    if degraded:
        return "SIN FILTRAR", "quiet"

    real = [it for it in signals if it.get("layer") == "signal"]
    n = len(real)
    # Umbral de "senal fuerte" en 85: con el gate v2 entregando 7-8 senales al
    # dia, el corte anterior (70, o 6+ senales) hacia que ALERTA saliera todos
    # los dias y el indicador dejara de informar. Un dia normal debe ser ACTIVO.
    strong = sum(1 for it in real if int(it.get("final_score") or 0) >= 85)

    if n == 0:
        return "SIN SEÑAL", "quiet"
    if strong >= 3 or n >= 10:
        return "ALERTA", "alert"
    if strong >= 1 or n >= 4:
        return "ACTIVO", "active"
    return "TRANQUILO", "quiet"
