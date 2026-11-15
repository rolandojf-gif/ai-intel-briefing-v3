"""Pulso de la carrera y quién la mueve: los dos indicadores propios del radar.

Los dos salen SOLO de los datos del radar (señales publicadas y su relevancia),
no de fuentes externas. Miden intensidad de la conversación, no progreso hacia
la AGI: la interfaz lo dice así.

  - pulse_of      — 0-100: cuánta señal fuerte trae una edición.
  - pulse_block   — pulso de hoy + serie de las últimas ediciones + percentil.
  - movers        — actores con más empuje en las últimas ediciones y tendencia.
"""
from __future__ import annotations

from src.config import ENTITY_ALIASES

# Tope de señales por edición (MAX_SIGNALS en main): 12 señales de 100 = pulso 100.
PULSE_FULL_SIGNALS = 12
HISTORY_EDITIONS = 30
MOVER_WINDOW = 5      # ediciones recientes (incluida la de hoy)
MAX_MOVERS = 6


def _signals(items: list[dict]) -> list[dict]:
    pool = [it for it in (items or []) if isinstance(it, dict)]
    judged = [it for it in pool if it.get("layer") == "signal"]
    return judged


def _score(it: dict) -> float:
    try:
        return max(0.0, min(100.0, float(it.get("final_score") or it.get("score") or 0)))
    except (TypeError, ValueError):
        return 0.0


def pulse_of(items: list[dict]) -> int:
    """Suma de la relevancia de las señales sobre el máximo posible, en 0-100."""
    total = sum(_score(it) for it in _signals(items))
    return int(round(min(100.0, total / PULSE_FULL_SIGNALS)))


def pulse_block(history: list[dict], today_items: list[dict], today: str = "") -> dict:
    """Pulso de hoy con contexto: serie reciente y qué parte de ella queda por debajo.

    Las ediciones degradadas no cuentan: no pasaron el filtro y su pulso sería 0
    por un fallo técnico, no porque el día fuera tranquilo.
    """
    series = [
        {"date": s.get("date", ""), "value": pulse_of(s.get("items") or [])}
        for s in history
        if isinstance(s, dict) and not s.get("degraded")
    ][-(HISTORY_EDITIONS - 1):]
    value = pulse_of(today_items)
    past = [p["value"] for p in series]
    hotter_than = round(100 * sum(1 for v in past if v < value) / len(past)) if past else None
    return {
        "value": value,
        "series": series + [{"date": today, "value": value}],
        "hotter_than": hotter_than,
        "editions": len(past),
    }


def _entity_weights(snapshots_items: list[list[dict]]) -> dict[str, float]:
    weights: dict[str, float] = {}
    for items in snapshots_items:
        for it in _signals(items):
            seen = set()
            for e in it.get("entities") or []:
                if not isinstance(e, str) or not e.strip():
                    continue
                name = ENTITY_ALIASES.get(e.strip(), e.strip())
                if name.lower() in seen:
                    continue
                seen.add(name.lower())
                weights[name] = weights.get(name, 0.0) + _score(it) / 100.0
    return weights


def movers(history: list[dict], today_items: list[dict]) -> list[dict]:
    """Actores con más peso en las últimas ediciones, con tendencia frente a las anteriores.

    Peso = suma de la relevancia de las señales donde aparece el actor. La
    tendencia compara la ventana reciente con la ventana anterior del mismo tamaño.
    """
    good = [s.get("items") or [] for s in history if isinstance(s, dict) and not s.get("degraded")]
    recent = good[-(MOVER_WINDOW - 1):] + [today_items or []]
    previous = good[-(2 * MOVER_WINDOW - 1):-(MOVER_WINDOW - 1)]
    now, before = _entity_weights(recent), _entity_weights(previous)
    if not now:
        return []
    top = sorted(now.items(), key=lambda kv: (-kv[1], kv[0]))[:MAX_MOVERS]
    peak = top[0][1] or 1.0
    out = []
    for name, w in top:
        prev = before.get(name, 0.0)
        if not previous:
            trend = "flat"
        elif prev == 0:
            trend = "new"
        elif w > prev * 1.2:
            trend = "up"
        elif w < prev * 0.8:
            trend = "down"
        else:
            trend = "flat"
        out.append({"entity": name, "weight": round(w, 2), "share": int(round(100 * w / peak)), "trend": trend})
    return out
