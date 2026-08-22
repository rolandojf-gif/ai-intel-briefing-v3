"""Relevance gate + strategic briefing.

Contrato v2 (2026-08): el LLM ya no puntúa "impacto genérico". Emite un JUICIO
estructurado contra una tesis explícita (ver READER_THESIS). Todo lo que marca
`noise` se ELIMINA del radar, no se rankea más abajo.

Esto es deliberado: el fallo del contrato v1 era pedir "puntúa impacto real"
sin decir impacto para quién, con lo que el modelo premiaba novedad académica
(un paper de estimación de peso de helicópteros sacaba 62/100).
"""

from google import genai
from pydantic import BaseModel, Field
from typing import List, Literal
import json
import os


client = None


# ── Tesis del lector ───────────────────────────────────────────────────
# Esto es lo que convierte el radar en personal. Si cambian los intereses,
# se cambia aquí y todo el ranking se realinea.
READER_THESIS = """
PERFIL DEL LECTOR
Perfil técnico senior (calidad/SQA en automoción). Escéptico, directo, sin
tiempo para relleno. No quiere noticias de IA: quiere señal estratégica sobre
la carrera hacia AGI y los cambios de poder que provoca.

LE IMPORTA (en este orden):
1. Progreso real hacia AGI y movimientos de los frontier labs
   (OpenAI, Anthropic, Google DeepMind, DeepSeek, Meta, xAI, Mistral, Qwen, Moonshot, Zhipu).
2. Agentes, coding agents, MCP, workflows autónomos y sustitución de trabajo cognitivo.
3. Compute, chips, datacenters, energía: quién puede entrenar qué y a qué coste.
4. Economía de modelos: precios de API, márgenes, coste por token, capex.
5. Stack chino de IA y geopolítica: export controls, Huawei, SMIC, soberanía.
6. Cambios de poder de mercado: quién gana y quién pierde posición.

NO LE IMPORTA (marcar como noise):
- Notas de prensa corporativas y marketing reciclado.
- Fichajes, premios, becas, webinars, eventos, conferencias, patrocinios.
- Papers académicos incrementales sin implicación estratégica
  (optimizaciones de arquitectura marginales, aplicaciones de nicho).
- Bumps de versión de librerías y notas de release de tooling menor.
- Tutoriales, guías "how to", contenido de content farm.
- Aplicaciones verticales de IA sin relevancia para la carrera frontier
  (IA en deportes, sanidad de consumo, entretenimiento, marketing).
- Benchmarks de bajo impacto y comparativas sin consecuencia.
"""


Verdict = Literal["signal", "context", "noise"]

Theme = Literal[
    "frontier_capability",     # salto de capacidad, nuevo modelo frontera, progreso AGI
    "agents_automation",       # agentes, coding agents, MCP, sustitución cognitiva
    "compute_chips_dc",        # compute, chips, datacenters, energía
    "model_economics",         # precios, márgenes, coste por token, capex
    "china_stack",             # stack chino de IA
    "geopolitics_power",       # export controls, regulación, soberanía
    "other",
]


class RankOut(BaseModel):
    id: int

    verdict: Verdict = Field(
        description=(
            "signal = mueve la carrera AGI o cambia el reparto de poder; el lector debe verlo hoy. "
            "context = cierto valor de fondo pero no cambia nada hoy. "
            "noise = irrelevante para la tesis, PR, tooling menor, paper incremental o vertical de nicho. "
            "Ante la duda entre context y signal, elige context. Ante la duda entre context y noise, elige noise."
        )
    )
    relevance: int = Field(ge=0, le=100, description="Relevancia para la tesis del lector, no calidad del artículo")
    theme: Theme

    headline_es: str = Field(
        description=(
            "Titular reescrito en castellano de España, afilado y concreto, máx 90 chars. "
            "Debe decir QUÉ ha pasado, no vender. Nada de clickbait ni lenguaje de marketing. "
            "Si el original viene truncado o sucio, reconstruye el sentido sin inventar hechos."
        )
    )
    so_what: str = Field(
        description=(
            "Por qué le importa AL LECTOR, máx 200 chars. NO resumas el artículo: di la consecuencia "
            "estratégica. Prohibido empezar con 'Este artículo' o 'Se anuncia'. Ve al grano."
        )
    )
    power_shift: str = Field(
        default="",
        description=(
            "Quién gana y quién pierde posición, máx 110 chars. Formato 'X gana / Y pierde' o similar. "
            "Vacío si el item no desplaza poder."
        )
    )
    watch_next: str = Field(
        default="",
        description=(
            "Qué señal concreta y verificable confirmaría o refutaría esto, máx 110 chars. "
            "Debe ser falsable (algo que se pueda comprobar en días o semanas). Vacío si no aplica."
        )
    )
    entities: List[str] = Field(default_factory=list, description="0-5 organizaciones/personas clave")


