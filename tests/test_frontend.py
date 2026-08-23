"""Tests del JavaScript embebido en las plantillas.

Los 54 tests de test_core.py cubren Python. El JS vive dentro de cadenas, asi
que ninguno podia verlo: por ese hueco paso una esc() que mapeaba cada caracter
a si mismo ('&':'&', '<':'<', ...) y no escapaba nada, dejando un XSS
almacenado en la busqueda del archivo.

Aqui se ejecuta el JavaScript real extraido de la plantilla con node, no una
reimplementacion en Python: es lo unico que demuestra que la pagina publicada
se comporta como creemos.
"""
import unittest


class EmbeddedJavaScriptTests(unittest.TestCase):
    """El JS embebido no lo cubria ningun test.

    Por ese hueco paso una esc() que mapeaba cada caracter a si mismo
    ('&':'&', '<':'<', ...): parecia correcta y no escapaba nada. Aqui se
    ejecuta el JavaScript real extraido de la plantilla, no una reimplementacion
    en Python, que es lo unico que demuestra que la pagina publicada es segura.
    """

    HOSTILE = '<img src=x onerror="alert(1)">'

    def _archive_html(self):
        from src.archive import ARCHIVO_TEMPLATE
        return ARCHIVO_TEMPLATE.render(
            months=[], total_days=0, total_signals=0, latest="2026-08-24"
        )

    def _extract_esc(self, html):
        import re
        m = re.search(r"function esc\(s\)\{.*?\n  \}", html, re.S)
        self.assertIsNotNone(m, "no se encontro la funcion esc() en la plantilla del archivo")
        return m.group(0)

    def _run_node(self, script):
        """Devuelve stdout, o None si node no esta instalado."""
        import subprocess
        try:
            proc = subprocess.run(["node", "-e", script], capture_output=True,
                                  text=True, timeout=20)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        self.assertEqual(proc.returncode, 0, f"node fallo: {proc.stderr}")
        return proc.stdout.strip()

    def test_archive_esc_actually_escapes_every_dangerous_char(self):
        import json

        esc_js = self._extract_esc(self._archive_html())
        cases = ["&", "<", ">", '"', "'", self.HOSTILE]
        script = esc_js + "\nconsole.log(JSON.stringify(%s.map(esc)));" % json.dumps(cases)

        out = self._run_node(script)
        if out is None:
            self.skipTest("node no disponible en este entorno")

        escaped = json.loads(out)
        for original, result in zip(cases, escaped):
            self.assertNotEqual(original, result,
                                f"esc() dejo {original!r} sin escapar")
        # El payload hostil no puede conservar delimitadores de etiqueta.
        self.assertNotIn("<", escaped[-1])
        self.assertNotIn(">", escaped[-1])

    def test_archive_esc_handles_null_and_non_string(self):
        esc_js = self._extract_esc(self._archive_html())
        script = esc_js + "\nconsole.log(JSON.stringify([esc(null), esc(undefined), esc(0)]));"

        out = self._run_node(script)
        if out is None:
            self.skipTest("node no disponible en este entorno")

        import json
        self.assertEqual(json.loads(out), ["", "", "0"])

    def test_archive_escape_table_never_maps_a_char_to_itself(self):
        """Guardia sin node: detecta la regresion exacta que se produjo.

        Si alguien vuelve a escribir '&':'&' —por ejemplo porque las entidades
        se decodifican al copiar HTML renderizado— este test falla.
        """
        import re

        esc_js = self._extract_esc(self._archive_html())
        pairs = re.findall(r"""['"](.)['"]\s*:\s*['"]([^'"]+)['"]""", esc_js)
        self.assertGreaterEqual(len(pairs), 5, f"tabla de escape incompleta: {pairs}")
        for char, replacement in pairs:
            self.assertNotEqual(char, replacement,
                                f"esc() mapea {char!r} a si mismo: no escapa nada")

    def test_search_index_rejects_non_http_urls(self):
        """El indice se pintaba con la URL cruda, saltandose _safe_url()."""
        from src.archive import search_entries

        snap = {"date": "2026-08-24", "items": [
            {"title_es": "Con javascript:", "url": "javascript:alert(1)", "source": "S"},
            {"title_es": "Con data:", "url": "data:text/html,<script>alert(1)</script>", "source": "S"},
            {"title_es": "Normal", "url": "https://example.com/ok", "source": "S"},
        ]}
        by_title = {e["t"]: e["u"] for e in search_entries([snap])}

        self.assertEqual(by_title["Con javascript:"], "")
        self.assertEqual(by_title["Con data:"], "")
        self.assertEqual(by_title["Normal"], "https://example.com/ok")

    def test_templates_emit_no_invalid_escape_sequences(self):
        """`\\d` dentro de una cadena normal avisa hoy y sera error manana.

        Ademas Python se comia `\\u0300` antes de que llegara al JS, dejando
        caracteres combinantes invisibles en el HTML publicado.
        """
        import pathlib
        import warnings

        for name in ("render", "archive", "weekly", "main", "notify"):
            path = pathlib.Path("src") / f"{name}.py"
            if not path.exists():
                continue
            source = path.read_text(encoding="utf-8")
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                compile(source, str(path), "exec")
            bad = [w for w in caught if "escape sequence" in str(w.message)]
            self.assertEqual(bad, [], f"{path}: {[str(w.message) for w in bad]}")

    def test_unicode_range_reaches_javascript_unconsumed(self):
        """La clase de acentos debe llegar al JS como escape, no como literal.

        Python interpretaba \\uXXXX dentro de la plantilla y colaba caracteres
        combinantes invisibles en el HTML. Las cadenas esperadas se construyen
        por partes a proposito: escritas de un tiron, cualquier reescritura del
        fichero puede volver a colapsarlas y el test dejaria de probar nada.
        """
        backslash = chr(92)
        html = self._archive_html()

        self.assertIn(backslash + "u0300", html)
        self.assertIn(backslash + "u036f", html)
        # Y el caracter combinante crudo no debe aparecer.
        self.assertNotIn(chr(0x0300), html)


if __name__ == "__main__":
    unittest.main()
