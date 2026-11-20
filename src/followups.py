"""Seguimientos editoriales. El modelo propone el vínculo; ambas citas se verifican antes de publicarlo."""
import re
from datetime import date, timedelta

from src.evidence import source_evidence
from src.memory import resolve_watchlist


def excerpt(item):
    texts = [(item.get(k) or "").strip() for k in ("title", "summary")]
    return " | ".join(dict.fromkeys(t for t in texts if t))[:320]


def previous_state(history):
    return next((s["memory"]["followups"] for s in reversed(history)
                 if isinstance((s.get("memory") or {}).get("followups"), dict)), {})


def with_open_stories(recent, history, candidates):
    """Reserva parte de los 20 antecedentes del ranking para hitos abiertos más antiguos."""
    older = [s["excerpt"] for s in previous_state(history).get("open", [])
             if isinstance(s, dict) and s.get("excerpt") and s["excerpt"] not in recent]
    if not older:
        return recent
    # Solo prioriza el contexto del prompt: el solape jamás genera una actualización.
    terms = set(re.findall(r"\w{4,}", " ".join(excerpt(it) for it in candidates).casefold()))
    older = sorted(dict.fromkeys(older), key=lambda x: len(terms.intersection(re.findall(r"\w{4,}", x.casefold()))),
                   reverse=True)[:6]
    return (recent[:20-len(older)] + older)[:20]


def _card(item, day, quote):
    evidence = source_evidence(item, quote)
    if not evidence:
        return None
    # Las ediciones antiguas carecen de clasificación. Mostrar el texto original citado.
    qualified = item.get("evidence_kind") in {"reported", "confirmed", "speculation", "inference"}
    return {**evidence, "date": day, "excerpt": excerpt(item),
            "es": (item.get("title_es") if qualified else "") or quote,
            "en": (item.get("title_en") if qualified else "") or quote,
            "watch": (item.get("watch_next") if qualified else "") or "",
            "watch_en": (item.get("watch_next_en") if qualified else "") or ""}


def _deadline(card):
    # Solo plazos escritos en formato ISO en la cita y en el propio hito.
    for value in re.findall(r"\b\d{4}-\d{2}-\d{2}\b", card["watch"] + " " + card["watch_en"]):
        if value in card["quote"]:
            try:
                return date.fromisoformat(value).isoformat()
            except ValueError:
                pass
    return ""


def followups(today, history, items, results, recent):
    state = previous_state(history)
    cutoff = (date.fromisoformat(today) - timedelta(days=30)).isoformat()
    active = {s["url"]: dict(s) for s in state.get("open", [])
              if max(s["date"], s.get("due", "")) >= cutoff}
    closed = {url: day for url, day in state.get("closed", {}).items() if day >= cutoff}
    updates = {}
    historical = {excerpt(it): (day["date"], it) for day in history for it in day.get("items", [])
                  if isinstance(it, dict) and it.get("title")}
    live = {it["_rid"]: it for it in items if it.get("evidence") and "_rid" in it}
    # Una reedición puede cambiar la entradilla manteniendo la misma novedad.
    previous_changes = {(event["before"]["url"], event["after"]["quote"].casefold())
                        for event in state.get("updates", []) if event.get("after")}
    linked = set()
    for rid, it in live.items():
        decision = results.get(rid) or results.get(str(rid)) or {}
        if decision.get("repeat_of") or decision.get("same_story_as"):
            continue
        link = decision.get("follow_up") or {}
        number, quote = link.get("number", 0), decision.get("prior_quote", "")
        if not isinstance(number, int) or number < 1 or not quote.strip() or len(quote.strip()) < 12:
            continue
        origin = None
        if link.get("origin") == "batch" and number != rid and number in live:
            origin = _card(live[number], today, quote)
        elif link.get("origin") == "history" and number <= len(recent):
            text = recent[number-1]
            if quote not in text:
                continue
            if text in historical:
                day, prior = historical[text]
                origin = _card(prior, day, quote)
            else:
                origin = next((s for s in active.values() if s["excerpt"] == text and quote in s["quote"]), None)
        if not origin or it.get("evidence_kind") not in {"confirmed", "reported"}:
            continue
        current = _card(it, today, it["evidence"]["quote"])
        if (not current or current["quote"].casefold() in origin["excerpt"].casefold()
                or current["quote"].casefold() == origin["quote"].casefold()
                or current["excerpt"] == origin["excerpt"]):
            continue
        if (origin["url"], current["quote"].casefold()) in previous_changes:
            continue
        if origin["url"] in closed:
            origin = dict(origin, watch="", watch_en="")
        status = "development"
        if link.get("correction") and re.search(r"\b(correction|corrected|retraction|retracted|fe de erratas|rectifica\w*)\b",
                                                current["quote"], re.I):
            status = "correction"
        updates.setdefault(origin["url"], {"date": today, "before": origin, "after": current, "status": status})
        if origin["watch"]:
            active.setdefault(origin["url"], dict(origin, due=_deadline(origin)))
        linked.add(rid)

    # Los hitos anteriores sobreviven a días sin novedades. La confirmación utiliza
    # el mismo criterio afirmativo que la vigilancia diaria, sin delegarla al modelo.
    for url, card in list(active.items()):
        brief = {"watch": [card["watch"]], "watch_en": [card["watch_en"]]}
        hit = resolve_watchlist([{"briefing": brief}], items)[0]
        if hit["status"] == "hit":
            item = next(it for it in items if (it.get("url") or it.get("link")) == hit["evidence_url"]
                        and (it.get("evidence") or {}).get("quote") == hit["evidence"])
            after = _card(item, today, hit["evidence"])
            if after and after["quote"] != card["quote"]:
                updates[url] = {"date": today, "before": card, "after": after, "status": "confirmed"}
                del active[url]
                closed[url] = today
        elif card.get("due") and today > card["due"] and not card.get("expired"):
            card["expired"] = True
            updates[url] = {"date": today, "before": card, "after": None, "status": "expired"}

    for rid, item in live.items():
        if rid in linked or not item.get("watch_next"):
            continue
        card = _card(item, today, item["evidence"]["quote"])
        if card and card["url"] not in updates and card["url"] not in closed:
            active.setdefault(card["url"], dict(card, due=_deadline(card)))

    for event in state.get("updates", []):
        updates.setdefault(event["before"]["url"], event)
    return {"open": list(active.values()), "closed": closed, "updates": list(updates.values())[:3]}
