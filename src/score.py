import re

KEYWORDS = {
    "infra": [
        "datacenter","data center","power","grid","substation","cooling",
        "hbm","hbm3","hbm3e","cows","cowos","packaging","2.5d","3d",
        "tsmc","samsung","intel foundry","substrate","interconnect",
        "blackwell","hopper","gb200","mi300","venice","diamond rapids","dram"
    ],
    "models": [
        "llm","model","reasoning","agent","tool","mcp","alignment","rl",
        "inference","training","token","context","benchmark","eval",
        "multimodal","transformer","mixture of experts","moe"
    ],
    "invest": [
        "earnings","guidance","capex","opex","margin","backlog","revenue",
        "supply","shortage","constraint","price","pricing"
    ],
    "geopol": [
        "export control","sanction","china","taiwan","biden","eu ai act","bis",
        "sovereign","regulation","chip act"
    ],
    "hype": [
        "breakthrough","state-of-the-art","sota","launch","released","announces",
        "preview","new","first","record","massive"
    ],
}

def _count_hits(text: str, words: list[str]) -> int:
    t = text.lower()
    hits = 0
    for w in words:
        if w in t:
            hits += 1
    return hits

def score_item(title: str, summary: str, source: str) -> dict:
    text = f"{title}\n{summary}".strip()
    infra = _count_hits(text, KEYWORDS["infra"])
    models = _count_hits(text, KEYWORDS["models"])
    invest = _count_hits(text, KEYWORDS["invest"])
    geopol = _count_hits(text, KEYWORDS["geopol"])
    hype = _count_hits(text, KEYWORDS["hype"])

    # pesos base (tu 40/40/20/20 simplificado en 100)
    # 40 infra + 40 invest + 20 models + 20 geopol pero normalizamos a 100
    raw = (infra * 10) + (invest * 10) + (models * 5) + (geopol * 5) + (hype * 3)

    # bonus por fuente (ajústalo luego)
    src = (source or "").lower()
    if "semiwiki" in src:
        raw += 10
    if "nvidia" in src:
        raw += 8
    if "arxiv" in src:
        raw += 4
    if "deepmind" in src or "google ai" in src:
        raw += 6

    score = max(0, min(100, raw))
    tags = []
    if infra: tags.append("infra")
    if invest: tags.append("invest")
    if models: tags.append("models")
    if geopol: tags.append("geopol")

    # categoría principal
    primary = "misc"
    if infra >= max(models, invest, geopol):
        primary = "infra"
    elif invest >= max(models, infra, geopol):
        primary = "invest"
    elif models >= max(infra, invest, geopol):
        primary = "models"
    elif geopol > 0:
        primary = "geopol"

    return {"score": score, "primary": primary, "tags": tags}
