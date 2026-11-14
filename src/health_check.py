"""Chequeo de salud del run diario: que un fallo no pase desapercibido.

Del 2026-11-07 al 2026-11-13 Gemini fallo todos los dias y el workflow siguio en
verde, porque el modo degradado es un fallo controlado: el radar se publica igual,
sin filtro de relevancia. Nadie se entero en una semana.

Este chequeo corre DESPUES de publicar, asi que nunca impide que salga la edicion:
- Dia degradado      -> anotacion de error, resumen del run y exit 1. El job sale
                        en rojo y GitHub avisa por email.
- Fuentes sin items  -> anotacion de aviso. No rompe el job: una fuente caida es
                        normal; varias durante dias es lo que hay que vigilar.
- Dia sin Gemini     -> no hay snapshot de analisis que comprobar; sale limpio.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

DATA = Path("docs/data")


def _escape(text: str) -> str:
    """Escapado de comandos de workflow de GitHub (::error::, ::warning::)."""
    return str(text).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def check(snapshot: dict) -> tuple[int, list[str], list[str]]:
    """Devuelve (exit_code, anotaciones, lineas_de_resumen)."""
    annotations: list[str] = []
    summary: list[str] = []
    day = snapshot.get("date", "?")

    health = snapshot.get("source_health") or {}
    dead = [d for d in (health.get("dead") or []) if isinstance(d, str)]
    alive, total = health.get("alive", 0), health.get("configured", 0)
    if dead:
        annotations.append(
            f"::warning title=Fuentes sin items ({alive}/{total} vivas)::{_escape(', '.join(dead))}"
        )
        summary.append(f"- Fuentes sin items ({alive}/{total} vivas): {', '.join(dead)}")

    if snapshot.get("degraded"):
        reason = snapshot.get("llm_error") or "sin error registrado (Gemini no se llamo o no devolvio veredictos)"
        annotations.append(
            "::error title=Radar degradado::"
            + _escape(f"{day}: el filtro de relevancia no se aplico. Motivo: {reason}")
        )
        summary.insert(0, f"## Radar DEGRADADO ({day})\n\nEl filtro de relevancia no se aplico.\n\n"
                          f"Motivo: `{reason}`\n")
        return 1, annotations, summary

    counts = snapshot.get("counts") or {}
    summary.insert(0, f"## Radar OK ({day})\n\n"
                      f"{counts.get('signal', 0)} senales, {counts.get('context', 0)} de contexto.\n")
    return 0, annotations, summary


def main(day: str | None = None, data_dir: Path = DATA) -> int:
    day = day or datetime.now().strftime("%Y-%m-%d")
    path = data_dir / f"{day}.json"
    if not path.exists():
        print(f"HEALTH: {day} sin edicion de analisis (dia RSS); nada que comprobar.")
        return 0

    snapshot = json.loads(path.read_text(encoding="utf-8"))
    code, annotations, summary = check(snapshot)
    for line in annotations:
        print(line)

    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path and summary:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(summary) + "\n")

    print(f"HEALTH: {day} {'DEGRADADO' if code else 'OK'}")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
