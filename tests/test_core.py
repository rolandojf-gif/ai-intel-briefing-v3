import unittest

from src.main import clean_entities, clean_signal_text
from src.render import _safe_url, signal_level, translate_headline_es
from src.score import score_item


class CoreQualityTests(unittest.TestCase):
    def test_x_text_cleanup_removes_markdown_and_image_noise(self):
        raw = 'NVIDIA [#AI](https://x.com/hashtag/AI) !Image 5: demo https://x.com/foo'
        self.assertEqual(clean_signal_text(raw, "X @NVIDIAAI"), "NVIDIA AI demo")

    def test_specific_gpt_entity_suppresses_generic_gpt(self):
        entities = clean_entities(["GPT-5.5", "GPT", "Update", "OpenAI"], "GPT-5.5 is available")
        self.assertEqual(entities, ["GPT-5.5", "OpenAI", "GPT-5"])

    def test_signal_level_requires_real_score_not_theme_concentration(self):
        items = [{"score": 18}, {"score": 12}, {"score": 8}]
        label, css, avg = signal_level(items)
        self.assertEqual((label, css), ("Low", "low"))
        self.assertLess(avg, 20)

    def test_hard_model_release_scores_above_soft_promo(self):
        hard = score_item("GPT-5.5 is now available in the API with new pricing", "", "X @OpenAI")
        soft = score_item("Applications now open for a sponsored AI webinar", "", "NVIDIA Blog (AI)")
        self.assertGreaterEqual(hard["score"], 50)
        self.assertLess(soft["score"], hard["score"])

    def test_safe_url_blocks_javascript(self):
        self.assertEqual(_safe_url("javascript:alert(1)"), "#")
        self.assertEqual(_safe_url("https://example.com/a"), "https://example.com/a")

    def test_headline_fallback_translation_is_spanish(self):
        title = translate_headline_es("Gemini 3.5: frontier intelligence with action")
        self.assertIn("inteligencia de frontera", title)
        self.assertIn("capacidad de acción", title)

    def test_frontier_models_scored_high(self):
        kimi_test = score_item("Moonshot AI releases Kimi K3 with massive reasoning capabilities", "New frontier open weights and API pricing available", "Simon Willison (AI & LLMs)")
        glm_test = score_item("Zhipu AI launches GLM-5 model family with new benchmark evals", "Weights and API now available", "MarkTechPost (AI Releases)")
        mythos_test = score_item("Mythos AI and Sol frontier models benchmarked against Claude and Gemini", "New agentic reasoning architecture", "X Frontier & LLM Releases")
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


if __name__ == "__main__":
    unittest.main()
