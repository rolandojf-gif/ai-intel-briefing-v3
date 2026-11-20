"""Relevance gate + strategic briefing.

Contrato v2 (2026-08): el LLM ya no puntúa "impacto genérico". Emite un JUICIO
estructurado contra una tesis explícita (ver READER_THESIS). Todo lo que marca
`noise` se ELIMINA del radar, no se rankea más abajo.

Esto es deliberado: el fallo del contrato v1 era pedir "puntúa impacto real"
sin decir impacto para quién, con lo que el modelo premiaba novedad académica
(un paper de estimación de peso de helicópteros sacaba 62/100).

Los tres puntos que instruyen al modelo sobre severidad (SYSTEM, la descripcion
del campo `verdict` y las REGLAS DE JUICIO del prompt) deben decir lo MISMO.
Convivieron pidiendo severidad y generosidad a la vez, y el volumen del radar
pasaba a depender de como resolviera el modelo la contradiccion.
"""

from google import genai
from pydantic import BaseModel, Field
from typing import List, Literal

from src.evidence import source_evidence
import json
import os


client = None


# -- Tesis del lector --------------------------------------------------------
# Esto es lo que convierte el radar en personal. Si cambian los intereses,
# se cambia aqui y todo el ranking se realinea.
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
            "signal = noticia real con consecuencia: nuevo modelo, hardware/chips, agentes, "
            "economía de modelos o movimiento de mercado estratégico. Va al radar principal. "
            "context = análisis de fondo o pieza secundaria; aporta perspectiva pero no cambia nada hoy. "
            "noise = marketing corporativo, fichajes, webinars, eventos, tutoriales, bumps de versión "
            "y papers incrementales sin impacto. "
            "Ante la duda entre signal y context, elige signal. Ante la duda entre context y noise, "
            "elige noise: el relleno no entra al radar."
        )
    )
    relevance: int = Field(ge=0, le=100, description="Relevancia para la tesis del lector, no calidad del artículo")
    theme: Theme

    evidence_kind: Literal["confirmed", "reported", "inference", "speculation"]
    evidence_quote: str = Field(description="Una frase literal del título o resumen que sustenta la noticia y su lectura. Vacío si falta.")
    repeat_of: int = Field(default=0, description="Número del hecho ya publicado si no aporta novedad material; 0 si es nuevo.")
    prior_quote: str = Field(default="", description="Solo para repeat_of: fragmento literal del histórico que acredita el mismo hecho.")

    headline_es: str = Field(
        description=(
            "Titular reescrito en castellano de España, afilado y concreto, máx 90 chars. "
            "Debe decir QUÉ ha pasado, no vender. Nada de clickbait ni lenguaje de marketing. "
            "Si el original viene truncado o sucio, reconstruye el sentido sin inventar hechos. "
            "Es el titular de ESTE item: di lo que este item concreto cuenta o añade. "
            "Nunca repitas el titular de otro item del lote."
        )
    )
    so_what: str = Field(
        description=(
            "Por qué le importa AL LECTOR en 1 frase seca, máx 150 chars. NO resumas el artículo, "
            "no repitas el titular ni quién gana/pierde (eso va en power_shift). Ve al grano."
        )
    )
    power_shift: str = Field(
        default="",
        description=(
            "Formato telegráfico 'X gana / Y pierde', máx 65 chars. Solo nombres/actores breves, "
            "sin frases explicativas. Vacío si el item no desplaza poder."
        )
    )
    watch_next: str = Field(
        default="",
        description=(
            "Hito concreto y verificable en días o semanas, máx 75 chars. Empieza directo por el dato "
            "o evento (prohibido abrir con 'Evaluar...', 'Monitorizar...', 'Observar...' o 'Ver si...'). "
            "Vacío si no aplica."
        )
    )
    entities: List[str] = Field(default_factory=list, description="0-5 organizaciones/personas clave")
    # Version inglesa para el boton EN de la web. Misma llamada: sin coste extra
    # de peticiones, solo algo mas de texto de salida.
    headline_en: str = Field(default="", description="headline_es translated into natural English, max 90 chars. Same facts.")
    so_what_en: str = Field(default="", description="so_what in natural English, max 150 chars.")
    power_shift_en: str = Field(default="", description="power_shift in English ('X gains / Y loses'), max 65 chars. Empty if power_shift is empty.")
    watch_next_en: str = Field(default="", description="watch_next in English, max 75 chars, no filler verbs. Empty if watch_next is empty.")
    same_story_as: int = Field(
        default=0,
        description=(
            "Si este item cuenta EL MISMO HECHO que otro item del lote sin añadir nada nuevo "
            "(la misma noticia en otro medio), pon aquí el id del item que mejor lo cuenta. "
            "0 si es el mejor, el único, o si aporta un desarrollo propio (una reacción, una "
            "consecuencia, un dato nuevo): eso es otro item, con su propio titular."
        ),
    )


