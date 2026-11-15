"""Publicacion: metadatos para buscadores, firma, ingles y dominio."""
import tempfile
import unittest
from pathlib import Path


class PublishTests(unittest.TestCase):
    ITEMS = [{"title": "Gemini 4 released", "title_es": "Sale Gemini 4", "title_en": "Gemini 4 is out",
              "so_what": "Salto de capacidad.", "so_what_en": "A capability jump.",
              "layer": "signal", "score": 90, "url": "https://example.com/a", "strategic_theme": "frontier_capability"}]

    def _html(self):
        from src.render import render_index
        return render_index([dict(i) for i in self.ITEMS], briefing={"thesis": "Tesis", "thesis_en": "Thesis"},
                            snapshot={"date": "2026-11-15"}, market={})

    def test_seo_metadata_points_to_the_public_domain(self):
        html = self._html()
        self.assertIn('<link rel="canonical" href="https://aievolve.netlify.app/"/>', html)
        self.assertIn('name="google-site-verification" content="yh8wm8HsAeqP892U5UGczQs-RLnGuNHx7WGfNntGduk"', html)
        self.assertIn('property="og:image" content="https://aievolve.netlify.app/og.png"', html)
        self.assertIn('name="robots" content="index, follow', html)
        self.assertIn("application/ld+json", html)
        self.assertNotIn("earnest-pie", html)

    def test_cloudflare_beacon_is_on_every_page_and_off_without_token(self):
        import src.brand as brand
        from src.archive import ARCHIVO_TEMPLATE
        beacon = 'data-cf-beacon=\'{"token": "ddd22b1c510f4ef2a210078c77c6d2d5"}\''
        self.assertIn(beacon, self._html())
        self.assertIn(beacon, str(brand.seo_head("t", path="weekly.html")))
        self.assertIn("cloudflareinsights", ARCHIVO_TEMPLATE.render(months=[], n=0, n_entries=0, first="", last="", missing=""))
        old = brand.CLOUDFLARE_TOKEN
        try:
            brand.CLOUDFLARE_TOKEN = ""
            self.assertNotIn("cloudflareinsights", str(brand.seo_head("t")))
        finally:
            brand.CLOUDFLARE_TOKEN = old

    def test_signature_and_coffee_link(self):
        html = self._html()
        self.assertIn("Rolando Fernández", html)
        self.assertIn('href="https://buymeacoffee.com/rolandofernandez"', html)

    def test_news_and_ui_ship_in_both_languages(self):
        html = self._html()
        self.assertIn('<span class="l-es">Sale Gemini 4</span><span class="l-en" lang="en">Gemini 4 is out</span>', html)
        self.assertIn('<span class="l-es">Tesis</span><span class="l-en" lang="en">Thesis</span>', html)
        self.assertIn('data-lang-set="en"', html)
        self.assertIn("A capability jump.", html)

    def test_bi_escapes_and_falls_back_to_spanish(self):
        from src.brand import bi
        self.assertEqual(str(bi("solo <b>", "")), "solo &lt;b&gt;")
        self.assertIn("&lt;x&gt;", str(bi("a", "<x>")))

    def test_llm_schema_asks_for_english(self):
        from src.llm_rank import Briefing, RankOut
        for f in ("headline_en", "so_what_en", "power_shift_en", "watch_next_en"):
            self.assertEqual(RankOut.model_fields[f].default, "")
        self.assertIn("thesis_en", Briefing.model_fields)

    def test_archive_writes_sitemap_and_robots(self):
        import json
        from src.archive import write_archive
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); (out / "data").mkdir()
            (out / "data" / "2026-11-15.json").write_text(json.dumps(
                {"date": "2026-11-15", "briefing": {"thesis": "t"}, "items": [{"title": "a", "layer": "signal", "url": "https://e.com/a"}]}))
            write_archive(out, write_days=False)
            sm = (out / "sitemap.xml").read_text()
            self.assertIn("<loc>https://aievolve.netlify.app/</loc>", sm)
            self.assertIn("<loc>https://aievolve.netlify.app/d/2026-11-15.html</loc>", sm)
            self.assertIn("Sitemap: https://aievolve.netlify.app/sitemap.xml", (out / "robots.txt").read_text())


if __name__ == "__main__":
    unittest.main()
