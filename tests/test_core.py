import unittest

from src.fetch import _extract_image_url
from src.main import clean_entities, clean_signal_text, apply_llm_results
from src.memory import activity_level, detect_threads, entity_deltas, resolve_watchlist
from src.render import _safe_url, display_title, human_theme, score_value
from src.score import score_item
from src.llm_rank import RankOut, Briefing, BatchOut


class CoreQualityTests(unittest.TestCase):
    def test_x_text_cleanup_removes_markdown_and_image_noise(self):
        raw = 'NVIDIA [#AI](https://x.com/hashtag/AI) !Image 5: demo https://x.com/foo'
        self.assertEqual(clean_signal_text(raw, "X @NVIDIAAI"), "NVIDIA AI demo")

    def test_specific_gpt_entity_suppresses_generic_gpt(self):
        entities = clean_entities(["GPT-5.5", "GPT", "Update", "OpenAI"], "GPT-5.5 is available")
        self.assertEqual(entities, ["GPT-5.5", "OpenAI"])

    def test_activity_level_honest_labeling(self):
        # Degraded run
        label, css = activity_level([], degraded=True)
        self.assertEqual((label, css), ("SIN FILTRAR", "quiet"))

        # Zero signals
        label, css = activity_level([{"layer": "context", "final_score": 80}])
        self.assertEqual((label, css), ("SIN SEÑAL", "quiet"))

        # Strong signal
        label, css = activity_level([{"layer": "signal", "final_score": 90}])
        self.assertEqual((label, css), ("ACTIVO", "active"))

        # Multiple strong signals
        label, css = activity_level([{"layer": "signal", "final_score": 85}] * 3)
        self.assertEqual((label, css), ("ALERTA", "alert"))

    def test_hard_model_release_scores_above_soft_promo(self):
        hard = score_item("GPT-5.5 is now available in the API with new pricing", "", "OpenAI")
        soft = score_item("Applications now open for a sponsored AI webinar", "", "NVIDIA Blog (AI)")
        self.assertGreaterEqual(hard["score"], 50)
        self.assertLess(soft["score"], hard["score"])

    def test_safe_url_blocks_javascript(self):
        self.assertEqual(_safe_url("javascript:alert(1)"), "#")
        self.assertEqual(_safe_url("https://example.com/a"), "https://example.com/a")

    def test_display_title_uses_llm_headline_or_fallback(self):
        item_with_es = {"title": "Raw English Title", "title_es": "Titular en español"}
        item_without_es = {"title": "Raw English Title", "title_es": ""}
        self.assertEqual(display_title(item_with_es), "Titular en español")
        self.assertEqual(display_title(item_without_es), "Raw English Title")

    def test_frontier_models_scored_high(self):
        kimi_test = score_item("Moonshot AI releases Kimi K3 with massive reasoning capabilities", "New frontier open weights and API pricing available", "Simon Willison (AI & LLMs)")
        glm_test = score_item("Zhipu AI launches GLM-5 model family with new benchmark evals", "Weights and API now available", "Together AI")
        mythos_test = score_item("Mythos AI and Sol frontier models benchmarked against Claude and Gemini", "New agentic reasoning architecture", "SemiAnalysis")
        self.assertGreaterEqual(kimi_test["score"], 50)
        self.assertEqual(kimi_test["primary"], "models")
        self.assertGreaterEqual(glm_test["score"], 50)
        self.assertGreaterEqual(mythos_test["score"], 50)

    def test_frontier_entities_cleaned_correctly(self):
        entities = clean_entities(["Kimi k3", "Moonshot", "GLM 5", "Zhipu", "Mythos", "Sol"], "Kimi K3 and GLM-5 released")
        self.assertIn("Kimi K3", entities)
        self.assertIn("Moonshot AI", entities)
        self.assertIn("GLM-5", entities)
        self.assertIn("Zhipu AI", entities)

    def test_relevance_gate_filters_noise(self):
        candidates = [
            {"_rid": 1, "title": "Gemini 3.5 Released", "score": 90, "heuristic_score": 90, "adjusted_score": 90},
            {"_rid": 2, "title": "Minor library patch 1.0.2", "score": 40, "heuristic_score": 40, "adjusted_score": 40},
            {"_rid": 3, "title": "Data center power constraints", "score": 75, "heuristic_score": 75, "adjusted_score": 75},
        ]
        results_map = {
            "1": {"relevance": 95, "verdict": "signal", "headline_es": "Lanzamiento de Gemini 3.5", "so_what": "Salto clave", "theme": "frontier_capability"},
            "2": {"relevance": 10, "verdict": "noise", "headline_es": "Parche menor", "so_what": "Tooling menor", "theme": "other"},
            "3": {"relevance": 70, "verdict": "context", "headline_es": "Límite energético en centros de datos", "so_what": "Cuello de botella", "theme": "compute_chips_dc"},
        }
        final = apply_llm_results(candidates, results_map)
        self.assertEqual(len(final), 2)
        layers = [it["layer"] for it in final]
        self.assertIn("signal", layers)
        self.assertIn("context", layers)
        self.assertNotIn("noise", layers)

    def test_memory_watchlist_resolution(self):
        history = [{
            "date": "2026-08-21",
            "briefing": {
                "watch": ["Vigilar precios de DeepSeek R1 y cuotas de inferencia", "Confirmar despliegue de Blackwell B200"]
            }
        }]
        today_items = [
            {"title_es": "DeepSeek R1 reduce precios de inferencia un 30%", "entities": ["DeepSeek"]}
        ]
        resolved = resolve_watchlist(history, today_items)
        self.assertEqual(len(resolved), 2)
        self.assertEqual(resolved[0]["status"], "hit")
        self.assertEqual(resolved[1]["status"], "open")

    def test_image_extraction_from_rss_entry(self):
        class DummyEntryMedia:
            media_content = [{"url": "https://example.com/thumb.jpg", "medium": "image"}]
            media_thumbnail = []
            enclosures = []
            links = []
            summary = "<p>Sample summary</p>"
            description = ""
            content = []

        img = _extract_image_url(DummyEntryMedia())
        self.assertEqual(img, "https://example.com/thumb.jpg")

        class DummyEntryHtml:
            media_content = []
            media_thumbnail = []
            enclosures = []
            links = []
            summary = '<p>Check this <img src="https://example.com/featured.png" alt="ai"/> news</p>'
            description = ""
            content = []

        img2 = _extract_image_url(DummyEntryHtml())
        self.assertEqual(img2, "https://example.com/featured.png")

    def test_market_overview_includes_indices_and_smci(self):
        from src.market import get_market_overview
        data = get_market_overview()
        self.assertIn("macro", data)
        self.assertIn("companies", data)
        macro_labels = [m["label"] for m in data["macro"]]
        self.assertIn("S&P Futures", macro_labels)
        self.assertIn("Bitcoin", macro_labels)
        tickers = [c["ticker"] for c in data["companies"]]
        self.assertIn("NVDA", tickers)
        self.assertIn("SMCI", tickers)
        self.assertIn("TSM", tickers)

    def test_discover_render_generates_valid_html(self):
        from src.render import render_index
        items = [
            {"title": "Gemini 3.7 Released", "title_es": "Lanzamiento de Gemini 3.7", "score": 95, "layer": "signal", "image_url": "https://example.com/g.png"},
            {"title": "SMCI server cluster", "title_es": "SMCI despliega nuevo cluster", "score": 85, "layer": "signal", "image_url": ""},
            {"title": "DeepSeek analysis", "title_es": "Análisis de DeepSeek", "score": 75, "layer": "context", "image_url": ""},
        ]
        html = render_index(items, briefing={"thesis": "Tesis de prueba"}, snapshot={"date": "2026-08-23"})
        self.assertIn("AI Strategic Radar", html)
        self.assertIn("Lanzamiento de Gemini 3.7", html)
        self.assertIn("Perspectiva del mercado", html)
        self.assertIn("SMCI", html)


if __name__ == "__main__":
    unittest.main()
