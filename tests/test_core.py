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

    # -- Integridad del gate: nada se publica sin haber sido juzgado ---------

    def _candidate(self, rid, score=80, title=None):
        return {
            "_rid": rid,
            "title": title or f"item {rid}",
            "summary": "",
            "source": "Fuente",
            "link": f"https://example.com/{rid}",
            "heuristic_score": score,
            "adjusted_score": score,
        }

    def test_unjudged_items_are_never_published(self):
        """La cola que no entra en el lote del LLM no puede llegar al radar.

        Publicarla afirmaba un filtrado inexistente: items del puesto 21-30
        aparecian en 'Contexto' con score 0 como si hubieran sido evaluados.
        """
        candidates = [self._candidate(i) for i in range(1, 6)]
        results = {
            "1": {"verdict": "signal", "relevance": 90, "so_what": "x", "power_shift": "", "theme": "other"},
            "2": {"verdict": "context", "relevance": 60, "so_what": "y", "power_shift": "", "theme": "other"},
            # 3, 4 y 5 nunca fueron juzgados
        }
        out = apply_llm_results(candidates, results)
        published = {it["_rid"] for it in out}

        self.assertEqual(published, {1, 2})
        self.assertTrue(all(it.get("llm_score") is not None for it in out))
        self.assertNotIn("unrated", [it.get("verdict") for it in out])

    def test_degraded_mode_still_publishes_when_llm_never_ran(self):
        """Sin ningun veredicto seguimos publicando, marcado como degradado.

        Distinto de 'el LLM juzgo y descarto': ahi el resultado correcto es cero.
        """
        candidates = [self._candidate(i) for i in range(1, 4)]
        out = apply_llm_results(candidates, {})

        self.assertEqual(len(out), 3)
        self.assertTrue(all(it.get("layer") == "unrated" for it in out))

    def test_power_shift_only_promotes_above_score_floor(self):
        """power_shift viene relleno en ~75% de items: sin umbral no filtra."""
        from src.main import POWER_SHIFT_FLOOR

        candidates = [self._candidate(1, score=95), self._candidate(2, score=5)]
        results = {
            "1": {"verdict": "context", "relevance": 88, "so_what": "a",
                  "power_shift": "A gana / B pierde", "theme": "other"},
            "2": {"verdict": "context", "relevance": 3, "so_what": "b",
                  "power_shift": "C gana / D pierde", "theme": "other"},
        }
        out = apply_llm_results(candidates, results)
        by_id = {it["_rid"]: it for it in out}

        self.assertEqual(by_id[1]["layer"], "signal")
        self.assertGreaterEqual(by_id[1]["final_score"], POWER_SHIFT_FLOOR)
        self.assertNotEqual(by_id[2]["layer"], "signal")

    def test_llm_batch_covers_whole_candidate_pool(self):
        """Si el lote es menor que el pool, se recrea la cola sin juzgar."""
        import inspect
        from src import main as main_mod

        self.assertIn("candidates[:LLM_BATCH_SIZE]", inspect.getsource(main_mod.generate_llm_data))
        self.assertIn("deduped[:LLM_BATCH_SIZE]", inspect.getsource(main_mod.main))

    # -- Mercado: un hueco honesto en vez de un precio inventado -------------

    def test_market_reports_missing_quotes_instead_of_inventing_them(self):
        import src.market as market

        original_quote = market._fetch_yahoo_quote
        original_crypto = market._fetch_crypto_bitcoin
        try:
            market._fetch_yahoo_quote = lambda symbol: None
            market._fetch_crypto_bitcoin = lambda: None
            data = market.get_market_overview()
        finally:
            market._fetch_yahoo_quote = original_quote
            market._fetch_crypto_bitcoin = original_crypto

        quotes = data["macro"] + data["companies"]
        self.assertTrue(quotes)
        self.assertTrue(all(q["available"] is False for q in quotes))
        self.assertTrue(all(q["price_str"] == "s/d" for q in quotes))
        self.assertTrue(all(q["change_str"] == "" for q in quotes))
        self.assertEqual(data["quotes_ok"], 0)

    def test_render_shows_gap_not_fake_number_for_missing_quotes(self):
        """La pagina muestra el hueco, nunca una cifra inventada."""
        from src.render import render_index

        market = {
            "macro": [{"label": "VIX", "price_str": "s/d", "change_str": "",
                       "positive": True, "available": False, "sparkline_svg": ""}],
            "companies": [{"name": "NVIDIA Corp.", "ticker": "NVDA", "exchange": "NASDAQ",
                           "price_str": "s/d", "change_str": "", "positive": True,
                           "available": False, "logo": ""}],
            "quotes_ok": 0,
            "quotes_total": 2,
        }
        html = render_index([], briefing={"thesis": "t"},
                            snapshot={"date": "2026-08-23"}, market=market)

        self.assertIn("s/d", html)
        # Ni porcentajes de relleno ni los antiguos precios codificados.
        self.assertNotIn("+0.00%", html)
        self.assertNotIn("128.50", html)
        self.assertNotIn("7691.25", html)

    # -- Imagen de respaldo: debe ser SVG valido ----------------------------

    def _fallback_svg(self, item):
        import base64
        from src.render import item_fallback_image
        uri = item_fallback_image(item)
        self.assertTrue(uri.startswith("data:image/svg+xml;base64,"))
        return base64.b64decode(uri.split(",", 1)[1]).decode("utf-8")

    def test_fallback_image_is_well_formed_for_every_theme(self):
        """Un & sin escapar invalidaba el SVG entero.

        Las etiquetas "COMPUTE & CHIPS" y "AGENTS & REASONING" llevaban un &
        literal: XML invalido, el navegador descartaba la imagen y mostraba el
        icono de rota en toda card sin imagen OpenGraph de esos dos temas.
        """
        import xml.etree.ElementTree as ET

        themes = ["compute_chips_dc", "agents_automation", "frontier_capability",
                  "china_stack", "model_economics", "other"]
        for theme in themes:
            svg = self._fallback_svg({"title_es": "Titular de prueba", "strategic_theme": theme})
            ET.fromstring(svg)  # lanza ParseError si el SVG no es valido

    def test_fallback_image_escapes_hostile_titles(self):
        import xml.etree.ElementTree as ET

        for title in ['Nvidia & AMD <suben> "precios"', "A" * 300, "", "Ñandú — 5 & 6"]:
            svg = self._fallback_svg({"title_es": title, "strategic_theme": "compute_chips_dc"})
            ET.fromstring(svg)
            self.assertNotIn("<suben>", svg)

    def test_fallback_title_wraps_instead_of_overflowing(self):
        """`width` en <text> no existe en SVG: hay que partir a mano."""
        from src.render import _wrap_svg_title

        lines = _wrap_svg_title("Nvidia sube más del 15% los precios de sus productos relacionados con IA")
        self.assertGreater(len(lines), 1)
        self.assertLessEqual(len(lines), 3)
        for line in lines:
            self.assertLessEqual(len(line), 34)

    # -- Filtro "Nuevo": primeras apariciones -------------------------------

    def test_new_filter_marks_first_time_items(self):
        from src.render import render_index

        items = [
            {"title_es": "Primera vez", "layer": "signal", "score": 90,
             "strategic_theme": "china_stack", "is_repeat": False},
            {"title_es": "Ya la vimos", "layer": "signal", "score": 80,
             "strategic_theme": "agents_automation", "is_repeat": True},
        ]
        html = render_index(items, briefing={"thesis": "t"},
                            snapshot={"date": "2026-08-23"}, market={})

        self.assertIn('data-filter="__new__"', html)
        self.assertEqual(html.count('data-new="1"'), 1)
        self.assertEqual(html.count('data-new="0"'), 1)
        self.assertIn("__new__", html)  # el JS debe saber filtrar por novedad

    def test_new_tab_hidden_when_it_would_not_discriminate(self):
        """Si todo es nuevo (o nada lo es), el filtro no informaria."""
        from src.render import render_index

        todos_nuevos = [
            {"title_es": f"Item {i}", "layer": "signal", "score": 90 - i,
             "strategic_theme": "china_stack", "is_repeat": False}
            for i in range(3)
        ]
        html = render_index(todos_nuevos, briefing={"thesis": "t"},
                            snapshot={"date": "2026-08-23"}, market={})
        self.assertNotIn('data-filter="__new__"', html)

    # -- Coherencia del prompt ----------------------------------------------

    def test_prompt_does_not_contradict_itself_on_severity(self):
        """SYSTEM, schema y cuerpo del prompt deben pedir lo mismo.

        Convivieron 'marcar algo irrelevante como signal es un fallo grave' con
        'prioriza categorizar como signal': el modelo tenia que desobedecer una.
        """
        import src.llm_rank as rank

        system = rank.SYSTEM.lower()
        verdict_desc = rank.RankOut.model_fields["verdict"].description.lower()

        self.assertNotIn("fallo grave", system)
        self.assertNotIn("severo", system)
        # El criterio de desempate debe existir y apuntar en una sola direccion.
        self.assertIn("ante la duda", verdict_desc)
        self.assertIn("noise", verdict_desc)


    # -- P0: Google News URL resolution -------------------------------------

    def test_google_news_url_detection_and_passthrough(self):
        from src.fetch import is_google_news_url, resolve_google_news_url

        self.assertTrue(is_google_news_url(
            "https://news.google.com/rss/articles/CBMiABC?oc=5"
        ))
        self.assertFalse(is_google_news_url("https://www.bloomberg.com/news/foo"))
        self.assertFalse(is_google_news_url(""))
        plain = "https://semiwiki.com/tsmc/story"
        self.assertEqual(resolve_google_news_url(plain), plain)

    def test_google_news_local_protobuf_decode(self):
        """Formato legado: el token lleva la URL del medio, sin red."""
        import base64
        from src.fetch import resolve_google_news_url, _GN_RESOLVE_CACHE

        dest = "https://www.reuters.com/technology/example-ai-story"
        payload = b"\x08\x13\x22" + bytes([len(dest)]) + dest.encode("latin1")
        token = base64.urlsafe_b64encode(payload).decode().rstrip("=")
        url = f"https://news.google.com/rss/articles/{token}?oc=5"
        _GN_RESOLVE_CACHE.clear()
        self.assertEqual(resolve_google_news_url(url), dest)

    def test_google_news_batchexecute_parser(self):
        from src.fetch import _parse_garturlres

        body = (
            ')]}\'\n\n[["wrb.fr","Fbv4je",'
            '"[\\"garturlres\\",\\"https://www.bloomberg.com/news/articles/2026-08-22/nvidia-hike\\",1]"'
            ',null,null,null,"generic"]]'
        )
        self.assertEqual(
            _parse_garturlres(body),
            "https://www.bloomberg.com/news/articles/2026-08-22/nvidia-hike",
        )
        self.assertEqual(_parse_garturlres("nope"), "")

    # -- P0: summary clip ---------------------------------------------------

    def test_summary_is_clipped_to_800_chars(self):
        from src.fetch import SUMMARY_MAX_CHARS, clip_text

        huge = "palabra " * 20000
        clipped = clip_text(huge)
        self.assertLessEqual(len(clipped), SUMMARY_MAX_CHARS)
        self.assertTrue(clipped.endswith("…"))
        self.assertEqual(clip_text("corto"), "corto")

    def test_snapshot_drops_raw_fields_and_clips_summary(self):
        from src.main import slim_item_for_snapshot

        item = {
            "title": "x",
            "summary": "y" * 5000,
            "raw_title": "raw",
            "raw_summary": "z" * 60000,
            "_rid": 7,
            "score": 90,
        }
        slim = slim_item_for_snapshot(item)
        self.assertNotIn("raw_title", slim)
        self.assertNotIn("raw_summary", slim)
        self.assertNotIn("_rid", slim)
        self.assertLessEqual(len(slim["summary"]), 800)
        self.assertEqual(slim["score"], 90)

    # -- P0: novelty hard-gate ----------------------------------------------

    def test_repeats_cannot_occupy_hero_or_top3_when_fresh_exists(self):
        from src.main import demote_repeats_from_lead

        items = [
            {"title": "repeat-high", "is_repeat": True, "score": 94},
            {"title": "repeat-mid", "is_repeat": True, "score": 87},
            {"title": "fresh-a", "is_repeat": False, "score": 86},
            {"title": "fresh-b", "is_repeat": False, "score": 71},
            {"title": "fresh-c", "is_repeat": False, "score": 67},
            {"title": "repeat-low", "is_repeat": True, "score": 64},
        ]
        out = demote_repeats_from_lead(items, lead_n=3)
        lead = [it["title"] for it in out[:3]]
        self.assertEqual(lead, ["fresh-a", "fresh-b", "fresh-c"])
        self.assertTrue(all(not it["is_repeat"] for it in out[:3]))
        self.assertEqual(out[3]["title"], "repeat-high")

    def test_repeats_fill_lead_only_when_fresh_runs_out(self):
        from src.main import demote_repeats_from_lead

        items = [
            {"title": "repeat-1", "is_repeat": True},
            {"title": "fresh-1", "is_repeat": False},
            {"title": "repeat-2", "is_repeat": True},
        ]
        out = demote_repeats_from_lead(items, lead_n=3)
        self.assertEqual(out[0]["title"], "fresh-1")
        self.assertFalse(out[0]["is_repeat"])
        self.assertEqual({out[1]["title"], out[2]["title"]}, {"repeat-1", "repeat-2"})

    def test_apply_llm_results_keeps_repeats_out_of_top3_signals(self):
        candidates = [
            {**self._candidate(1, score=94), "is_repeat": True, "title": "repeat lead"},
            {**self._candidate(2, score=80), "is_repeat": False, "title": "fresh A"},
            {**self._candidate(3, score=78), "is_repeat": False, "title": "fresh B"},
            {**self._candidate(4, score=76), "is_repeat": False, "title": "fresh C"},
        ]
        results = {
            str(i): {
                "verdict": "signal",
                "relevance": 90 - i,
                "so_what": "x",
                "power_shift": "",
                "theme": "other",
            }
            for i in range(1, 5)
        }
        out = apply_llm_results(candidates, results)
        signals = [it for it in out if it.get("layer") == "signal"]
        self.assertGreaterEqual(len(signals), 3)
        self.assertTrue(all(not it.get("is_repeat") for it in signals[:3]))
        self.assertEqual(signals[0]["title"], "fresh A")

    def test_render_hero_is_fresh_when_a_repeat_scores_higher(self):
        from src.render import render_index

        items = [
            {
                "title_es": "Repeat en portada",
                "layer": "signal",
                "score": 99,
                "is_repeat": True,
                "strategic_theme": "compute_chips_dc",
                "url": "https://semiwiki.com/repeat",
            },
            {
                "title_es": "Señal nueva de hoy",
                "layer": "signal",
                "score": 70,
                "is_repeat": False,
                "strategic_theme": "china_stack",
                "url": "https://www.bloomberg.com/news/new-story",
            },
            {
                "title_es": "Otra nueva",
                "layer": "signal",
                "score": 65,
                "is_repeat": False,
                "strategic_theme": "frontier_capability",
                "url": "https://openai.com/new",
            },
        ]
        html = render_index(items, briefing={"thesis": "t"},
                            snapshot={"date": "2026-08-23"}, market={})
        hero_pos = html.find('class="hero"')
        self.assertGreater(hero_pos, 0)
        # El titular fresco tiene que aparecer en el hero, no el repeat.
        fresh_pos = html.find("Señal nueva de hoy")
        repeat_pos = html.find("Repeat en portada")
        self.assertGreater(fresh_pos, 0)
        self.assertGreater(repeat_pos, 0)
        self.assertLess(fresh_pos, repeat_pos)
        self.assertLess(abs(fresh_pos - hero_pos), abs(repeat_pos - hero_pos))


if __name__ == "__main__":
    unittest.main()

