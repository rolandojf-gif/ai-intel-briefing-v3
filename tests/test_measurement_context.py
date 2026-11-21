import json
import unittest
from pathlib import Path

from src.evidence import measurement_context
from src.render import render_index


def items(day):
    return json.loads(Path(f"docs/data/2026-11-{day}.json").read_text())["items"]


class MeasurementContextTests(unittest.TestCase):
    def test_current_edition_preserves_conditions_and_excludes_financial_numbers(self):
        current = items(21)
        citations = {it["source"]: citation for it in current if (citation := measurement_context(it))}
        self.assertEqual(set(citations), {"The Decoder", "X @gdb", "Together AI"})
        for name, terms in [("The Decoder", ["adaptive red-teaming tests", "54 percent to 0.2 percent"]),
                            ("X @gdb", ["hundreds of head-to-head comparisons", "1 in", "SO-101 Elo"]),
                            ("Together AI", ["first audio in as little as 97ms"])]:
            citation = citations[name]
            original = next(it for it in current if it["source"] == name)
            self.assertIn(citation["quote"], original["summary"])
            self.assertEqual(citation["url"], original["url"])
            for term in terms:
                self.assertIn(term, citation["quote"])

    def test_historical_compiler_comparison_keeps_device_model_and_units(self):
        original = next(it for it in items(18) if it["source"] == "Together AI")
        quote = measurement_context(original)["quote"]
        for term in ("hand-written megakernels", "28%", "B200", "2,118 vs 1,649 tokens/s", "Llama 3.2 1B"):
            self.assertIn(term, quote)

    def test_missing_or_unrelated_evidence_cannot_supply_metric(self):
        base = {"title": "The model was evaluated", "summary": "Latency fell to 97ms.", "url": "https://example.org"}
        for edits in ({"evidence": {}}, {"evidence": {"quote": "Invented result of 97ms"}},
                      {"evidence": {"quote": base["title"]}}, {"url": "javascript:alert(1)"},
                      {"summary": "Market share rose 28% in benchmark tests."},
                      {"summary": "The company ranked 1 in sales."}):
            with self.subTest(edits=edits):
                self.assertIsNone(measurement_context(dict(base, **edits)))

    def test_hero_card_context_and_archive_render_native_details(self):
        current = items(21)
        for opts in ({}, {"nav": "archivo", "archive": {"next": "", "prev": ""}}):
            html = render_index(current, snapshot={"date": "2026-11-21"}, market={}, **opts)
            self.assertEqual(html.count('<details class="metric-context">'), 4)  # hero + su copia para filtros
            self.assertIn("Contexto de la medición", html)
            self.assertIn("Measurement context", html)
            self.assertIn("first audio in as little as 97ms", html)
