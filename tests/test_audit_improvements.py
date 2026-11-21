"""Tests de regresion para las mejoras de ingestion, calibracion, UX, bilinguismo y CI."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import src.config as config
import src.fetch as fetch
import src.health_check as health_check
import src.main as main
import src.render as render
import src.score as score


class IngestionAndDedupTests(unittest.TestCase):
    def test_ingest_sorts_by_freshness_and_score_before_cap_and_resolves_gn_after(self):
        cfg = {
            "sources": [
                {"name": "Google News AI", "type": "rss", "url": "https://news.google.com/rss/search?q=ai", "limit": 10}
            ]
        }
        now = datetime.now(timezone.utc)
        fresh_iso = now.isoformat()
        old_iso = "2020-01-01T00:00:00+00:00"
        raw_items = [
            {
                "title": "Old generic commentary",
                "summary": "random words",
                "link": "https://news.google.com/rss/articles/OLD",
                "published": old_iso,
                "image_url": "",
            },
            {
                "title": "Fresh low signal post",
                "summary": "minor update",
                "link": "https://news.google.com/rss/articles/LOW",
                "published": fresh_iso,
                "image_url": "",
            },
            {
                "title": "OpenAI launches GPT-6 reasoning model API",
                "summary": "Frontier benchmark reasoning training release",
                "link": "https://news.google.com/rss/articles/BEST",
                "published": fresh_iso,
                "image_url": "",
            },
        ]
        resolved_calls: list[list[str]] = []

        def fake_resolve(items: list[dict]) -> list[dict]:
            resolved_calls.append([it["link"] for it in items])
            for it in items:
                it["link"] = "https://openai.com/gpt-6"
            return items

        with mock.patch.object(main, "fetch_rss", return_value=raw_items) as m_rss, \
             mock.patch.object(main, "resolve_items_google_news", side_effect=fake_resolve):
            items, _ = main.ingest_feeds(cfg, {"Google News AI": 1})

        m_rss.assert_called_once()
        self.assertTrue(m_rss.call_args.kwargs.get("resolve_gn") is False)
        self.assertEqual(len(items), 1)
        self.assertIn("GPT-6", items[0]["title"])
        self.assertEqual(resolved_calls, [["https://news.google.com/rss/articles/BEST"]])
        self.assertEqual(items[0]["url"], "https://openai.com/gpt-6")

    def test_dedup_keeps_new_development_in_short_title(self):
        a = {"title": "OpenAI launches agent API", "link": "https://a.example/1", "source": "Source A"}
        b = {"title": "OpenAI launches agent pricing", "link": "https://b.example/2", "source": "Source B"}
        c = {"title": "OpenAI launches new Claude model", "link": "https://c.example/3", "source": "Source C"}
        out = main.dedup_items([a, b, c])
        # El precio de la API es un desarrollo distinto de su lanzamiento.
        self.assertEqual(out, [a, b, c])

    def test_cross_day_fuzzy_repeat_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "2026-11-14.json").write_text(
                json.dumps({
                    "items": [
                        {
                            "title": "Anthropic unveils Claude 5 frontier coding model",
                            "title_es": "Anthropic presenta Claude 5 para programación avanzada",
                            "url": "https://anthropic.com/claude-5",
                        }
                    ]
                }),
                encoding="utf-8",
            )
            token_sets, headlines = main.load_recent_context(d, today="2026-11-15", days=2)
            self.assertTrue(headlines)
            candidate = {
                "title": "Anthropic unveils Claude 5 coding model with new API",
                "link": "https://other.news/anthropic-claude-5",
                "heuristic_score": 80,
            }
            scored = main.apply_novelty_penalty(
                [candidate],
                history_urls=set(),
                history_titles=set(),
                recent_token_sets=token_sets,
            )
            self.assertTrue(scored[0]["is_repeat"])
            self.assertEqual(scored[0]["adjusted_score"], 55)

    def test_fetch_artificial_analysis_does_not_fabricate_published_date(self):
        html_no_date = "<html><body><a href='/articles/gpt-5'>GPT-5 Leaderboard Benchmarks</a></body></html>"
        html_with_date = (
            '<html><body><time datetime="2026-11-14T12:00:00Z">Nov 14</time>'
            '<a href="/articles/claude-5">Claude 5 Intelligence Benchmark</a></body></html>'
        )
        resp = mock.MagicMock()
        resp.raise_for_status.return_value = None

        with mock.patch.object(fetch.requests, "get", return_value=resp):
            resp.text = html_no_date
            items_none = fetch.fetch_artificial_analysis(limit=5)
            resp.text = html_with_date
            items_dated = fetch.fetch_artificial_analysis(limit=5)

        self.assertEqual(len(items_none), 1)
        self.assertIsNone(items_none[0]["published"])
        self.assertEqual(len(items_dated), 1)
        self.assertEqual(items_dated[0]["published"], "2026-11-14T12:00:00+00:00")


class CalibrationAndLimitsTests(unittest.TestCase):
    def test_noise_penalty_exempts_real_model_launches_from_official_blogs(self):
        it = {
            "source": "Google DeepMind Blog",
            "title": "Gemini 4 reasoning model release with new multimodal API",
            "summary": "Frontier benchmark launch for developers",
            "entities": ["Google DeepMind", "Gemini"],
        }
        self.assertEqual(main.compute_noise_penalty(it), 0)

    def test_score_boosts_frontier_models_and_strategic_sources(self):
        s_model = score.score_item("NVIDIA Rubin GPU cluster benchmark release", "New training architecture", "SemiAnalysis")
        s_chinatalk = score.score_item("Export controls hit advanced lithography supply chain", "Policy brief", "ChinaTalk")
        self.assertGreaterEqual(s_model["score"], 50)
        self.assertGreaterEqual(s_chinatalk["score"], 25)

    def test_apply_llm_results_soft_caps_repeats_in_signals(self):
        items = []
        results_map = {}
        # 5 repeats scored slightly higher than 10 fresh signals
        for i in range(1, 6):
            items.append({
                "_rid": i,
                "title": f"Repeat story {i}",
                "link": f"https://example.com/r{i}",
                "source": "TechCrunch AI",
                "heuristic_score": 80,
                "adjusted_score": 60,
                "novelty_score": 65,
                "is_repeat": True,
            })
            results_map[str(i)] = {
                "verdict": "signal",
                "relevance": 90,
                "headline_es": f"Repetida {i}",
                "headline_en": f"Repeat {i}",
                "so_what": "ok",
                "so_what_en": "ok",
                "primary": "models",
                "entities": ["OpenAI"],
            }
        for i in range(6, 16):
            items.append({
                "_rid": i,
                "title": f"Fresh story {i}",
                "link": f"https://example.com/f{i}",
                "source": "Anthropic News",
                "heuristic_score": 70,
                "adjusted_score": 70,
                "novelty_score": 100,
                "is_repeat": False,
            })
            results_map[str(i)] = {
                "verdict": "signal",
                "relevance": 78,
                "headline_es": f"Nueva {i}",
                "headline_en": f"Fresh {i}",
                "so_what": "ok",
                "so_what_en": "ok",
                "primary": "models",
                "entities": ["Anthropic"],
            }

        selected = main.apply_llm_results(items, results_map)
        signals = [it for it in selected if it["layer"] == "signal"]
        repeats_in_signals = sum(1 for it in signals if it.get("is_repeat"))
        self.assertEqual(len(signals), main.MAX_SIGNALS)
        self.assertLessEqual(repeats_in_signals, main.MAX_REPEAT_SIGNALS)


class UxTimezoneHealthTests(unittest.TestCase):
    def test_radar_today_str_uses_madrid_timezone(self):
        utc_late = datetime(2026, 11, 15, 23, 30, tzinfo=timezone.utc)
        self.assertEqual(config.radar_today_str(utc_late), "2026-11-16")

    def test_render_accessible_tabs_and_bilingual_chrome(self):
        items = [
            {
                "title_es": "Señal 1",
                "title_en": "Signal 1",
                "layer": "signal",
                "score": 90,
                "strategic_theme": "frontier_capability",
                "power_shift": "X gana / Y pierde",
                "power_shift_en": "X gains / Y loses",
                "watch_next": "Hito verificable",
                "watch_next_en": "Verifiable milestone",
                "url": "https://example.com/1",
                "is_new": True,
            },
            {
                "title_es": "Señal 2",
                "title_en": "Signal 2",
                "layer": "signal",
                "score": 80,
                "strategic_theme": "china_stack",
                "url": "https://example.com/2",
                "is_new": False,
            },
            {
                "source": "Together AI",
                "title_es": "Contexto 1",
                "title_en": "Context 1",
                "layer": "context",
                "score": 55,
                "strategic_theme": "frontier_capability",
                "url": "https://example.com/3",
                "is_new": False,
            },
        ]
        html = render.render_index(
            items,
            briefing={"thesis": "Tesis", "thesis_en": "Thesis"},
            snapshot={"date": "2026-11-15", "x_layer": {"status": "killed"}},
            market={},
        )
        self.assertIn('role="tablist"', html)
        self.assertIn('<button type="button" role="tab" aria-selected="true" class="tab on"', html)
        self.assertIn("classList.toggle('filter-empty'", html)
        self.assertIn('id="ctx-block"', html)
        self.assertIn("yesterday's edition", html)
        self.assertIn("X off", html)
        self.assertIn('<span class="k"><span class="l-es">Impacto</span><span class="l-en" lang="en">Impact</span></span>', html)
        self.assertIn('<span class="k"><span class="l-es">Vigilar</span><span class="l-en" lang="en">Watch</span></span>', html)
        ctx = html.split('id="ctx-block"', 1)[1].split("</section>", 1)[0]
        self.assertIn('data-topic="frontier_capability"', ctx)
        for text in ("Contexto 1", "Context 1", "Together AI"):
            self.assertIn(text, ctx)
        self.assertNotIn('class="score', ctx)
        self.assertNotIn("data-copy", html)
        self.assertEqual(render.score_tier(97), "s-95")
        self.assertEqual(render.score_tier(90), "s-88")
        self.assertEqual(render.score_tier(82), "s-80")
        self.assertEqual(render.score_tier(74), "s-70")
        self.assertEqual(render.score_tier(55), "s-low")
        self.assertIn('<span class="score s-88">', html)
        self.assertIn('<span class="score s-80">80/100</span>', html)

    def test_llm_rank_fields_enforce_concise_non_redundant_copy(self):
        import src.llm_rank as llm_rank
        fields = llm_rank.RankOut.model_fields
        self.assertIn("150", fields["so_what"].description)
        self.assertIn("65", fields["power_shift"].description)
        self.assertIn("75", fields["watch_next"].description)

    def test_health_check_warns_when_x_layer_killed_without_failing(self):
        snap = {
            "date": "2026-11-15",
            "degraded": False,
            "counts": {"signal": 10, "context": 3},
            "source_health": {"configured": 35, "alive": 35, "dead": []},
            "x_layer": {"status": "killed", "reason": "zero_posts"},
        }
        code, annotations, summary = health_check.check(snap)
        self.assertEqual(code, 0)
        self.assertTrue(any("::warning title=Capa X apagada::" in a for a in annotations))
        self.assertTrue(any("Capa X apagada" in line for line in summary))
    def test_weekly_deduplicates_items_and_renders_modern_dossier(self):
        from pathlib import Path
        import src.weekly as weekly
        snaps = [
            {
                "date": "2026-11-16",
                "items": [
                    {"title_es": "Qwen4-Max v1", "url": "https://example.com/qwen4", "score": 100, "layer": "signal", "entities": ["Alibaba"]},
                ],
            },
            {
                "date": "2026-11-17",
                "items": [
                    {"title_es": "Qwen4-Max repetida", "url": "https://example.com/qwen4/", "score": 72, "layer": "context", "entities": ["Alibaba"]},
                    {"title_es": "Agentes OpenAI", "url": "https://example.com/openai", "score": 94, "layer": "signal", "entities": ["OpenAI"]},
                ],
            },
        ]
        ent_hits = weekly.pick_items_for_entity(snaps, "Alibaba", limit=6)
        self.assertEqual(len(ent_hits), 1)
        top_hits = weekly._pick_weekly_top_signals(snaps, limit=6)
        self.assertEqual(len(top_hits), 2)
        self.assertEqual(top_hits[0]["score"], 100)

        weekly.main()
        html = Path("docs/weekly.html").read_text(encoding="utf-8")
        self.assertIn('class="kpi-grid"', html)
        self.assertIn("class='tl-day'", html)
        self.assertIn("class='wk-card'", html)
        self.assertIn('id="wk-tabs"', html)
        self.assertNotIn("&amp;quot;", html)
        self.assertEqual(weekly._bi_opt("Solo español", ""), "<span class='l-es'>Solo español</span>")

        import re
        body = re.sub(r"<head>.*?</head>|<style>.*?</style>|<script>.*?</script>", "", html, flags=re.S)
        en_view = re.sub(r"<span class=['\"]l-es['\"][^>]*>.*?</span>", "", body, flags=re.S)
        en_texts = [re.sub(r"\s+", " ", t).strip() for t in re.split(r"<[^>]+>", en_view)]
        # Nombres propios con tilde o eñe (personas, productos): no son texto en español.
        proper = ("Rolando Fernández", "Jalapeño")
        en_texts = [t for t in en_texts if t and t != "Rolando Fernández"]
        en_texts = [t for t in (re.sub("|".join(map(re.escape, proper)), "", t) for t in en_texts)]
        spanish_re = re.compile(r"[áéíóúñ¿¡]|\b(señales|menciones|ediciones|impacto|vigilar|confirmadas|alto voltaje)\b", re.I)
        self.assertEqual([t for t in en_texts if spanish_re.search(t)], [])

    def test_adaptive_hero_subleads_cover_and_image_inheritance(self):
        import xml.etree.ElementTree as ET
        import src.cover as cover
        import src.main as main_mod

        # 1) Hero sin imagen -> modo Dossier editorial (sin <img> placeholder gigante)
        no_photo_items = [
            {"title_es": "OpenAI lanza GPT-6.2", "title_en": "OpenAI launches GPT-6.2", "layer": "signal",
             "score": 100, "strategic_theme": "frontier_capability", "source": "OpenAI",
             "url": "https://openai.com/gpt-6-2", "image_url": "", "entities": ["OpenAI"],
             "power_shift": "OpenAI avanza", "power_shift_en": "OpenAI advances",
             "watch_next": "Benchmarks", "watch_next_en": "Benchmarks"},
            {"title_es": "Sublead dos", "title_en": "Sublead two", "layer": "signal",
             "score": 95, "strategic_theme": "agents_automation", "source": "TechCrunch AI",
             "url": "https://example.com/2", "image_url": "https://cdn.example.com/2.jpg"},
            {"title_es": "Sublead tres", "title_en": "Sublead three", "layer": "signal",
             "score": 90, "strategic_theme": "compute_chips_dc", "source": "The Verge AI",
             "url": "https://example.com/3", "image_url": ""},
        ]
        html_dossier = render.render_index(
            no_photo_items,
            briefing={"thesis": "Tesis", "thesis_en": "Thesis"},
            snapshot={"date": "2026-11-18", "pulse": {"value": 92, "series": [{"date": "2026-11-18", "value": 92}]}},
            market={},
        )
        self.assertIn('class="lead lead-dossier"', html_dossier)
        self.assertNotIn('class="lead-media"', html_dossier)
        self.assertIn('class="lead-wm"', html_dossier)
        self.assertIn('class="lead-cta"', html_dossier)
        self.assertNotIn('class="subleads"', html_dossier)
        self.assertIn("grid-template-columns:minmax(295px,330px) minmax(0,1.85fr) minmax(310px,345px)", html_dossier)
        self.assertIn("align-items:stretch", html_dossier)
        self.assertLess(html_dossier.index('class="rail"'), html_dossier.index('class="lead lead-dossier"'))
        self.assertIn("<b>92/100</b>", html_dossier)
        self.assertLess(html_dossier.index('class="opening"'), html_dossier.index('class="telemetry-band"'))

        # 2) Hero con foto -> modo Photo con barra superpuesta y fallback JS a Dossier
        photo_items = [dict(no_photo_items[0], image_url="https://cdn.example.com/hero.jpg")]
        html_photo = render.render_index(photo_items, briefing={"thesis": "Tesis"}, snapshot={"date": "2026-11-18"}, market={})
        self.assertIn('class="lead lead-photo"', html_photo)
        self.assertIn('class="lead-media"', html_photo)
        self.assertIn("lead.classList.add('lead-dossier')", html_photo)

        # 3) Cover SVG mejorada con entidad y score (XML válido < 6KB)
        svg = cover.cover_svg("frontier_capability", "Capacidad frontier", "OpenAI", seed="s1", entity="OpenAI", score=100)
        ET.fromstring(svg)
        self.assertIn("OPENAI", svg)
        self.assertIn(">100<", svg)
        self.assertLess(len(svg), 6000)

        # 4) Herencia de image_url en merge_same_story
        lead = {"title": "OpenAI launches GPT-6.2 Astra and Sol with lower API pricing",
                "title_es": "OpenAI lanza GPT-6.2 Astra y Sol con menor coste de API",
                "source": "OpenAI", "url": "https://openai.com/a",
                "llm_score": 100, "verdict": "signal", "strategic_theme": "frontier_capability",
                "entities": ["OpenAI", "GPT-6.2 Astra"], "image_url": ""}
        dup = {"title": "OpenAI launches GPT-6.2 Astra and Sol with lower API pricing",
               "title_es": "OpenAI lanza GPT-6.2 Astra y Sol con menor coste de API",
               "source": "The Verge AI", "url": "https://theverge.com/a",
               "llm_score": 95, "verdict": "signal", "strategic_theme": "frontier_capability",
               "entities": ["OpenAI", "GPT-6.2 Astra"], "image_url": "https://cdn.theverge.com/gpt62.jpg"}
        merged = main_mod.merge_same_story([lead, dup])
        self.assertEqual(merged, 1)
        self.assertEqual(lead["image_url"], "https://cdn.theverge.com/gpt62.jpg")


if __name__ == "__main__":
    unittest.main()
