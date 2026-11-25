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
        {"title": "Con anuncio", "title_es": "Con anuncio", "score": 75, "layer": "signal",
         "url": "https://example.com/c", "image_url": "https://cdn.example.com/english-banner.jpg"},
    ]

    def _html(self, **kw):
        from src.render import render_index
        return render_index([dict(i) for i in self.ITEMS], briefing={"thesis": "t"},
                            snapshot={"date": "2026-11-14"}, market={}, **kw)

    def test_remote_images_only_appear_in_english_with_a_generated_fallback(self):
        import re
        html = self._html()
        covers_es = re.findall(r'<img class="(?:hero-img|card-img) l-es"[^>]*>', html)
        self.assertEqual(len(covers_es), 4)
        for cover in covers_es:
            self.assertIn('src="data:image/svg+xml;base64,', cover)
            self.assertNotIn("data-fb", cover)
        for url in ("https://cdn.example.com/a.jpg", "https://cdn.example.com/english-banner.jpg"):
            images = re.findall(r'<img[^>]*src="' + re.escape(url) + r'"[^>]*>', html)
            self.assertTrue(images)
            for image in images:
                self.assertIn(' l-en"', image)
                self.assertIn('data-fb="data:image/svg+xml;base64,', image)
        self.assertRegex(html, r'<img class="card-img l-en" src="data:image/svg\+xml;base64,[^"]*" alt="" loading="lazy"/>')

    def test_generated_cover_is_translated(self):
        import base64
        from src.render import item_fallback_image
        item = {"title": "t", "strategic_theme": "frontier_capability", "source": "X @grok"}
        dec = lambda uri: base64.b64decode(uri.split(",", 1)[1]).decode()
        self.assertIn("CAPACIDAD DE VANGUARDIA", dec(item_fallback_image(item)))
        self.assertIn("FRONTIER CAPABILITY", dec(item_fallback_image(item, "en")))

    def test_site_defaults_to_english_and_light(self):
        html = self._html()
        self.assertIn('<html lang="en" data-lang="en" data-theme="light">', html)
        self.assertNotIn('archivo.html">', html.split('class="strip"')[1].split("</div>")[0])

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


class MemoryEnglishTests(unittest.TestCase):
    def test_watchlist_and_threads_carry_english(self):
        from src.memory import detect_threads, resolve_watchlist
        hist = [{"date": "2026-11-13", "items": [{"layer": "signal", "strategic_theme": "china_stack"}]},
                {"date": "2026-11-14", "briefing": {"watch": ["DeepSeek R1 baja precios"], "watch_en": ["DeepSeek R1 cuts prices"]},
                 "items": [{"layer": "signal", "strategic_theme": "china_stack"}]}]
        today = [{"title": "DeepSeek R1 cuts prices", "url": "https://deepseek.com/pricing",
                  "evidence_kind": "confirmed", "evidence": {"quote": "DeepSeek R1 cuts prices"},
                  "title_es": "DeepSeek R1 baja precios", "title_en": "DeepSeek R1 cuts prices", "layer": "signal",
                  "strategic_theme": "china_stack", "entities": ["DeepSeek"]}]
        w = resolve_watchlist(hist, today)[0]
        self.assertEqual((w["status"], w["text_en"], w["evidence_en"]), ("hit", "DeepSeek R1 cuts prices", "DeepSeek R1 cuts prices"))
        t = detect_threads(hist, today)[0]
        self.assertEqual((t["label_en"], t["lead_en"]), ("China stack", "DeepSeek R1 cuts prices"))


class ArchiveHidesDegradedTests(unittest.TestCase):
    def test_degraded_days_are_not_listed_nor_kept_as_pages(self):
        import re
        from src.archive import write_archive
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); (out / "data").mkdir(); (out / "d").mkdir()
            ok = {"date": "2026-11-05", "briefing": {"thesis": "buena"}, "items": [{"title": "a", "layer": "signal", "url": "https://e.com/a"}]}
            bad = {"date": "2026-11-07", "degraded": True, "briefing": {"thesis": "mala"}, "items": [{"title": "b", "url": "https://e.com/b"}]}
            for s in (ok, bad):
                (out / "data" / f"{s['date']}.json").write_text(json.dumps(s))
            (out / "d" / "2026-11-07.html").write_text("vieja")
            n = write_archive(out)
            html = (out / "archivo.html").read_text()
            self.assertEqual(n, 1)
            self.assertIn("d/2026-11-05.html", html)
            self.assertNotIn("2026-11-07", html)
            self.assertFalse((out / "d" / "2026-11-07.html").exists())
            self.assertNotIn("2026-11-07", (out / "sitemap.xml").read_text())


class NewspaperLayoutTests(unittest.TestCase):
    def _html(self, n=9):
        from src.render import render_index
        items = [{"title_es": f"Noticia {i}", "layer": "signal", "score": 99 - i, "url": f"https://e.com/{i}",
                  "strategic_theme": "agents_automation" if i % 2 else "china_stack"} for i in range(n)]
        return render_index(items, briefing={"thesis": "Tesis", "signals": ["clave uno", "clave dos"]},
                            snapshot={"date": "2026-11-15", "top_entities": [{"entity": "NVIDIA", "count": 3}]},
                            market={"macro": [{"label": "VIX", "available": True, "price_str": "19.30", "change_str": "+3%", "positive": True, "sparkline_svg": ""}]})

    def test_front_page_has_editorial_lead_and_beyond_grid(self):
        html = self._html()
        self.assertLess(html.index('class="opening"'), html.index('class="ticker"'))
        self.assertIn("clave uno", html)
        self.assertIn(">NVIDIA<", html)
        self.assertEqual(html.count('<article class="lead '), 1)
        self.assertNotIn('class="subleads"', html)
        self.assertEqual(html.count('class="rail"'), 1)
        self.assertIn('class="below"', html)
        self.assertNotIn('class="brief"', html)

    def test_every_signal_has_a_filterable_card_and_front_is_hidden_by_default(self):
        import re
        html = self._html()
        cards = re.findall(r'<article class="card( dup)?" data-topic="(\w+)"', html)
        self.assertEqual(len(cards), 9)
        self.assertEqual(sum(1 for d, _ in cards if d), 1)
        self.assertIn("deck.classList.toggle('filtered'", html)

    def test_no_rest_section_when_everything_fits_on_the_front(self):
        self.assertIn('class="below no-rest"', self._html(n=1))
        self.assertIn('class="below"', self._html(n=3))
        self.assertIn('class="below"', self._html(n=9))


class FirstAppearanceTests(unittest.TestCase):
    def test_new_entrant_means_never_seen_in_the_whole_archive(self):
        """Alibaba o Huawei salian como 'primera aparicion' por mirar solo 10 dias."""
        from src.memory import entity_deltas, known_before
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "2026-08-06.json").write_text(json.dumps({"items": [{"title": "x", "entities": ["Alibaba"]}]}))
            (d / "2026-09-01.json").write_text(json.dumps({"items": [{"title": "Gemini 4 Hydrogen leaks", "entities": []}]}))
            (d / "2026-11-16.json").write_text(json.dumps({"items": [{"title": "hoy", "entities": ["Alibaba"]}]}))
            known = known_before(d, "2026-11-16")
            today = [{"entities": ["Alibaba", "Gemini 4 Hydrogen", "Nathaniel Craig"]}]
            self.assertEqual(entity_deltas([], today, known)["new_entrants"], ["Nathaniel Craig"])
            self.assertEqual(entity_deltas([], today)["new_entrants"], ["Alibaba", "Gemini 4 Hydrogen", "Nathaniel Craig"])
