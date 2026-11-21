"""Evidencia que puede comprobarse en el título o extracto recibido del feed."""
import re
from urllib.parse import urlsplit


UNCERTAIN = re.compile(
    r"\b(may|might|could|would|rumou?rs?|appears? to|allegedly|unconfirmed|"
    r"podría\w*|quizá\w*|habría\w*|se especula|al parecer)\b|\?", re.I,
)
PROSPECTIVE = re.compile(
    r"^(?:[A-Z][\w.-]* ){1,5}to (?:publish|launch|release|approve|cut|ship|file|report)\b"
    r"|(?i:\b(?:will|plans? to|expected to|set to|planea|prevé|publicará[n]?|lanzará[n]?)\b)"
)
PENDING = re.compile(
    r"\b(no|not|never|false|debunked|denies|deny|denied|declines?|refuses?|if|will|plans?|expects?|"
    r"desmiente|desmentido|nunca|niega|prevé|planea|espera|si)\b|n['’]t\b", re.I,
)


def sentences(text):
    return re.split(r"(?<=[.!?])\s+", text)


def percentages_supported(text, quotes):
    """Una cifra porcentual publicada debe aparecer en al menos una de las citas."""
    def values(s):
        return {v.replace(",", ".") for v in re.findall(
            r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(?:%|percent\b|per cent\b|por ciento\b)", s, re.I
        )}
    return values(text) <= values(" ".join(quotes))


PRIMARY_HOSTS = {
    "openai.com", "anthropic.com", "deepmind.google", "blog.google", "mistral.ai",
    "ai.meta.com", "x.ai", "together.ai", "deepseek.com", "api-docs.deepseek.com",
}


def source_url(item):
    url = item.get("url") or item.get("link") or ""
    try:
        parts = urlsplit(url)
        return url if parts.scheme in {"https", "http"} and parts.hostname else ""
    except ValueError:
        return ""


def source_evidence(item, quote):
    url = source_url(item)
    if not url or not isinstance(quote, str) or len(quote.strip()) < 12:
        return {}
    quote = quote.strip()
    if not any(quote in (item.get(field) or "") for field in ("title", "summary")):
        return {}
    return {"source": item.get("source", ""), "url": url, "quote": quote}


def primary_source(item):
    url = source_url(item)
    parts = urlsplit(url)
    host = (parts.hostname or "").removeprefix("www.")
    if host in PRIMARY_HOSTS:
        return True
    account = (item.get("source") or "").removeprefix("X @").lower()
    return (host in {"x.com", "twitter.com"} and account in {"openai", "anthropicai", "googledeepmind"}
            and parts.path.lower().startswith(f"/{account}/status/"))


LABELS = {
    "confirmed": ("Confirmado", "Confirmed"),
    "reported": ("Según la fuente", "Reported"),
    "inference": ("Inferencia", "Inference"),
    "speculation": ("Hipótesis", "Hypothesis"),
}


UNVERIFIED = ("La fuente disponible no permite verificar la conclusión.",
              "The available source does not verify the conclusion.")


def qualify_item(item, result):
    evidence = source_evidence(item, result.get("evidence_quote"))
    kind = result.get("evidence_kind")
    title = item.get("title") or ""
    if not evidence or kind not in LABELS:
        item.update(evidence={}, evidence_kind="unverified",
                    title_es=f"Sin verificar · {title}", title_en=f"Unverified · {title}",
                    so_what=UNVERIFIED[0], so_what_en=UNVERIFIED[1],
                    power_shift="", power_shift_en="", watch_next="", watch_next_en="")
    else:
        summary = item.get("summary") or ""
        # Una cautela en otra frase (p. ej., el aviso legal de una OPV)
        # no invalida el acto documentado. Conserva el contexto que rodea la cita.
        context = [sentences(title)[0], sentences(summary)[0], evidence["quote"]]
        context.extend(s for s in sentences(summary) + sentences(title) if evidence["quote"] in s)
        uncertain = any(UNCERTAIN.search(text) for text in context)
        # Un acto ya documentado puede compartir frase con otro futuro:
        # la OPV tiene precio hoy, aunque la cotización empiece mañana.
        prospective = PROSPECTIVE.search(evidence["quote"])
        if uncertain or prospective:
            kind = "speculation"
        elif kind == "confirmed" and not primary_source(item):
            kind = "reported"
        item.update(evidence=evidence, evidence_kind=kind)
        for idx, lang in enumerate(("es", "en")):
            key = f"title_{lang}"
            headline = item.get(key) or title
            if (kind == "speculation" and not (UNCERTAIN.search(headline) or PROSPECTIVE.search(headline))
                    and (UNCERTAIN.search(title) or PROSPECTIVE.search(title))):
                # Una traducción categórica puede incluso cambiar el verbo (planificar → lanzar).
                headline = title
            item[key] = f"{LABELS[kind][idx]} · {headline}"
            suffix = "" if lang == "es" else "_en"
            for field in ("so_what", "power_shift"):
                key = field + suffix
                if field == "power_shift" and kind in {"inference", "speculation"}:
                    item[key] = ""
                elif item.get(key) and not percentages_supported(item[key], [evidence["quote"]]):
                    item[key] = UNVERIFIED[idx] if field == "so_what" else ""
                elif item.get(key):
                    item[key] = f"{LABELS['inference'][idx]} · {item[key]}"
    item["why"] = item["so_what"]


# Prefer explicit measurement units; a model version or a percentage alone is ambiguous.
_MEASUREMENT = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:tokens?/s(?:ec(?:ond)?)?|tokens? per second|ms|milliseconds?|milisegundos)\b", re.I,
)
_RANK = re.compile(r"(?:\brank(?:ed)?\s+#?|\bpuesto\s+|\bclimbed to\s+#?)\d+\b", re.I)
_PERCENT = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:%|percent\b|por ciento\b)", re.I)
_TEST_CONTEXT = re.compile(
    r"\b(?:accuracy|precision|recall|Elo|success rate|error rate|throughput|latency|benchmarks?|"
    r"tests?|tasa de éxito|tasa de error|latencia|pruebas?|precisión)\b", re.I,
)
_FINANCIAL = re.compile(
    r"\b(?:share price|stock price|shareholder|revenue|earnings|market share|valuation|"
    r"cotización|precio de la acción|cuota de mercado|ingresos|valoración)\b", re.I,
)


def measurement_context(item):
    """Una frase original completa que documente una medida. No calcular ni traducir cifras."""
    evidence = item.get("evidence") or {}
    quote = evidence.get("quote", "")
    if "evidence" in item and (not quote or not source_evidence(item, quote)):
        return None
    for field in ("summary", "title"):
        for sentence in sentences(item.get(field) or ""):
            # En el contrato actual la cifra debe pertenecer a la cita validada.
            # Recuperar la frase completa conserva «hasta», el comparador y las condiciones.
            cited = sentence
            if quote and sentence not in quote:
                if quote not in sentence:
                    continue
                cited = quote
            if _FINANCIAL.search(sentence):
                continue
            if _MEASUREMENT.search(cited) or ((_PERCENT.search(cited) or _RANK.search(cited))
                                               and _TEST_CONTEXT.search(sentence)):
                return source_evidence(item, sentence) or None
    return None
