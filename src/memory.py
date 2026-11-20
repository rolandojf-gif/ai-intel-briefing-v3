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

from src.evidence import PENDING, PROSPECTIVE, UNCERTAIN, sentences, source_evidence


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

# El hito se formula como declaración observable. Solo una declaración completa
# en la fuente primaria lo cierra; una paráfrasis se queda pendiente de revisión.
_OBSERVED_ACTION = re.compile(
    r"\b(publish(?:es|ed)?|releases?|released|launch(?:es|ed)?|cuts?|approves?|approved|"
    r"ships?|shipped|files?|filed|reports?|reported|publica[nr]?|publicó|lanza[nr]?|"
    r"lanzó|reduce[n]?|redujo|aprueba[n]?|aprobó)\b", re.I,
)


def _statement(text: str) -> str:
    return " ".join(text.split()).strip().rstrip(".").casefold()


def resolve_watchlist(history: list[dict], today_items: list[dict]) -> list[dict]:
    """Cierra solo hitos afirmados literalmente, con evidencia y URL de origen."""
    if not history:
        return []
    brief = history[-1].get("briefing") or {}
    observed = {}
    for item in today_items:
        if item.get("evidence_kind") != "confirmed":
            continue
        quote = (item.get("evidence") or {}).get("quote", "")
        evidence = source_evidence(item, quote)
        if not evidence or not _OBSERVED_ACTION.search(quote) or PROSPECTIVE.search(quote):
            continue
        if any(UNCERTAIN.search(item.get(k) or "") or PENDING.search(item.get(k) or "")
               for k in ("title", "summary")):
            continue
        statement = _statement(quote)
        if any(statement == _statement(s) for k in ("title", "summary")
               for s in sentences(item.get(k) or "")):
            observed[statement] = evidence

    resolved = []
    english = brief.get("watch_en") or []
    for idx, watch in enumerate((brief.get("watch") or [])[:4]):
        if not isinstance(watch, str):
            continue
        en = english[idx] if idx < len(english) and isinstance(english[idx], str) else ""
        evidence = observed.get(_statement(watch)) or observed.get(_statement(en))
        quote = evidence["quote"] if evidence else ""
        resolved.append({"text": watch, "text_en": en, "status": "hit" if evidence else "open",
                         "evidence": quote, "evidence_en": quote,
                         "evidence_url": evidence["url"] if evidence else ""})
    return resolved


# -- Deltas de entidad -------------------------------------------------------

def known_before(data_dir: Path, today: str) -> tuple[set[str], str]:
    """Todo lo visto antes de hoy en el archivo: entidades y texto de titulares.

    "Primera aparicion" se comparaba solo con los ultimos 10 dias: Alibaba,
    Huawei o GPT-6 Astra salian como nuevos aunque llevaban meses en el radar.
    """
    names: set[str] = set()
    texts: list[str] = []
    if not data_dir.exists():
        return names, ""
    for p in sorted(data_dir.glob("*.json")):
        if not _is_snapshot(p) or p.stem >= today:
            continue
        try:
            snap = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for it in (snap.get("items") or []) if isinstance(snap, dict) else []:
            if not isinstance(it, dict):
                continue
            names.update(str(e).strip().lower() for e in (it.get("entities") or []) if isinstance(e, str))
            texts.append(" ".join(str(it.get(k) or "") for k in ("title", "title_es", "title_en", "so_what")))
    return names, " ".join(texts).lower()


def _seen_before(entity: str, known: tuple[set[str], str] | None) -> bool:
    if not known:
        return False
    names, text = known
    e = entity.strip().lower()
    if e in names:
        return True
    return bool(re.search(r"(?<![\w-])" + re.escape(e) + r"(?![\w-])", text))


def entity_deltas(history: list[dict], today_items: list[dict], known: tuple[set[str], str] | None = None) -> dict[str, Any]:
    """Quien es nuevo, quien vuelve tras silencio y quien encadena dias.

    `known` (de known_before) amplia "nuevo" a todo el archivo: solo es primera
    aparicion si el nombre no salio nunca, ni como entidad ni en un titular.
    """
    today_ents: set[str] = set()
    for it in today_items:
        for e in (it.get("entities") or []):
            if isinstance(e, str) and e.strip():
                today_ents.add(e.strip())

    if not today_ents:
        return {"new_entrants": [], "returning": [], "streaks": []}

    per_day = [_entities_of(s) for s in history]
    seen_ever = set().union(*per_day) if per_day else set()

    new_entrants = sorted(e for e in today_ents if e not in seen_ever and not _seen_before(e, known))

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


_THEME_LABELS_EN = {
    "frontier_capability": "Frontier capability", "agents_automation": "Agents and automation",
    "compute_chips_dc": "Compute and chips", "model_economics": "Model economics",
    "model_economics_pricing": "Model economics", "china_stack": "China stack",
    "geopolitics_power": "Geopolitics and power", "other": "Other signals",
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
                "label_en": _THEME_LABELS_EN.get(t, t.replace("_", " ").capitalize()),
                "lead_en": (lead.get("title_en") or lead.get("title") or "")[:110] if lead else "",
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
