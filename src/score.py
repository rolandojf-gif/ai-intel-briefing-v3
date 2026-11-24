import re

KEYWORDS = {
    "infra": [
        "datacenter","data center","power","grid","substation","cooling",
        "hbm","hbm3","hbm3e","hbm4","cows","cowos","packaging","2.5d","3d",
        "tsmc","samsung","intel foundry","substrate","interconnect","smic","asml",
        "blackwell","b200","gb200","b100","rubin","r100","vr200","hopper","h100","h200","mi300","mi350","mi325",
        "venice","diamond rapids","dram","cluster","rack","accelerator","cuda","xpu","asic","wafer","foundry",
        "tpu","tpu v5","tpu v6","trainium","inferentia"
    ],
    "models": [
        "llm","model","reasoning","agent","agents","tool","tools","mcp","alignment","rl","rlhf",
        "inference","training","token","tokens","context","context window","benchmark","eval","evals",
        "multimodal","transformer","mixture of experts","moe","frontier","distillation",
        "test-time compute","thinking","chain of thought","synthetic data","weights","open weights",
        "gpt","gpt-6","gpt-5","gpt-4","claude","claude 4","claude 5","gemini","gemini 4","gemini 3.5",
        "deepseek","deepseek-r2","deepseek-r1","deepseek-v4","deepseek-v3",
        "kimi","kimi k3","glm","glm-5","glm-4","zhipu","qwen","qwen2.5","qwen 3","moonshot",
        "fable","mythos","sol","minimax","yi","01.ai","baichuan","llama","llama 4","llama 3.3",
        "mistral","codestral","pixtral","grok","grok 4","grok 3","grok imagine","o1","o3","o4","command r","phi"
    ],
    "invest": [
        "earnings","guidance","capex","opex","margin","backlog","revenue",
        "supply","shortage","constraint","price","pricing","api","cost","tokens","cost per token",
        "valuation","funding","investment","deal","contract","customer","demand","arr","series",
        "ipo","acquisition","acquires","merger","buyout","market cap","trillion","billion","rally","plunge","selloff","sell-off"
    ],
    "geopol": [
        "export control","sanction","sanctions","china","taiwan","biden","trump","eu ai act","bis",
        "sovereign","regulation","chip act","policy","nist","eu commission",
        "huawei","bytedance","alibaba","tencent","national security","entity list",
        "antitrust","doj","sec","ftc","subpoena","smuggling","tariff","tariffs"
    ],
    "hype": [
        "breakthrough","state-of-the-art","sota","launch","released","announces",
        "preview","new","first","record","massive","unveils","drops"
    ],
    "promo": [
        "webinar","applications now open","event","award","tips","organizing your space",
        "special presentation","sponsored","meet us","join us","booth","register now"
    ],
}

