from google import genai
from pydantic import BaseModel, Field
from typing import List, Literal
import json

client = genai.Client()

Primary = Literal["infra", "models", "invest", "geopol", "misc"]

class RankOut(BaseModel):
    id: int = Field(description="ID del item de entrada")
    score: int = Field(ge=0, le=100, description="Impacto real (0-100)")
    primary: Primary = Field(description="Categoría principal")
    tags: List[str] = Field(default_factory=list, description="2-6 tags cortos")
    why: str = Field(description="1 frase corta: por qué importa (<=160 chars)")
    entities: List[str] = Field(default_factory=list, description="0-6 entidades clave")

class BatchOut(BaseModel):
    results: List[RankOut] = Field(default_factory=list)

SYSTEM = (
    "Eres un analista de IA/hardware/inversión. "
    "Puntúa impacto real (no hype). No inventes. "
    "Usa solo el título+resumen dados. "
    "Devuelve JSON válido y compacto."
)

def rank_batch(items: list[dict], model: str = "gemini-3-flash-preview") -> dict[int, dict]:
    """
    items: lista de dicts con keys: id(int), source(str), title(str), summary(str), url(str)
    Devuelve: {id: {"score":..,"primary":..,"tags":[..],"why":..,"entities":[..]}}
    """
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
        "Clasifica y puntúa cada item.\n"
        "Reglas:\n"
        "- score 0-100 por impacto real para IA (chips, datacenters, modelos, inversión, regulación)\n"
        "- primary: infra/models/invest/geopol/misc\n"
        "- tags: 2-6 tags en minúscula (ej: hbm3e, cowos, datacenter, inference, earnings, funding, export controls)\n"
        "- why: 1 frase corta <=160 chars\n"
        "- entities: 0-6 (TSMC, NVIDIA, AMD, Samsung, OpenAI, Anthropic...)\n"
        "Devuelve SOLO JSON con forma: {\"results\": [ ... ]}\n"
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

    data = json.loads(resp.text)
    validated = BatchOut.model_validate(data)

    out: dict[int, dict] = {}
    for r in validated.results:
        out[int(r.id)] = r.model_dump()
    return out
