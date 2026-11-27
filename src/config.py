# src/config.py
from __future__ import annotations

from datetime import date, datetime, timezone
try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]

RADAR_TZ_NAME = "Europe/Madrid"


def radar_now(now: datetime | None = None) -> datetime:
    """Hora actual en la zona horaria editorial del radar (Europe/Madrid)."""
    if now is None:
        if ZoneInfo is not None:
            try:
                return datetime.now(ZoneInfo(RADAR_TZ_NAME))
            except Exception:
                pass
        return datetime.now(timezone.utc)
    dt = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
    if ZoneInfo is not None:
        try:
            return dt.astimezone(ZoneInfo(RADAR_TZ_NAME))
        except Exception:
            pass
    return dt.astimezone(timezone.utc)


def radar_today(now: datetime | None = None) -> date:
    return radar_now(now).date()


def radar_today_str(now: datetime | None = None) -> str:
    return radar_today(now).strftime("%Y-%m-%d")


LEAD_SLOT_COUNT = 3  # hero + las dos cards siguientes


def demote_repeats_from_lead(items: list[dict], lead_n: int = LEAD_SLOT_COUNT) -> list[dict]:
    """Hard-gate de novedad: un repeat no puede ser hero ni top-N si hay fresco.

    El radar es "qué ha cambiado hoy". La penalización de score no basta:
    TSMC (repeat) seguía saliendo #2 por encima de señales nuevas.
    Si no hay suficientes items frescos, se rellenan los huecos con repeats
    para no dejar la portada vacía.
    """
    if not items or lead_n <= 0:
        return items

    fresh = [it for it in items if not it.get("is_repeat")]
    repeats = [it for it in items if it.get("is_repeat")]
    if not fresh:
        return items

    lead: list[dict] = []
    used: set[int] = set()
    for it in fresh:
        if len(lead) >= lead_n:
            break
        lead.append(it)
        used.add(id(it))
    if len(lead) < lead_n:
        for it in repeats:
            if len(lead) >= lead_n:
                break
            lead.append(it)
            used.add(id(it))

    rest = [it for it in items if id(it) not in used]
    return lead + rest


CATEGORY_LABELS = {
    "models": "Modelos",
    "infra": "Infraestructura/HW",
    "invest": "Economía/mercado",
    "geopol": "Geopolítica",
    "policy": "Política/Regulación",
    "security": "Seguridad",
    "research": "Investigación",
    "products": "Producto",
    "chips": "Chips",
    "robotics": "Robótica",
    "compute": "Computación",
    "misc": "Otros",
}

KNOWN_ENTITIES = [
    "OpenAI", "NVIDIA", "Anthropic", "Google", "DeepMind", "Microsoft", "Meta", "Apple",
    "Amazon", "AWS", "Azure", "TSMC", "AMD", "Intel", "Arm", "Tesla",
    "Cerebras", "Groq", "Mistral", "Hugging Face", "Stability AI",
    "ByteDance", "Alibaba", "Tencent", "Samsung", "Qualcomm", "xAI", "DeepSeek",
    "Gemini 4 Hydrogen", "Gemini 4", "Gemini 3.5", "Gemini 3", "Gemini",
    "Claude Fable", "Claude 5", "Claude 4", "Claude 3.7", "Claude 3.5", "Claude",
    "GPT-6", "GPT-5.5", "GPT-5", "GPT-4.5", "o1", "o3", "o4", "ChatGPT",
    "Grok 4", "Grok 3", "Grok Imagine", "Grok",
    "DeepSeek-R2", "DeepSeek-R1", "DeepSeek-V4", "DeepSeek-V3", "Kimi K3", "Kimi", "Moonshot AI",
    "GLM-5", "GLM-4", "GLM", "Zhipu AI", "Qwen 3", "Qwen 2.5", "Qwen",
    "Llama 4", "Llama 3.3", "Llama", "Mistral Large", "Codestral",
    "Fable", "Mythos", "Sol", "MiniMax", "01.AI", "Yi", "Baichuan",
    "Cohere", "Scale AI", "Together AI", "ASML", "SMIC", "Blackwell", "Rubin",
    "Huawei", "Baidu", "CoreWeave", "SoftBank", "Oracle", "Broadcom", "SK hynix", "Micron",
    "Jensen Huang", "Sam Altman", "Dario Amodei", "Demis Hassabis", "Elon Musk", "Liang Wenfeng",
]

