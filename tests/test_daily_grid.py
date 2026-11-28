import html as html_lib
import json
import re
import unittest
from pathlib import Path

from src.render import render_index


def cards(html):
    return re.findall(r'<article class="card(?: from-archive)?"[^>]*>.*?</article>', html, re.S)


def story(i, layer="signal"):
    return {"title": f"Report {i}", "title_es": f"Noticia {i}", "source": "Medio",
            "url": f"https://example.org/{i}", "score": 90, "layer": layer,
            "evidence_kind": "reported", "evidence": {"quote": f"Report {i}"}}


class DailyGridTests(unittest.TestCase):
    def test_november_28_has_nine_distinct_cards_and_a_separate_lead(self):
        day = json.loads(Path("docs/data/2026-11-28.json").read_text())
        html = render_index(day["items"], day["briefing"], day, market={})
        grid = cards(html)
        self.assertEqual(len(grid), 9)
        self.assertEqual(sum('>Contexto</span>' in card for card in grid), 2)
        self.assertNotIn('class="card from-archive"', html)
        lead = re.search(r'<article class="lead .*?</article>', html, re.S).group()
        for item in day["items"]:
            href = f'href="{item["url"]}"'
            self.assertEqual(sum(href in html_lib.unescape(card) for card in [lead, *grid]), 1)

    def test_complete_rows_use_current_news_first(self):
        for count in (6, 9, 12, 15):
            with self.subTest(count=count):
                items = [story(i) for i in range(count)] + [story(count, "context")]
                html = render_index(items, snapshot={"date": "2026-11-28"}, market={})
                self.assertEqual(len(cards(html)), count)
                self.assertNotIn('class="card from-archive"', html)

    def test_sparse_day_adds_dated_readings_without_counting_them_as_new(self):
        current = [story(0), story(1), story(2, "context")]
        prior = [dict(story(99), url=current[0]["url"]+"?utm_source=feed"),
                 dict(story(98), title_es=current[1]["title_es"]), dict(story(97), evidence={}),
                 dict(story(96), related=[{"url":current[2]["url"]}])]
        prior += [story(i) for i in range(3, 12)]
        history = [{"date": "2026-11-27", "items": prior},
                   {"date": "2026-11-28", "items": [story(95)]}]
        html = render_index(current, snapshot={"date": "2026-11-28"}, history=history, market={})
        grid = cards(html)
        self.assertEqual(len(grid), 6)
        archived = [card for card in grid if 'class="card from-archive"' in card]
        self.assertEqual(len(archived), 4)
        for i, card in enumerate(archived, 3):
            self.assertIn(f'href="https://example.org/{i}"', card)
            self.assertIn("2026-11-27", card)
            self.assertNotIn('class="badge-new"', card)
            self.assertNotIn('data-topic=', card)
        self.assertIn('class="fig-count">3</strong>', html)
