import unittest

from src.main import clean_entities, clean_signal_text
from src.render import _safe_url, signal_level
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


if __name__ == "__main__":
    unittest.main()
