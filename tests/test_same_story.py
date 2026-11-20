"""Un mismo suceso contado por muchos medios debe ser UNA card.

El 2026-11-14 la caida de Jensen Huang lleno la portada: nueve articulos
distintos a los que el LLM puso el mismo titular y el mismo analisis, letra por
letra. El dedup de ingest no los unia porque compara titulares originales.
"""
import unittest

from src.main import apply_llm_results, merge_same_story, same_story

H = "Jensen Huang destituido como CEO de Nvidia; se le acusa de manipular la escasez de GPUs."
W = "La destitución del CEO de Nvidia introduce una incertidumbre extrema en el suministro de cómputo."


def cand(rid, title, source, score=70):
    return {"_rid": rid, "title": title, "source": source, "url": f"https://example.com/{rid}",
            "score": score, "heuristic_score": score, "adjusted_score": score}


def verdict(headline, so_what="consecuencia distinta de cada item, suficientemente larga", **kw):
    return {"relevance": 90, "verdict": "signal", "headline_es": headline, "so_what": so_what,
            "theme": "compute_chips_dc", **kw}


class SameStoryTests(unittest.TestCase):
    def test_identical_llm_headline_collapses_into_one_card(self):
        cands = [
            cand(1, "Nvidia allegedly engineered scarcity", "Hacker News", 80),
            cand(2, "The End of Jensen", "Stratechery"),
            cand(3, "Jensen Out, MATCH Act In?", "ChinaTalk"),
            cand(4, "Musk says Nvidia will lose critical deals", "Reuters AI"),
            cand(5, "Introducing Gemini 4 Hydrogen", "DeepMind Blog"),
        ]
        results = {str(i): verdict(H, W) for i in (1, 2, 3, 4)}
        results["5"] = verdict("Google DeepMind presenta Gemini 4 Hydrogen.", "Nuevo modelo frontera de Google, salto de capacidad.")
        final = apply_llm_results(cands, results)

        titles = [it["title_es"] for it in final]
        self.assertEqual(titles.count(H), 1)
        self.assertEqual(len(final), 2)
        lead = next(it for it in final if it["title_es"] == H)
        self.assertEqual(lead["source"], "Hacker News")
        self.assertEqual(sorted(lead["other_sources"]), ["ChinaTalk", "Reuters AI", "Stratechery"])
        self.assertEqual({r["url"] for r in lead["related"]},
                         {"https://example.com/2", "https://example.com/3", "https://example.com/4"})

    def test_duplicates_do_not_eat_signal_slots(self):
        """Nueve copias ocupaban 9 de los 12 huecos y dejaban fuera señales reales."""
        from src.main import MAX_SIGNALS
        n_dupes = MAX_SIGNALS + 3
        cands = [cand(i, f"Jensen story {i}", f"Medio {i}", 90) for i in range(1, n_dupes + 1)]
        cands += [cand(100 + i, f"Otra noticia {i}", f"Otro {i}", 50) for i in range(5)]
        results = {str(i): verdict(H, W) for i in range(1, n_dupes + 1)}
        temas = ["chips de Huawei", "precios de la API de Claude", "agentes de programación autónomos",
                 "centros de datos en Texas", "modelo abierto de Mistral"]
        for i, tema in enumerate(temas):
            results[str(100 + i)] = verdict(f"Novedad relevante sobre {tema}", f"Consecuencia estratégica propia y distinta sobre {tema}.")
        final = apply_llm_results(cands, results)
        self.assertEqual(len(final), 6)
        self.assertEqual(sum(1 for it in final if it["title_es"] == H), 1)

    def test_llm_same_story_as_merges_even_with_different_headlines(self):
        a, b = cand(1, "A", "Reuters AI", 80), cand(2, "B", "Bloomberg Tech")
        a.update(llm_score=90, verdict="signal", title_es="Nvidia destituye a su CEO", so_what="x" * 50, _same_as=0)
        b.update(llm_score=85, verdict="signal", title_es="El consejo de Nvidia cesa a Huang tras el escándalo", so_what="y" * 50, _same_as=1)
        self.assertTrue(same_story(a, b))
        self.assertEqual(merge_same_story([a, b]), 1)
        self.assertEqual(b["verdict"], "duplicate")
        self.assertEqual(a["other_sources"], ["Bloomberg Tech"])

    def test_distinct_developments_stay_separate(self):
        a, b, c = cand(1, "A", "S1"), cand(2, "B", "S2"), cand(3, "C", "S3")
        a.update(llm_score=90, verdict="signal", title_es="Jensen Huang destituido como CEO de Nvidia", so_what="Crisis de liderazgo en el mayor proveedor de cómputo.")
        b.update(llm_score=85, verdict="signal", title_es="Musk y 100.000 firmantes piden restituir a Huang", so_what="La presión de clientes clave puede revertir la decisión del consejo.")
        c.update(llm_score=80, verdict="signal", title_es="OpenAI lanza ChatGPT Wallet para pagos de agentes", so_what="Los agentes pasan de recomendar a ejecutar compras.")
        self.assertEqual(merge_same_story([a, b, c]), 0)

    def test_noise_and_unrated_are_never_merged(self):
        a, b = cand(1, "A", "S1"), cand(2, "B", "S2")
        a.update(llm_score=90, verdict="signal", title_es=H, so_what=W)
        b.update(llm_score=10, verdict="noise", title_es=H, so_what=W)
        self.assertEqual(merge_same_story([a, b]), 0)
        self.assertEqual(b["verdict"], "noise")

    def test_card_lists_the_other_outlets_with_safe_links(self):
        from src.render import render_index
        item = {"title_es": H, "title": "x", "layer": "signal", "score": 90, "source": "Reuters AI",
                "url": "https://example.com/1",
                "related": [{"source": "Bloomberg Tech", "url": "https://example.com/2"},
                            {"source": "Malo", "url": "javascript:alert(1)"}],
                "other_sources": ["Bloomberg Tech", "Stratechery"]}
        html = render_index([item], briefing={"thesis": "t"}, snapshot={"date": "2026-11-14"}, market={})
        self.assertIn("También en:", html)
        self.assertIn('<a href="https://example.com/2" target="_blank" rel="noopener noreferrer">Bloomberg Tech</a>', html)
        self.assertIn("<span>Stratechery</span>", html)
        self.assertNotIn("javascript:alert", html)
        # Una vez en la portada y otra en su card de la rejilla (visible con filtro).
        self.assertEqual(html.count(">Bloomberg Tech<"), 2)

    def test_schema_and_prompt_ask_for_item_specific_headlines(self):
        import inspect
        import src.llm_rank as llm
        self.assertIn("same_story_as", llm.RankOut.model_fields)
        self.assertEqual(llm.RankOut.model_fields["same_story_as"].default, 0)
        self.assertIn("VARIOS ITEMS SOBRE LO MISMO", inspect.getsource(llm.rank_batch))