STRATEGIC_ACTOR_RE = re.compile(
    r"\b(nvidia|nvda|jensen huang|tsmc|asml|broadcom|sk hynix|micron|amd|arm|coreweave|"
    r"openai|sam altman|anthropic|dario amodei|deepmind|demis hassabis|xai|elon musk|"
    r"deepseek|liang wenfeng|mistral|qwen|alibaba|zhipu|moonshot|huawei|smic)\b"
)
GOVERNANCE_OR_MARKET_SHOCK_RE = re.compile(
    r"\b(ceo|chief executive|board|reinstat\w*|resign\w*|oust\w*|fired|step\w* down|succession|"
    r"ipo|acqui\w+|merger|buyout|antitrust|subpoena|doj|sec|ftc|probe|investigation|"
    r"trillion|market cap|rally|plung\w*|surge\w*|tumble\w*)\b"
)

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

    raw = (infra * 12) + (invest * 12) + (models * 11) + (geopol * 11) + (hype * 2)

    hard_signal_patterns = [
        r"\b(gpt|claude|gemini|deepseek|llama|mistral|qwen|kimi|glm|zhipu|moonshot|grok|minimax|yi|fable|mythos|sol|command|phi|o1|o3|o4|r1|r2|v3|v4)[-\s]?(v?\d|\b)",
        r"\b(api|pricing|price|cost|tokens?|cost per million|tps)\b",
        r"\b(capex|revenue|margin|earnings|guidance|backlog|deal|valuation|ipo|market cap|trillion)\b",
        r"\b(hbm|hbm3e|hbm4|gb200|b200|blackwell|rubin|vr200|mi300|mi350|tpu|gpu|datacenter|data center|cluster|power|cooling)\b",
        r"\b(export control|sanction|eu ai act|nist|sovereign|bis|entity list|antitrust|subpoena)\b",
        r"\b(agent|agents|mcp|coding|tool use|autonomous|reasoning|thinking|distillation|benchmark|evals?)\b",
        r"\b(weights?|open-weights?|open weights?|checkpoint|weights release|open-source|open source)\b",
    ]
    hard_signals = sum(1 for pat in hard_signal_patterns if re.search(pat, text_l))

    # Cambios de cúpula, OPVs, compras, investigaciones o sacudidas bursátiles en actores críticos
    strategic_actor_shock = bool(
        STRATEGIC_ACTOR_RE.search(text_l) and GOVERNANCE_OR_MARKET_SHOCK_RE.search(text_l)
    )
    if strategic_actor_shock:
        hard_signals += 2
        raw += 36
        if invest == 0 and geopol == 0:
            invest += 2

    raw += hard_signals * 10

    # Boost major release / milestone
    if re.search(r"\b(now available|available in the api|released?|ships?|launches?|open weights?|weights are live|weights released)\b", text_l) and hard_signals:
        raw += 12
    if re.search(r"\b(frontier|reasoning|benchmark|eval|multimodal|distillation|chain of thought)\b", text_l) and models:
        raw += 8
    # Boost Chinese frontier ecosystem & competition
    if re.search(r"\b(kimi|glm|zhipu|deepseek|qwen|moonshot|minimax|01\.ai|yi|baichuan|huawei|smic)\b", text_l):
        raw += 9
    # Boost new/frontier models
    if re.search(r"\b(mythos|fable|sol|gemini[-\s]?[34]|claude[-\s]?[345]|gpt[-\s]?[56]|o3|o4|grok[-\s]?[34]|deepseek[-\s]?[rv][1234]|glm[-\s]?5|kimi[-\s]?k3)\b", text_l):
        raw += 10

    if promo and hard_signals == 0:
        raw -= min(28, promo * 10)

    src = (source or "").lower()
    if "semiwiki" in src:
        raw += 6
    if "nvidia" in src:
        nvidia_strategic_signal = strategic_actor_shock or (infra + invest + geopol) > 0 or any(
            k in text_l for k in ("datacenter", "hbm", "gpu", "inference", "training", "pricing", "capex", "blackwell", "gb200", "rubin")
        )
        if nvidia_strategic_signal:
            raw += 5
    if "arxiv" in src:
        raw += 4
    if any(k in src for k in (
        "simon willison", "marktechpost", "hugging face", "mistral",
        "venturebeat", "techcrunch", "rundown", "latent space",
        "artificial analysis", "semianalysis", "stratechery", "chinatalk",
        "epoch ai", "import ai", "interconnects", "fabricated knowledge", "arc prize",
        "reuters", "bloomberg",
    )):
        raw += 6
    if "deepmind" in src or "google ai" in src or "openai" in src or "anthropic" in src:
        raw += 5
    if src.startswith("x "):
        raw += 5
        if any(x in src for x in ("openai", "anthropic", "deepmind", "nvidia", "deepseek", "xai", "grok", "sama", "karpathy", "gdb", "zhipu", "moonshot", "qwen", "mistral")):
            raw += 5

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
    elif models == max_hits:
        primary = "models"
    elif infra == max_hits:
        primary = "infra"
    elif invest == max_hits:
        primary = "invest"
    else:
        primary = "geopol"

    return {"score": score, "primary": primary, "tags": tags}