class Briefing(BaseModel):
    thesis: str = Field(
        default="",
        description=(
            "LA tesis del día en una frase de máx 150 chars: qué ha cambiado hoy en la carrera AGI. "
            "Debe ser una lectura estratégica propia, no el titular de la noticia principal. "
            "Si el día es flojo, dilo con honestidad ('Día sin movimientos de frontera; ...')."
        )
    )
    signals: List[str] = Field(default_factory=list, description="2-5 bullets, 1 línea, lo que ha cambiado hoy")
    risks: List[str] = Field(default_factory=list, description="1-3 riesgos o cuellos de botella reales")
    watch: List[str] = Field(default_factory=list, description="2-3 señales concretas y falsables a vigilar")
    entities_top: List[str] = Field(default_factory=list, description="hasta 5 actores dominantes hoy")


class BatchOut(BaseModel):
    briefing: Briefing
    results: List[RankOut] = Field(default_factory=list)


SYSTEM = (
    "Eres el analista jefe de inteligencia estratégica de un solo lector. "
    "Tu trabajo NO es resumir noticias: es decidir qué merece su atención hoy y por qué. "
    "Eres severo filtrando. Un radar con 3 señales reales vale más que uno con 15 items de relleno. "
    "Marcar algo irrelevante como 'signal' es un fallo grave; descartar relleno nunca lo es. "
    "No inventes hechos ni cifras que no estén en el material. "
    "Escribe en castellano de España: directo, técnico, sin lenguaje corporativo ni superlativos."
)


def rank_batch(items: list[dict], model: str = "gemini-2.5-flash") -> dict:
    """items: dicts con keys id, source, title, summary, url.

    Devuelve {"briefing": {...}, "map": {id: {...}}}.
    """
    global client
    if client is None:
        client = genai.Client()
    model = (os.getenv("GEMINI_MODEL") or model).strip()

    payload = []
    for it in items:
        payload.append({
            "id": int(it["id"]),
            "source": (it.get("source") or "")[:80],
            "title": (it.get("title") or "")[:240],
            "summary": (it.get("summary") or "")[:700],
            "url": (it.get("url") or "")[:300],
        })

    prompt = (
        f"{READER_THESIS}\n"
        "═══════════════════════════════════════════════════════════
"
        "TAREA\n\n"
        "1) Juzga CADA item contra la tesis del lector. Devuelve un objeto por item,\n"
        "   con el MISMO id que recibes. No omitas ninguno, no reordenes, no inventes ids.\n\n"
        "2) Genera un briefing global basado SOLO en los items marcados signal/context.\n\n"
        "REGLAS DE JUICIO\n"
        "- Sé severo: en un día normal la mayoría de items son noise. Es lo esperado.\n"
        "- 'signal' se reserva a lo que de verdad mueve la carrera AGI o el reparto de poder.\n"
        "- Un lanzamiento real de modelo de frontera, un salto de capacidad, un cambio de precios\n"
        "  relevante, un movimiento de compute a gran escala o un control de exportación: signal.\n"
        "- Un fichaje, una beca, un tutorial, un bump de versión, un paper incremental,\n"
        "  una aplicación vertical de nicho: noise, sin excepciones.\n"
        "- relevance mide relevancia para ESTE lector, no calidad del artículo.\n"
        "  Un artículo excelente sobre algo que no le importa tiene relevance baja.\n"
        "- so_what: la consecuencia, no el resumen. Si no sabes decir por qué le importa,\n"
        "  probablemente sea noise.\n\n"
        "REGLAS DEL BRIEFING\n"
        "- thesis: tu lectura del día en una frase. Si no ha pasado nada relevante, dilo.\n"
        "- signals: entre 2 y 5 bullets. Menos es mejor. Sin relleno.\n"
        "- watch: señales falsables, comprobables en días o semanas.\n"
        "- Todo en castellano de España.\n\n"
        "Devuelve SOLO JSON: {\"briefing\":{...},\"results\":[...]}\n\n"
        f"ITEMS:\n{json.dumps(payload, ensure_ascii=False)}"
    )

    resp = client.models.generate_content(
        model=model,
        contents=[{"role": "user", "parts": [{"text": prompt}]}],
        config={
            "system_instruction": SYSTEM,
            "response_mime_type": "application/json",
            "response_json_schema": BatchOut.model_json_schema(),
        },
    )

    raw_text = (resp.text or "").strip()
    if not raw_text:
        raise RuntimeError("Gemini returned empty response text.")

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Gemini returned invalid JSON: {exc.msg}") from exc

    validated = BatchOut.model_validate(data)

    out_map: dict[int, dict] = {}
    for r in validated.results:
        out_map[int(r.id)] = r.model_dump()

    return {
        "briefing": validated.briefing.model_dump(),
        "map": out_map,
    }
