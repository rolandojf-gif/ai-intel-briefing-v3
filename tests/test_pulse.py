"""Indicadores propios: pulso de la carrera, quién la mueve y banda de mercados."""
import unittest

from src.pulse import movers, pulse_block, pulse_of


def sig(score, *ents):
    return {"layer": "signal", "final_score": score, "entities": list(ents)}


class PulseTests(unittest.TestCase):
    def test_pulse_scales_with_number_and_strength_of_signals(self):
        self.assertEqual(pulse_of([]), 0)
        self.assertEqual(pulse_of([sig(60)]), 5)
        self.assertEqual(pulse_of([sig(100)] * 12), 100)
        self.assertEqual(pulse_of([sig(100)] * 20), 100)
        # contexto y sin juzgar no cuentan
        self.assertEqual(pulse_of([{"layer": "context", "final_score": 90}, {"layer": "unrated", "final_score": 90}]), 0)

    def test_block_ignores_degraded_days_and_ranks_today(self):
        hist = [{"date": "d1", "items": [sig(80)] * 2}, {"date": "d2", "degraded": True, "items": [sig(99)] * 12},
                {"date": "d3", "items": [sig(80)] * 9}]
        b = pulse_block(hist, [sig(80)] * 6, "hoy")
        self.assertEqual([p["date"] for p in b["series"]], ["d1", "d3", "hoy"])
        self.assertEqual(b["value"], 40)
        self.assertEqual(b["hotter_than"], 50)
        self.assertEqual(b["editions"], 2)
        self.assertIsNone(pulse_block([], [sig(80)], "hoy")["hotter_than"])

    def test_movers_rank_by_weight_and_show_trend(self):
        hist = ([{"items": [sig(90, "Google"), sig(50, "OpenAI")]}] * 5      # ventana anterior
                + [{"items": [sig(90, "NVIDIA"), sig(90, "OpenAI")]}] * 4)   # ventana reciente
        m = movers(hist, [sig(90, "NVIDIA", "NVIDIA"), sig(80, "Anthropic")])
        names = [x["entity"] for x in m]
        self.assertEqual(names[0], "NVIDIA")
        self.assertEqual(m[0]["share"], 100)
        by = {x["entity"]: x["trend"] for x in m}
        self.assertEqual(by["NVIDIA"], "new")
        self.assertEqual(by["OpenAI"], "up")
        self.assertNotIn("Google", by)
        self.assertEqual(movers([], []), [])


class TickerTests(unittest.TestCase):
    def test_brent_and_apple_are_tracked(self):
        import inspect
        import src.market as market
        src = inspect.getsource(market.get_market_overview)
        self.assertIn('"BZ=F"', src)
        self.assertIn('"AAPL"', src)
        self.assertIn('"ANT"', src)

    def test_band_rotates_with_selected_companies_and_renders_indicators(self):
        from src.render import render_index
        q = {"available": True, "price_str": "1.00", "change_str": "+1%", "positive": True, "sparkline_svg": ""}
        market = {"macro": [{**q, "label": "Brent"}],
                  "companies": [{**q, "name": n, "ticker": t} for n, t in
                                (("NVIDIA Corp.", "NVDA"), ("Amazon.com Inc.", "AMZN"), ("Microsoft Corp.", "MSFT"),
                                 ("Apple Inc.", "AAPL"), ("Anthropic (ANT)", "ANT"), ("TSMC Ltd.", "TSM"))]}
        items = [{"title_es": "A", "layer": "signal", "score": 90, "url": "https://e.com/a"}]
        snap = {"date": "2026-11-15", "pulse": {"value": 67, "hotter_than": 80, "editions": 20,
                                                "series": [{"date": "d", "value": 30}, {"date": "h", "value": 67}]},
                "movers": [{"entity": "NVIDIA", "share": 100, "trend": "up"}]}
        html = render_index(items, briefing={"thesis": "t"}, snapshot=snap, market=market)
        band = html.split('class="ticker-track"')[1].split("</section>")[0]
        for label in ("Brent", "NVIDIA", "Amazon", "Microsoft", "Apple", "Anthropic (ANT)"):
            self.assertEqual(band.count(f'<span class="tq-n">{label}</span>'), 2, label)   # dos copias: bucle sin corte
        self.assertNotIn("TSMC", band)
        self.assertIn('aria-hidden="true"', band)
        self.assertIn("prefers-reduced-motion", html)
        self.assertIn('<strong>67</strong>', html)
        self.assertIn("Hotter than 80% of the last 20 editions", html)
        self.assertNotIn('class="movers"', html)

    def test_no_pulse_block_without_data(self):
        from src.render import render_index
        html = render_index([{"title_es": "A", "layer": "signal", "score": 90, "url": "https://e.com/a"}],
                            briefing={"thesis": "t"}, snapshot={"date": "2026-11-15"}, market={})
        self.assertNotIn('class="pulse"', html)
        self.assertNotIn('class="movers"', html)


if __name__ == "__main__":
    unittest.main()


class ActivityFromPulseTests(unittest.TestCase):
    def test_status_follows_the_pulse_percentile(self):
        from src.pulse import activity_from_pulse
        fb = ("ALERTA", "alert")
        mk = lambda pct, v=60, n=20: {"value": v, "hotter_than": pct, "editions": n}
        self.assertEqual(activity_from_pulse(mk(90), fb), ("ALERTA", "alert"))
        self.assertEqual(activity_from_pulse(mk(41), fb), ("ACTIVO", "active"))
        self.assertEqual(activity_from_pulse(mk(10), fb), ("TRANQUILO", "quiet"))
        self.assertEqual(activity_from_pulse(mk(50, v=0), fb), ("SIN SEÑAL", "quiet"))

    def test_without_enough_history_keeps_the_old_rule(self):
        from src.pulse import activity_from_pulse
        fb = ("ACTIVO", "active")
        self.assertEqual(activity_from_pulse({"value": 80, "hotter_than": 99, "editions": 3}, fb), fb)
        self.assertEqual(activity_from_pulse({}, fb), fb)
