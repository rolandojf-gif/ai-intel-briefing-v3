"""El cliente de Gemini debe hablar con v1beta, la unica API que acepta system_instruction.

Del 2026-11-07 al 2026-11-13 el radar estuvo en modo degradado: google-genai 3.x
cambio la API por defecto a v1, que responde 400 a system_instruction, y como el
SDK no tenia version fijada el CI lo actualizo solo. El workflow seguia en verde.
"""
import os
import unittest
from unittest import mock


class GeminiClientTests(unittest.TestCase):
    def test_client_uses_v1beta_regardless_of_sdk_default(self):
        from src.llm_rank import make_client

        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            client = make_client()

        self.assertEqual(client._api_client._http_options.api_version, "v1beta")

    def test_rank_batch_builds_its_client_through_make_client(self):
        """Si alguien vuelve a escribir genai.Client() a pelo, este test falla."""
        import inspect
        import src.llm_rank as llm_rank

        source = inspect.getsource(llm_rank.rank_batch)
        self.assertIn("make_client()", source)
        self.assertNotIn("genai.Client(", source)


if __name__ == "__main__":
    unittest.main()