class BriefReference(BaseModel):
    field: Literal["thesis", "signals", "risks", "watch"]
    index: int = Field(ge=0, description="Posición desde 0 (tesis: 0)")
    ids: List[int] = Field(description="Items cuyos extractos justifican esta conclusión o hito")


class Briefing(BaseModel):
    references: List[BriefReference] = Field(default_factory=list)
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
    thesis_en: str = Field(default="", description="thesis in natural English, max 150 chars.")
    signals_en: List[str] = Field(default_factory=list, description="signals in English, same order.")
    risks_en: List[str] = Field(default_factory=list, description="risks in English, same order.")
    watch_en: List[str] = Field(default_factory=list, description="watch in English, same order.")


class BatchOut(BaseModel):
    briefing: Briefing
    results: List[RankOut] = Field(default_factory=list)


SYSTEM = (
    "Eres el analista jefe de inteligencia estratégica de un solo lector. "
    "Tu trabajo NO es resumir noticias: es decidir qué merece su atención hoy y por qué. "
    "Cubre con generosidad lo que de verdad ocurre en la industria —lanzamientos, chips, "
    "precios, agentes, movimientos de mercado— y corta sin piedad el relleno corporativo. "
    "El error que debes evitar no es incluir de más, sino dejar pasar promoción disfrazada "
    "de noticia o publicar algo sin poder decir qué consecuencia tiene. "
    "No inventes hechos ni cifras que no estén en el material. "
    "Escribe en castellano de España: directo, técnico, sin lenguaje corporativo ni superlativos."
)


# google-genai 3.x cambio la API por defecto de v1beta a v1, y v1 rechaza
# system_instruction con un 400. Como requirements.txt no fijaba version, el CI
# instalo la 3.x y el radar paso a modo degradado (2026-11-07) sin tocar codigo.
# Se fija aqui para no depender del valor por defecto del SDK.
GEMINI_API_VERSION = "v1beta"


def make_client():
    return genai.Client(http_options={"api_version": GEMINI_API_VERSION})


