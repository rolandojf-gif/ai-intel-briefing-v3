import re

KEYWORDS = {
    "infra": [
        "datacenter","data center","power","grid","substation","cooling",
        "hbm","hbm3","hbm3e","cows","cowos","packaging","2.5d","3d",
        "tsmc","samsung","intel foundry","substrate","interconnect",
        "blackwell","hopper","gb200","mi300","mi350","venice","diamond rapids","dram",
        "cluster","rack","accelerator","cuda","xpu","asic","wafer","foundry"
    ],
    "models": [
        "llm","model","reasoning","agent","tool","mcp","alignment","rl",
        "inference","training","token","context","benchmark","eval",
        "multimodal","transformer","mixture of experts","moe","frontier",
        "gpt","claude","gemini","deepseek","open weights","safety","post-training"
    ],
    "invest": [
        "earnings","guidance","capex","opex","margin","backlog","revenue",
        "supply","shortage","constraint","price","pricing","api","cost","tokens",
        "valuation","funding","investment","deal","contract","customer","demand"
    ],
    "geopol": [
        "export control","sanction","china","taiwan","biden","eu ai act","bis",
        "sovereign","regulation","chip act","policy","nist","eu commission",
        "huawei","bytedance","alibaba","tencent","national security"
    ],
    "hype": [
        "breakthrough","state-of-the-art","sota","launch","released","announces",
        "preview","new","first","record","massive"
    ],
    "promo": [
        "webinar","applications now open","event","award","tips","organizing your space",
        "special presentation","sponsored","meet us","join us"
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
    text_l = text.lower()
    infra = _count_hits(text, KEYWORDS["infra"])
    models = _count_hits(text, KEYWORDS["models"])
    invest = _count_hits(text, KEYWORDS["invest"])
    geopol = _count_hits(text, KEYWORDS["geopol"])
    hype = _count_hits(text, KEYWORDS["hype"])
    promo = _count_hits(text, KEYWORDS["promo"])

    raw = (infra * 12) + (invest * 12) + (models * 9) + (geopol * 11) + (hype * 2)

    hard_signal_patterns = [
        r"\b(gpt|claude|gemini|deepseek|llama|mistral)[-\s]?\d",
        r"\b(api|pricing|price|cost|tokens?)\b",
        r"\b(capex|revenue|margin|earnings|guidance|backlog)\b",
        r"\b(hbm|gb200|blackwell|mi300|tpu|gpu|datacenter|data center)\b",
        r"\b(export control|sanction|eu ai act|nist|sovereign)\b",
        r"\b(agent|agents|mcp|coding|tool use|autonomous)\b",
    ]
    hard_signals = sum(1 for pat in hard_signal_patterns if re.search(pat, text_l))
    raw += hard_signals * 9

    if re.search(r"\b(now available|available in the api|released|ships?|launches?)\b", text_l) and hard_signals:
        raw += 8
    if re.search(r"\b(frontier|reasoning|benchmark|eval|multimodal)\b", text_l) and models:
        raw += 6
    if re.search(r"\b(china|huawei|deepseek|export control|sanction)\b", text_l) and (geopol or infra):
        raw += 8
    if promo and hard_signals == 0:
        raw -= min(24, promo * 8)

    src = (source or "").lower()
    if "semiwiki" in src:
        raw += 8
    if "nvidia" in src:
        nvidia_strategic_signal = (infra + invest + geopol) > 0 or any(
            k in text_l for k in ("datacenter", "hbm", "gpu", "inference", "training", "pricing", "capex")
        )
        if nvidia_strategic_signal:
            raw += 5
    if "arxiv" in src:
        raw += 3
    if "deepmind" in src or "google ai" in src:
        raw += 4
    if src.startswith("x "):
        raw += 4
        if any(x in src for x in ("openai", "anthropic", "deepmind", "nvidia", "deepseek", "xai", "sama", "karpathy")):
            raw += 4

    score = max(0, min(100, raw))
    tags = []
    if infra: tags.append("infra")
    if invest: tags.append("invest")
    if models: tags.append("models")
    if geopol: tags.append("geopol")

    # categoría principal
    counts = {
        "infra": infra,
        "invest": invest,
        "models": models,
        "geopol": geopol,
    }
    max_hits = max(counts.values())
    if max_hits == 0:
        primary = "misc"
    elif infra == max_hits:
        primary = "infra"
    elif invest == max_hits:
        primary = "invest"
    elif models == max_hits:
        primary = "models"
    else:
        primary = "geopol"

    return {"score": score, "primary": primary, "tags": tags}
