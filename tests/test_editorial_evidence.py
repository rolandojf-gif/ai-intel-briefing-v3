"""Regresiones editoriales con los textos de fuente publicados el 18–20 de noviembre."""
import json
import unittest
from pathlib import Path

from src import main
from src.memory import resolve_watchlist


ARCHIVE = Path(__file__).resolve().parents[1] / "docs/data"


def edition(day):
    return json.loads((ARCHIVE / f"2026-11-{day}.json").read_text())


def outlet(day, name):
    return next(it for it in edition(day)["items"] if it["source"] == name)


def judge(item, **overrides):
    result = {"verdict": "signal", "relevance": 90, "headline_es": item["title_es"],
              "headline_en": item.get("title_en", ""), "so_what": item["so_what"],
              "power_shift": item["power_shift"], "evidence_kind": "confirmed",
              "evidence_quote": item["title"], **overrides}
    return main.apply_llm_results([dict(item, _rid=1)], {1: result})[0]


class HistoricalRegressionTests(unittest.TestCase):
    def test_reprints_removed_even_if_llm_rewords_headline(self):
        for day, source in [(19, "Together AI"), (20, "X @OpenAI")]:
            with self.subTest(day=day):
                self.assertEqual(main.exclude_reprints([outlet(day, source)], [edition(day - 1)]), [])

    def test_neon_bare_launch_repeats_but_new_results_survive(self):
        neon = outlet(20, "DeepMind Blog")
        update = dict(neon, summary="Independent users measured a 12% regression on production workloads.")
        self.assertEqual(main.exclude_reprints([neon, update], [edition(19)]), [update])

    def test_live_article_update_and_market_reaction_survive(self):
        old = outlet(19, "X @OpenAI")
        new = dict(old, summary=old["summary"] + " AMD now reports an independent validation.")
        apple, market = outlet(20, "TechCrunch AI"), outlet(20, "Bloomberg Tech")
        self.assertEqual(main.exclude_reprints([new, market], [{"items": [old, apple]}]), [new, market])
        self.assertEqual(len(main.dedup_items([apple, market])), 2)

    def test_apple_hypothesis_does_not_establish_a_winner(self):
        apple = outlet(20, "TechCrunch AI")
        result = judge(apple, headline_es="Apple lanza su agente", headline_en="Apple launches its agent",
                       source_title_es="Apple podría estar desarrollando un agente para Mac")
        self.assertIn("podría estar desarrollando", result["title_es"])
        self.assertEqual(result["evidence_kind"], "speculation")
        self.assertIn("Hipótesis", result["title_es"])
        self.assertIn("Hypothesis", result["title_en"])
        self.assertEqual(result["power_shift"], "")
        self.assertEqual(result["power_shift_en"], "")
        self.assertEqual(result["evidence"]["quote"], apple["title"])

    def test_invented_quote_or_bad_url_cannot_support_a_conclusion(self):
        original = outlet(20, "TechCrunch AI")
        for item, quote in [(original, "Apple released audited figures"),
                            (dict(original, url="javascript:alert(1)", link=""), original["title"])]:
            with self.subTest(quote=quote):
                result = judge(item, evidence_quote=quote)
                self.assertFalse(result.get("evidence"))
                self.assertIn("verific", result["so_what"])
                self.assertFalse(result["power_shift"])

    def test_briefing_requires_published_evidence_in_both_languages(self):
        it = judge(outlet(20, "Bloomberg Tech"), evidence_kind="reported")
        brief = {"thesis": "Competencia por agentes", "thesis_en": "Agent competition",
                 "signals": ["Dato inventado"], "signals_en": ["Invented figure"],
                 "references": [{"field": "thesis", "index": 0, "ids": [1]},
                                {"field": "signals", "index": 0, "ids": [2]}]}
        b = main.merge_briefings([brief], [it])
        self.assertEqual(b["signals"], [])
        self.assertEqual(b["signals_en"], [])
        self.assertIn("Inferencia", b["thesis"])
        self.assertEqual(b["evidence"]["thesis"][0]["url"], it["url"])
        self.assertEqual(b["evidence"]["thesis"][0]["quote"], it["title"])

    def test_watch_requires_full_affirmative_source_statement_and_url(self):
        watch = "Apple and OpenAI publish audited adoption figures"
        prev = [{"briefing": {"watch": ["Apple y OpenAI publican cifras auditadas de adopción"],
                              "watch_en": [watch]}}]
        for title, url, expected in [
            ("Apple and OpenAI decline to publish audited adoption figures", "https://apple.com/report", "open"),
            (watch + "?", "https://apple.com/report", "open"),
            (watch, "", "open"), (watch, "https://apple.com/report", "hit"),
        ]:
            with self.subTest(title=title, url=url):
                item = {"title": title, "title_en": watch, "url": url, "evidence_kind": "confirmed",
                        "evidence": {"url": url, "quote": title}, "entities": ["Apple", "OpenAI"]}
                resolved = resolve_watchlist(prev, [item])[0]
                self.assertEqual(resolved["status"], expected)
                if expected == "hit":
                    self.assertEqual((resolved["evidence_url"], resolved["evidence"]), (url, title))

    def test_refuted_release_does_not_hide_later_announcement(self):
        neon = outlet(20, "DeepMind Blog")
        for title in ("Google never released Gemini 4 Neon", "Report debunked: Google launches Gemini 4 Neon"):
            with self.subTest(title=title):
                self.assertEqual(main.exclude_reprints([neon], [{"items": [{"title": title}]}]), [neon])

    def test_ipo_pricing_is_distinct_from_forward_looking_disclaimer(self):
        ipo = outlet(19, "X @AnthropicAI")
        result = judge(ipo, evidence_quote="We’ve priced our IPO at $83 per share")
        self.assertEqual(result["evidence_kind"], "confirmed")

    def test_briefing_cannot_inherit_confirmation_for_an_inferred_outcome(self):
        ipo = judge(outlet(19, "X @AnthropicAI"), evidence_quote="We’ve priced our IPO at $83 per share")
        brief = {"signals": ["Esto implica una ventaja de financiación", "El margen sube un 90%"],
                 "signals_en": ["This implies a funding advantage", "Margins rise by 90%"],
                 "references": [{"field": "signals", "index": i, "ids": [1]} for i in range(2)]}
        out = main.merge_briefings([brief], [ipo])
        self.assertEqual(len(out["signals"]), 1)
        self.assertTrue(out["signals"][0].startswith("Inferencia"))

    def test_watch_accepts_a_complete_cited_sentence_in_a_longer_excerpt(self):
        watch = "OpenAI cuts API prices"
        item = {"title": "November pricing", "summary": watch + ". New prices apply today.",
                "url": "https://openai.com/pricing", "evidence_kind": "confirmed",
                "evidence": {"quote": watch}}
        resolved = resolve_watchlist([{"briefing": {"watch": [watch]}}], [item])
        self.assertEqual(resolved[0]["status"], "hit")
        self.assertEqual(resolved[0]["evidence_url"], item["url"])

    def test_future_announcement_neither_confirms_action_nor_closes_watch(self):
        title = "OpenAI to publish audited adoption figures"
        item = dict(outlet(20, "X @OpenAI"), title=title, summary="")
        result = judge(item, headline_en="OpenAI publishes audited adoption figures")
        self.assertNotEqual(result["evidence_kind"], "confirmed")
        self.assertIn(title, result["title_en"])
        prev = [{"briefing": {"watch": [title]}}]
        self.assertEqual(resolve_watchlist(prev, [result])[0]["status"], "open")

    def test_empty_batch_after_reprints_costs_no_model_request(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        with TemporaryDirectory() as directory, patch.object(main, "should_use_gemini_today", return_value=True), \
                patch.object(main, "rank_batch", return_value={}) as rank:
            root = Path(directory)
            self.assertEqual(main.generate_llm_data([], root / "cache", root / "done"), ({}, []))
            rank.assert_not_called()
            self.assertEqual(list(root.iterdir()), [])

    def test_semantic_repeat_requires_citations_to_both_editions(self):
        from unittest.mock import patch
        from src import llm_rank

        current = outlet(20, "DeepMind Blog")
        previous = outlet(19, "VentureBeat AI")["title"]
        item = {**current, "id": 1}
        result = {"id": 1, "verdict": "signal", "relevance": 80, "theme": "frontier_capability",
                  "source_title_es": current["title_es"], "headline_es": current["title_es"], "so_what": "", "evidence_kind": "confirmed",
                  "evidence_quote": current["title"], "repeat_of": 1, "prior_quote": previous}
        with patch.object(llm_rank, "client") as client:
            for change, expected in [({}, "noise"), ({"repeat_of": 2}, "signal"),
                                     ({"prior_quote": "Invented quote"}, "signal"),
                                     ({"evidence_quote": "Wrong new quote"}, "signal")]:
                with self.subTest(change=change):
                    client.models.generate_content.return_value.text = json.dumps(
                        {"briefing": {}, "results": [{**result, **change}]})
                    out = llm_rank.rank_batch([item], recent_headlines=[previous])
                    self.assertEqual(out["map"][1]["verdict"], expected)

    def test_failed_global_thesis_can_use_a_published_signal_with_its_own_evidence(self):
        it = {**outlet(21, "The Decoder"), "_rid": 1}
        rejected = {"thesis": "Sin respaldo", "thesis_en": "Unsupported",
                    "references": [{"field": "thesis", "index": 0, "ids": [99]}]}
        b = main.merge_briefings([rejected], [it])
        self.assertIn(it["so_what"], b["thesis"])
        self.assertIn(it["so_what_en"], b["thesis_en"])
        self.assertEqual(b["evidence"]["thesis"], [it["evidence"]])
        b = main.merge_briefings([rejected], [dict(it, evidence={})])
        self.assertNotIn("thesis", b["evidence"])