if __name__ == "__main__":
    unittest.main()


class EntityMergeTests(unittest.TestCase):
    def _it(self, rid, title_es, ents, theme="frontier_capability", title_en=""):
        return {"_rid": rid, "llm_score": 90, "verdict": "signal", "title_es": title_es, "title_en": title_en,
                "so_what": f"analisis distinto numero {rid} " * 3, "entities": ents, "strategic_theme": theme}

    def test_lab_blog_and_its_x_posts_are_one_story(self):
        """2026-11-16: el blog de OpenAI y los posts de @OpenAI y @gdb salian como 3 cards."""
        a = self._it(1, "OpenAI publica sobre una definición reticular del Modelo Estándar con GPT-6 Astra", ["OpenAI", "GPT-6 Astra"])
        b = self._it(2, "Físico colabora con GPT-6 Astra para definir el Modelo Estándar en una retícula", ["OpenAI", "Nathaniel Craig", "GPT-6 Astra"])
        c = self._it(3, "GPT-6 Astra utilizado en física teórica para definir el Modelo Estándar reticular", ["OpenAI", "GPT-6 Astra"])
        for x in (a, b, c):
            x["title_es"] = x["title_es"].replace("Modelo Estándar", "Modelo Estándar lattice")
        self.assertEqual(merge_same_story([a, b, c]), 2)

    def test_sharing_only_a_big_lab_or_a_loose_word_is_not_enough(self):
        a = self._it(1, "OpenAI lanza ChatGPT Wallet para pagos de agentes", ["OpenAI", "ChatGPT Wallet"])
        b = self._it(2, "OpenAI lanza Codex Cloud para agentes de programación", ["OpenAI", "Codex Cloud"])
        self.assertFalse(same_story(a, b))
        c = self._it(3, "Presentación de Gemini 3.6 Flash y Flash-Lite", ["Google", "flash"])
        d = self._it(4, "Presentación del uso del ordenador en Gemini Flash", ["Google", "flash"])
        self.assertFalse(same_story(c, d))

    def test_same_name_but_different_theme_stays_apart(self):
        a = self._it(1, "Gran modelo de lenguaje razona con grafos de tamaño", ["large language models"])
        b = self._it(2, "Gran modelo de lenguaje y el tamaño de su huella ecológica", ["large language models"], theme="compute_chips_dc")
        self.assertFalse(same_story(a, b))

class EvidenceFallbackTests(unittest.TestCase):
    def test_unlinked_syndicated_report_merges_with_source_attribution(self):
        title = "Google launches Gemini 4 Neon"
        a = dict(source="Reuters", title=title + " - Reuters", summary=title, evidence_kind="reported")
        b = dict(source="AP", title=title + " - AP", summary="", evidence_kind="reported")
        self.assertTrue(same_story(a, b))

    def test_shared_editorial_headline_preserves_material_developments(self):
        title = "Google launches Gemini 4 Neon"
        a = dict(title=title, title_es="Google presenta Neon", evidence_kind="reported")
        for update in ("Google cuts Gemini 4 Neon prices", "Independent tests show a 12% regression"):
            with self.subTest(update=update):
                self.assertFalse(same_story(a, dict(a, title=update)))
                self.assertFalse(same_story(a, dict(a, summary=update)))
