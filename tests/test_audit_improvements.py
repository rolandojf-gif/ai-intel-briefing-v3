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

    def test_dedup_items_short_title_threshold(self):
        a = {"title": "OpenAI launches agent API", "link": "https://a.example/1", "source": "Source A"}
        b = {"title": "OpenAI launches agent pricing", "link": "https://b.example/2", "source": "Source B"}
        c = {"title": "OpenAI launches new Claude model", "link": "https://c.example/3", "source": "Source C"}
        out = main.dedup_items([a, b, c])
        # a y b comparten 3/4 palabras (75%) -> fusionan; c solo comparte 2 palabras -> se conserva
        self.assertEqual(len(out), 2)
        self.assertIn("Source B", out[0].get("other_sources", []))

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
        self.assertIn("En segundo plano", html)
        self.assertIn("Supporting signals shaping the backdrop", html)
        self.assertIn('<span class="cx-tag">', html)

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


if __name__ == "__main__":
    unittest.main()
