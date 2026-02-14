# src/config.py

CATEGORY_LABELS = {
    "models": "Modelos",
    "infra": "Infraestructura/HW",
    "policy": "Política/Regulación",
    "security": "Seguridad",
    "research": "Research",
    "products": "Producto",
    "chips": "Chips",
    "robotics": "Robótica",
    "compute": "Compute",
    "misc": "Misc",
}

KNOWN_ENTITIES = [
    "OpenAI", "NVIDIA", "Anthropic", "Google", "DeepMind", "Microsoft", "Meta", "Apple",
    "Amazon", "AWS", "Azure", "TSMC", "AMD", "Intel", "Arm", "Tesla",
    "Cerebras", "Groq", "Mistral", "Hugging Face", "Stability AI",
    "ByteDance", "Alibaba", "Tencent", "Samsung", "Qualcomm",
]

ENTITY_ALIASES = {"UK": "Reino Unido", "US": "EEUU", "USA": "EEUU", "EU": "UE"}

STOP_ENTITIES = {"AI", "ML", "LLM", "RAG", "RL", "GPU", "CPU", "API", "SDK", "OSS", "PDF", "HTML"}
ALLOW_ACRONYMS = {"AWS", "TSMC", "AMD", "ARM", "NVIDIA", "GPT", "CUDA", "EEUU", "UE"}
