import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.health_check import check, main


BASE = {
    "date": "2026-11-13",
    "counts": {"signal": 10, "context": 3},
    "source_health": {"configured": 36, "alive": 36, "dead": []},
}


class HealthCheckTests(unittest.TestCase):
    def test_degraded_day_fails_and_explains_why(self):
        snap = {**BASE, "degraded": True,
                "llm_error": "ClientError('400 Developer instruction is not enabled for api version v1')"}
        code, annotations, summary = check(snap)

        self.assertEqual(code, 1)
        errors = [a for a in annotations if a.startswith("::error")]
        self.assertEqual(len(errors), 1)
        self.assertIn("api version v1", errors[0])
        self.assertIn("DEGRADADO", summary[0])

    def test_degraded_without_recorded_error_still_fails(self):
        code, annotations, _ = check({**BASE, "degraded": True})
        self.assertEqual(code, 1)
        self.assertIn("sin error registrado", annotations[-1])

    def test_healthy_day_passes(self):
        code, annotations, summary = check({**BASE, "degraded": False})
        self.assertEqual(code, 0)
        self.assertEqual(annotations, [])
        self.assertIn("10 senales", summary[0])

    def test_dead_sources_warn_but_do_not_fail(self):
        snap = {**BASE, "degraded": False,
                "source_health": {"configured": 36, "alive": 34, "dead": ["Yahoo Finance News", "OpenRouter"]}}
        code, annotations, _ = check(snap)
        self.assertEqual(code, 0)
        self.assertTrue(annotations[0].startswith("::warning"))
        self.assertIn("Yahoo Finance News, OpenRouter", annotations[0])
        self.assertIn("34/36", annotations[0])

    def test_newlines_cannot_break_the_annotation(self):
        """Un error multilinea partiria el comando y GitHub perderia el resto."""
        code, annotations, _ = check({**BASE, "degraded": True, "llm_error": "linea 1\nlinea 2 100%"})
        self.assertNotIn("\n", annotations[-1])
        self.assertIn("linea 1%0Alinea 2 100%25", annotations[-1])

    def test_rss_day_without_snapshot_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main("2026-11-14", Path(tmp)), 0)

    def test_main_writes_step_summary_and_returns_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "2026-11-13.json").write_text(
                json.dumps({**BASE, "degraded": True, "llm_error": "boom"}), encoding="utf-8")
            summary_file = Path(tmp, "summary.md")
            with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary_file)}):
                code = main("2026-11-13", Path(tmp))
            self.assertEqual(code, 1)
            self.assertIn("boom", summary_file.read_text(encoding="utf-8"))


class SnapshotRecordsLlmErrorTests(unittest.TestCase):
    def test_main_snapshot_carries_llm_error_field(self):
        """El aviso solo puede explicar el fallo si main.py lo guarda en el snapshot."""
        import inspect
        import src.main as m

        self.assertIn('"llm_error"', inspect.getsource(m))
        self.assertIn("LLM_LAST_ERROR = repr(last_err)", inspect.getsource(m.generate_llm_data))


if __name__ == "__main__":
    unittest.main()
