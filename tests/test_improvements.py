"""Mejoras de noviembre: ingest mas barato, fechas Atom, dias degradados y front."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import feedparser

import src.fetch as fetch

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>Uno</title><link>https://example.com/1</link><pubDate>Sat, 14 Nov 2026 10:00:00 GMT</pubDate></item>
<item><title>Dos</title><link>https://example.com/2</link><pubDate>Sat, 14 Nov 2026 09:00:00 GMT</pubDate></item>
</channel></rss>"""

ATOM_ONLY_UPDATED = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>r</title>
<entry><id>1</id><title>v3.1</title><link href="https://github.com/x/y/releases/v3.1"/>
<updated>2026-03-01T10:00:00Z</updated></entry></feed>"""


class IngestTests(unittest.TestCase):
    def test_fetch_rss_does_not_scrape_og_image_per_entry(self):
        """Se pedia el og:image de ~250 entradas por run para publicar ~13."""
        with mock.patch.object(fetch, "_fetch_feed_with_retries", return_value=feedparser.parse(RSS)), \
             mock.patch.object(fetch, "fetch_og_image", side_effect=AssertionError("og:image en ingest")):
            items = fetch.fetch_rss("https://example.com/feed")
        self.assertEqual([i["title"] for i in items], ["Uno", "Dos"])
        self.assertEqual([i["image_url"] for i in items], ["", ""])

    def test_enrich_fills_images_only_for_given_items(self):
        items = [{"link": "https://example.com/1", "image_url": ""},
                 {"link": "https://example.com/2", "image_url": "https://cdn.example.com/x.png"}]
        with mock.patch.object(fetch, "fetch_og_image", return_value="https://cdn.example.com/og.png") as og:
            fetch.enrich_items_with_images(items)
        og.assert_called_once_with("https://example.com/1")
        self.assertEqual(items[0]["image_url"], "https://cdn.example.com/og.png")
        self.assertEqual(items[1]["image_url"], "https://cdn.example.com/x.png")

    def test_atom_entry_with_only_updated_gets_a_date(self):
        """Sin fecha un item no caduca nunca en el radar y NEXUS lo descarta siempre."""
        with mock.patch.object(fetch, "_fetch_feed_with_retries", return_value=feedparser.parse(ATOM_ONLY_UPDATED)):
            items = fetch.fetch_rss("https://github.com/x/y/releases.atom")
        self.assertEqual(items[0]["published"], "2026-03-01T10:00:00+00:00")

    def test_retries_back_off_instead_of_hammering(self):
        import requests
        with mock.patch.object(fetch.requests, "get", side_effect=requests.ConnectionError("x")), \
             mock.patch.object(fetch.time, "sleep") as sleep:
            with self.assertRaises(RuntimeError):
                fetch._fetch_feed_with_retries("https://example.com/feed")
        self.assertEqual(sleep.call_count, fetch.RSS_RETRIES)
        waits = [c.args[0] for c in sleep.call_args_list]
        self.assertEqual(waits, sorted(waits))
        self.assertGreater(waits[0], 0)


class EntityTests(unittest.TestCase):
    RAW = 'Amodei admits &quot;there&#039;s a huge uncertainty&quot; in <b>R&amp;D</b> &lt;i&gt;spend&lt;/i&gt;'

    def test_double_encoded_entities_are_decoded_not_mangled(self):
        """El filtro de hashtags convertia "&#039;" en "&039;" y NEXUS lo mostraba tal cual."""
        from src.main import clean_signal_text
        text = clean_signal_text(fetch._clean_html(self.RAW), "The Decoder")
        self.assertEqual(text, 'Amodei admits "there\'s a huge uncertainty" in R&D spend')

    def test_feed_titles_are_decoded(self):
        rss = RSS.replace(b"<title>Uno</title>", b"<title>A &amp;quot;big&amp;quot; deal &amp;amp; more</title>")
        with mock.patch.object(fetch, "_fetch_feed_with_retries", return_value=feedparser.parse(rss)):
            items = fetch.fetch_rss("https://example.com/feed")
        self.assertEqual(items[0]["title"], 'A "big" deal & more')

    def test_hashtags_still_lose_the_hash(self):
        from src.main import clean_signal_text
        self.assertEqual(clean_signal_text("NVIDIA #AI demo", "X @NVIDIAAI"), "NVIDIA AI demo")


class NoveltyHistoryTests(unittest.TestCase):
    def test_history_window_counts_only_real_snapshots(self):
        """image_cache.json y los *.llm_cache.json robaban huecos de la ventana."""
        from src.main import load_recent_history
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            for day in range(1, 6):
                (d / f"2026-11-0{day}.json").write_text(json.dumps(
                    {"items": [{"title": f"noticia del dia {day}", "url": f"https://example.com/{day}"}]}))
            (d / "image_cache.json").write_text("{}")
            (d / "2026-11-05.llm_cache.json").write_text("{}")
            (d / "2026-11-05.x_cache.json").write_text("{}")
            urls, _ = load_recent_history(d, today="2026-11-06", days=5)
        self.assertEqual(urls, {f"https://example.com/{day}" for day in range(1, 6)})


class DegradedDaysTests(unittest.TestCase):
    def test_archive_does_not_call_unfiltered_items_signals(self):
        from src.archive import meta_of
        items = [{"title": "a", "layer": "unrated"}] * 10
        self.assertEqual(meta_of({"date": "2026-11-13", "degraded": True, "items": items})["n_label"], "sin filtrar")
        ok = [{"title": "a", "layer": "signal"}] * 3
        self.assertEqual(meta_of({"date": "2026-11-14", "items": ok})["n_label"], "3 señales")
        self.assertEqual(meta_of({"date": "2026-11-14", "items": ok[:1]})["n_label"], "1 señal")

    def test_weekly_skips_degraded_editions_and_backfills(self):
        from src.weekly import select_analyzed
        loaded = [(f"2026-11-{d:02d}", {"degraded": d in (7, 9, 11, 13)}) for d in range(1, 15)]
        days, snaps, excluded = select_analyzed(loaded, n=7)
        self.assertEqual(len(days), 7)
        self.assertFalse(any(s["degraded"] for s in snaps))
        self.assertEqual(days[-1], "2026-11-14")
        self.assertEqual(days[0], "2026-11-04")
        self.assertEqual(excluded, 4)

    def test_weekly_uses_degraded_only_when_nothing_else_exists(self):
        from src.weekly import select_analyzed
        loaded = [("2026-11-07", {"degraded": True}), ("2026-11-09", {"degraded": True})]
        days, _, excluded = select_analyzed(loaded)
        self.assertEqual(days, ["2026-11-07", "2026-11-09"])
        self.assertEqual(excluded, 0)

    def test_fallback_briefing_is_spelled_properly(self):
        from src.main import generate_fallback_briefing
        b = generate_fallback_briefing([{"title": "x", "score": 1}], {}, [])
        self.assertTrue(b["thesis"].startswith("Análisis no disponible"))


class FrontTests(unittest.TestCase):
    ITEMS = [
        {"title": "Con foto", "title_es": "Con foto", "score": 90, "layer": "signal",
         "url": "https://example.com/a", "image_url": "https://cdn.example.com/a.jpg"},
        {"title": "Sin foto", "title_es": "Sin foto", "score": 80, "layer": "signal",
         "url": "https://example.com/b", "image_url": ""},
    ]

    def _html(self, **kw):
        from src.render import render_index
        return render_index([dict(i) for i in self.ITEMS], briefing={"thesis": "t"},
                            snapshot={"date": "2026-11-14"}, market={}, **kw)

    def test_remote_images_carry_a_generated_fallback(self):
        import re
        html = self._html()
        hero = re.search(r'<img class="hero-img"[^>]*>', html).group(0)
        card = re.search(r'<img class="card-img"[^>]*>', html).group(0)
        self.assertIn('src="https://cdn.example.com/a.jpg"', hero)
        self.assertIn('data-fb="data:image/svg+xml;base64,', hero)
        # El que ya usa la portada generada no necesita respaldo.
        self.assertIn('src="data:image/svg+xml;base64,', card)
        self.assertNotIn("data-fb", card)

    def test_error_listener_is_registered_before_the_first_image(self):
        html = self._html()
        self.assertLess(html.index("addEventListener('error'"), html.index("<body"))

    def test_stale_edition_chip_only_on_the_live_daily_page(self):
        self.assertIn('id="stale" data-date="2026-11-14"', self._html())
        archived = self._html(nav="archivo", root="../", archive={"prev": None, "next": None})
        self.assertNotIn('id="stale"', archived)

    def test_pages_ship_a_favicon(self):
        from src.archive import ARCHIVO_TEMPLATE
        arch = ARCHIVO_TEMPLATE.render(months=[], total_days=0, total_signals=0, latest="2026-11-14")
        for html in (self._html(), arch):
            self.assertIn('rel="icon"', html)
            self.assertIn('name="theme-color"', html)


if __name__ == "__main__":
    unittest.main()


class TopicFilterTests(unittest.TestCase):
    def test_filter_never_targets_the_theme_attribute_on_html(self):
        """Con Claro/Oscuro elegido, <html data-theme> casaba con el filtro y la pagina quedaba en blanco."""
        from src.render import render_index
        items = [{"title_es": "A", "layer": "signal", "score": 90, "strategic_theme": "china_stack", "url": "https://e.com/a"},
                 {"title_es": "B", "layer": "signal", "score": 80, "strategic_theme": "agents_automation", "url": "https://e.com/b"}]
        html = render_index(items, briefing={"thesis": "t"}, snapshot={"date": "2026-11-15"}, market={})
        self.assertIn('data-topic="china_stack"', html)
        self.assertNotIn("querySelectorAll('[data-theme]')", html)
        self.assertIn("querySelectorAll('[data-topic]')", html)
