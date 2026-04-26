# src/config.py

CATEGORY_LABELS = {
    "models": "Modelos",
    "infra": "Infraestructura/HW",
    "invest": "Economía/mercado",
    "geopol": "Geopolítica",
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
    "ByteDance", "Alibaba", "Tencent", "Samsung", "Qualcomm", "xAI", "DeepSeek",
    "Gemini", "Claude", "GPT-5.5", "GPT-5", "ChatGPT", "Copilot", "CUDA",
    "Huawei", "Baidu", "CoreWeave", "SoftBank", "Oracle", "Broadcom", "SK hynix",
]

ENTITY_ALIASES = {
    "UK": "Reino Unido",
    "US": "EEUU",
    "USA": "EEUU",
    "EU": "UE",
    "Google DeepMind": "DeepMind",
    "OpenAIDevs": "OpenAI",
    "OpenAI Developers": "OpenAI",
    "Nvidia": "NVIDIA",
    "Xai": "xAI",
}

STOP_ENTITIES = {
    "AI", "ML", "LLM", "RAG", "RL", "GPU", "CPU", "API", "SDK", "OSS", "PDF", "HTML",
    "Update", "Quote", "Thread", "Post", "Tweet", "Image", "Video", "New", "Apr", "May",
    "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "CEO", "CTO",
    "Our", "The", "This", "That", "Today", "Tomorrow", "Project", "Research", "Blog",
    "Pro", "Developers", "Resources", "Link", "Read", "More", "Welcome", "Live",
    "His", "Her", "Their", "Introducing", "Interview", "CEO Interview",
}
ALLOW_ACRONYMS = {"AWS", "TSMC", "AMD", "ARM", "NVIDIA", "GPT", "CUDA", "EEUU", "UE", "xAI"}