ENTITY_ALIASES = {
    # Actores politicos con nombre neutro: la entidad sale igual en ES y en EN.
    "Administración Trump": "Trump",
    "Gobierno de Trump": "Trump",
    "Trump Administration": "Trump",
    "Donald Trump": "Trump",
    "UK": "Reino Unido",
    "US": "EEUU",
    "USA": "EEUU",
    "EU": "UE",
    "Google DeepMind": "DeepMind",
    "OpenAIDevs": "OpenAI",
    "OpenAI Developers": "OpenAI",
    "Nvidia": "NVIDIA",
    "Xai": "xAI",
    "Kimi k3": "Kimi K3",
    "Kimi-K3": "Kimi K3",
    "Moonshot": "Moonshot AI",
    "MoonshotAI": "Moonshot AI",
    "Zhipu": "Zhipu AI",
    "ZhipuAI": "Zhipu AI",
    "Z.ai": "Zhipu AI",
    "GLM 5": "GLM-5",
    "GLM5": "GLM-5",
    "GLM-5.3": "GLM-5",
    "GLM 4": "GLM-4",
    "Qwen2.5": "Qwen 2.5",
    "Qwen3": "Qwen 3",
    "Alibaba Qwen": "Qwen",
    "DeepSeek-R2": "DeepSeek-R2",
    "DeepSeek-R1": "DeepSeek-R1",
    "DeepSeek-V4": "DeepSeek-V4",
    "DeepSeek-V3": "DeepSeek-V3",
    "Deepseek": "DeepSeek",
    "Claude 3.7": "Claude 3.7",
    "Claude 3.5": "Claude 3.5",
    "Gemini 4": "Gemini 4",
    "Gemini 3.5": "Gemini 3.5",
    "Gemini 3": "Gemini 3",
    "GPT-6": "GPT-6",
    "GPT-5": "GPT-5",
    "GPT-5.5": "GPT-5.5",
    "Fable Studio": "Fable",
    "Mythos AI": "Mythos",
    "Sol AI": "Sol",
}

STOP_ENTITIES = {
    "AI", "ML", "LLM", "RAG", "RL", "GPU", "CPU", "API", "SDK", "OSS", "PDF", "HTML",
    "Update", "Quote", "Thread", "Post", "Tweet", "Image", "Video", "New", "Apr", "May",
    "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "CEO", "CTO",
    "Our", "The", "This", "That", "Today", "Tomorrow", "Project", "Research", "Blog",
    "Pro", "Developers", "Resources", "Link", "Read", "More", "Welcome", "Live",
    "His", "Her", "Their", "Introducing", "Interview", "CEO Interview",
    "You", "Paul", "Misc", "Stop", "Making", "Stop Making", "Best", "Top", "Great",
    "Use", "Simulate", "Science", "Premium", "Regulation",
    "General Data Protection", "Introducing Gemini Omni", "TUIs", "TUI", "CLI", "CLIs",
    "Neoclouds", "Neocloud", "Guide", "Ranking", "Ranked", "Review", "Summary", "Overview",
    "How", "Why", "What", "When", "Where", "Build", "Building", "Run", "Running",
}
ALLOW_ACRONYMS = {"AWS", "TSMC", "AMD", "ARM", "NVIDIA", "GPT", "CUDA", "EEUU", "UE", "xAI", "GLM", "SMIC", "ASML", "MCP"}
