from google import genai
from pydantic import BaseModel, Field
from typing import List, Literal, Optional
import json

client = genai.Client()

Primary = Literal["infra", "models", "invest", "geopol", "misc"]

class LLMRank(BaseModel):
    score: int = Field(ge=0, le=100, description="Importancia/impacto para IA. 0 nada, 100 crítico.")
    primary: Primary = Field(description="Categoría principal.")
    tags: List[str] = Field(default_factory=list, description="Tags cortos (máx 6).")
    why: str = Field(description="1 frase: por qué importa (máx 160 chars).")
    entities: List[str] = Field(default_factory=list, description="Empresas/chips/proyectos clave (máx 6).")

SYSTEM = (
    "Eres un analista de IA/hardware/inversión. Puntúa impacto real (no hype). "
    "No inventes. Usa solo la info dada."
)

def rank_item(title: str, summary: str, source: str, url: str, model: str = "gemini-3-flash-preview") -> dict:
    prompt = f"""
Fuente: {source}
Título: {title}
Resumen: {summary[:1200]}
URL: {url}

Devuelve SOLO JSON válido siguiendo el schema.
Reglas:
- score 0-100 (impacto/urgencia para IA)
- primary en: infra/models/invest/geopol/misc
- tags: 2-6 tags cortos en minúscula (ej: hbm, cowos, datacenter, export controls, earnings, funding)
- why: 1 frase corta
- entities: 0-6 (TSMC, NVIDIA, AMD, Samsung, OpenAI, Anthropic, etc.)
""".strip()

    resp = client.models.generate_content(
        model=model,
        contents=[{"role": "user", "parts": [{"text": prompt}]}],
        config={
            "system_instruction": SYSTEM,
            "response_mime_type": "application/json",
            "response_json_schema": LLMRank.model_json_schema(),
        },
    )

    # response.text debería ser JSON limpio; aun así, blindaje mínimo:
    data = json.loads(resp.text)
    validated = LLMRank.model_validate(data)
    return validated.model_dump()
