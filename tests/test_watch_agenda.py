import json
import unittest
from html import unescape
from pathlib import Path

from src.render import render_index


class WatchAgendaTests(unittest.TestCase):
    def test_real_edition_moves_selected_watch_points_once_in_both_languages(self):
        day = json.loads(Path("docs/data/2026-11-21.json").read_text())
        html = unescape(render_index(day["items"], briefing=day["briefing"], snapshot=day, market={}))
        agenda = html.split('class="watch-agenda"', 1)[1].split("</section>", 1)[0]
        self.assertEqual(agenda.count('class="watch-row"'), 3)
        for i, source in enumerate(("The Verge AI", "TechCrunch AI", "Ars Technica AI"), 1):
            item = next(it for it in day["items"] if it["source"] == source)
            self.assertIn(f'href="#watch-point-{i}"', html)
            self.assertIn(f'href="{item["url"]}"', agenda)
            for key in ("watch_next", "watch_next_en"):
                self.assertEqual(html.count(item[key]), 1)
                self.assertIn(item[key], agenda)
        self.assertNotIn('class="watch-results"', html)
        self.assertNotIn('class="companies"', html)

    def test_only_documented_results_and_no_empty_sections(self):
        empty = render_index([], market={})
        for key in ("agenda-title", "results-title"):
            self.assertNotIn(f'id="{key}"', empty)
        hit = {"status": "hit", "text": "Se publicó la auditoría.", "evidence": "Audit published.",
               "evidence_url": "https://example.org/audit"}
        invalid = [
            dict(hit, text="En espera", status="open"),
            dict(hit, text="Sin enlace", evidence_url="javascript:void(0)"),
            dict(hit, text="Sin cita", evidence=""),
        ]
        html = render_index([], briefing={"watch": [hit["text"], "Publicación de costes."],
                                          "watch_en": ["Audit published.", "Publication of costs."]},
                            snapshot={"memory": {"watch_resolved": invalid + [hit]}}, market={})
        self.assertEqual(html.count(hit["text"]), 1)
        for w in invalid:
            self.assertNotIn(w["text"], html)
        for text in ("Publicación de costes.", "Publication of costs.", hit["evidence"], hit["evidence_url"]):
            self.assertIn(text, html)

    def test_multiple_milestones_from_one_source_stay_distinct(self):
        url = "https://example.org/roadmap"
        refs = [{"source": "AI Lab", "url": url}]
        card = {"title": "Roadmap", "watch_next": "Prueba independiente.", "url": url, "layer": "signal"}
        html = render_index([card], briefing={"watch": ["Publicación de los pesos.", "Apertura de la API."],
                                          "evidence": {"watch.0": refs, "watch.1": refs}}, market={})
        self.assertIn("Publicación de los pesos.", html)
        self.assertIn("Apertura de la API.", html)