def rank_batch(
    items: list[dict],
    model: str = "gemini-2.5-flash",
    recent_headlines: list[str] | None = None,
) -> dict:
    """items: dicts con keys id, source, title, summary, url.

    Devuelve {"briefing": {...}, "map": {id: {...}}}.
    """
    global client
    if client is None:
        client = make_client()
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

    recent_block = ""
    cleaned_recent = []
    if recent_headlines:
        cleaned_recent = [str(h).strip()[:320] for h in recent_headlines if str(h).strip()][:20]
        if cleaned_recent:
            recent_lines = "\n".join(f"{i}. {h}" for i, h in enumerate(cleaned_recent, 1))
            recent_block = (
                "HISTÓRICO RECIENTE (ya publicado en las últimas 48h; si un item solo repite "
                "lo mismo sin dato, precio, lanzamiento ni consecuencia nueva, indica repeat_of "
                "y copia prior_quote del número citado):\n"
                f"{recent_lines}\n\n"
            )

    prompt = (
        f"{READER_THESIS}\n"
        "=========================================================\n"
        "TAREA\n\n"
        "1) Juzga CADA item contra la tesis del lector. Devuelve un objeto por item,\n"
        "   con el MISMO id que recibes. No omitas ninguno, no reordenes, no inventes ids.\n\n"
        "2) Genera un briefing global basado SOLO en los items marcados signal/context.\n\n"
        "REGLAS DE JUICIO\n"
        "- 'signal' es el caso normal para una noticia real: lanzamiento de modelo, salto de\n"
        "  capacidad, chips y compute, precios y márgenes, agentes, o un movimiento de mercado\n"
        "  con consecuencia. No lo reserves solo a lo histórico; el radar debe reflejar el día.\n"
        "- 'context' es para el análisis de fondo y lo secundario: aporta perspectiva pero no\n"
        "  cambia nada hoy.\n"
        "- 'noise' es marketing corporativo, fichajes, becas, webinars, eventos, patrocinios,\n"
        "  tutoriales, bumps de versión, papers incrementales y verticales de nicho.\n"
        "  Aquí sí sé implacable: eso no llega nunca al radar.\n"
        "- relevance mide relevancia para ESTE lector, no calidad del artículo.\n"
        "  Un artículo excelente sobre algo que no le importa tiene relevance baja.\n"
        "- so_what: la consecuencia, no el resumen. Si no sabes decir qué consecuencia tiene,\n"
        "  entonces es noise.\n"
        "- Sin redundancia entre campos: headline dice QUÉ pasó; so_what explica la consecuencia\n"
        "  (máx 150 chars); power_shift solo nombra 'X gana / Y pierde' (máx 65 chars); watch_next\n"
        "  va directo al hito verificable (máx 75 chars, sin verbos de relleno).\n\n"
        "VARIOS ITEMS SOBRE LO MISMO\n"
        "- Un gran suceso llega contado por muchos medios. NO les pongas a todos el mismo\n"
        "  titular ni el mismo so_what: el lector vería la misma card repetida.\n"
        "- La misma noticia en otro medio, sin nada nuevo: same_story_as = id del mejor item.\n"
        "- Un desarrollo distinto del mismo suceso (reacción, petición, consecuencia, análisis\n"
        "  con tesis propia): same_story_as = 0 y un titular y un so_what que digan qué añade.\n\n"
        "EVIDENCIA: confirmed solo para un acto propio documentado por fuente primaria; "
        "reported para prensa, testimonios y métricas atribuidas; inference para análisis; speculation para hipótesis. "
        "Conserva modalidad y atribución ES/EN. No conviertas planes, benchmarks propios ni rumores en hechos. "
        "so_what y power_shift son inferencias sobre evidence_quote; omítelos si ese extracto no los sustenta. "
        "Una confirmación posterior de un rumor, una métrica nueva o una reacción documentada son desarrollos distintos. "
        "La mera reescritura o una segunda fuente sin novedades es repetición.\n"
        "REGLAS DEL BRIEFING\n"
        "- Aporta references para cada tesis, señal, riesgo e hito. Usa solo los extractos literales de esos ids. "
        "Cada referencia debe sustentar toda la frase en ambos idiomas. Omite las que no puedas respaldar.\n"
        "- watch y watch_next: actor, acción observable y objeto, umbral o fecha concreta si procede. "
        "Formula el resultado observable en presente afirmativo, como titular futuro, en ambos idiomas.\n"
        "- thesis: tu lectura del día en una frase. Si no ha pasado nada relevante, dilo.\n"
        "- signals: entre 2 y 5 bullets. Menos es mejor. Sin relleno.\n"
        "- watch: señales falsables, comprobables en días o semanas.\n"
        "- Todo en castellano de España.\n\n"
        "INGLÉS\n"
        "- Los campos *_en son la versión inglesa de su campo en español: mismo contenido,\n"
        "  inglés natural y directo, sin añadir ni quitar hechos.\n\n"
        f"{recent_block}"
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
    inputs = {it["id"]: it for it in payload}
    eligible = {r.id for r in validated.results if r.verdict != "noise"}
    for r in validated.results:
        if r.id not in inputs or r.id in out_map:
            raise RuntimeError("Gemini returned unknown or duplicate result id.")
        result = r.model_dump()
        if r.same_story_as == r.id or r.same_story_as not in eligible:
            result["same_story_as"] = 0
        if (0 < r.repeat_of <= len(cleaned_recent) and source_evidence(inputs[r.id], r.evidence_quote)
                and len(r.prior_quote.strip()) >= 12
                and r.prior_quote in cleaned_recent[r.repeat_of - 1]):
            result["verdict"] = "noise"
        out_map[r.id] = result

    return {
        "briefing": validated.briefing.model_dump(),
        "map": out_map,
    }
