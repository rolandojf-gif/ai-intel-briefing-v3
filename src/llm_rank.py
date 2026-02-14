from google import genai
from pydantic import BaseModel, Field
from typing import List, Literal
import json
import os


client = None


Primary = Literal["infra", "models", "invest", "geopol", "misc"]

class RankOut(BaseModel):
    id: int
    score: int = Field(ge=0, le=100)
    primary: Primary
    tags: List[str] = Field(default_factory=list)
    why: str
    entities: List[str] = Field(default_factory=list)

class Briefing(BaseModel):
    signals: List[str] = Field(default_factory=list, description="5 señales (1 línea c/u)")
    risks: List[str] = Field(default_factory=list, description="3 riesgos/cuellos de botella")
    watch: List[str] = Field(default_factory=list, description="3 cosas a vigilar mañana")
    entities_top: List[str] = Field(default_factory=list, description="3 entidades dominantes")

class BatchOut(BaseModel):
    briefing: Briefing
    results: List[RankOut] = Field(default_factory=list)

SYSTEM = (
    "Eres analista de IA/hardware/inversión. "
    "Puntúa impacto real (no hype). No inventes. "
    "Usa solo título+resumen+fuente. "
    "Sé conciso."
)

def rank_batch(items: list[dict], model: str = "gemini-3-flash-preview") -> dict:
    """
    items: lista de dicts con keys: id, source, title, summary, url
    Devuelve dict:
      {
        "briefing": {...},
        "map": {id: {...rank fields...}}
      }
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
        "Tarea:\n"
        "1) Para cada item, devuelve score/primary/tags/why/entities.\n"
        "2) Además, genera un briefing global basado SOLO en estos items.\n\n"
        "Reglas ranking:\n"
        "- score 0-100 (impacto real para IA)\n"
        "- primary: infra/models/invest/geopol/misc\n"
        "- tags: 2-6 tags en minúscula\n"
        "- why: 1 frase <=160 chars\n"
        "- entities: 0-6 nombres clave\n\n"
        "Reglas briefing:\n"
        "- signals: exactamente 5 bullets (1 línea, máximo 120 chars)\n"
        "- risks: exactamente 3 bullets\n"
        "- watch: exactamente 3 bullets\n"
        "- entities_top: exactamente 3 (nombres)\n\n"
        "Devuelve SOLO JSON con forma:\n"
        "{\"briefing\":{...},\"results\":[...]}\n\n"
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
