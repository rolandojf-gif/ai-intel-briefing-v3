"""Capa X: espejos verificados + descubrimiento, filtro de reposts y reserva FxTwitter.

La capa estuvo apagada desde su primer dia (51 ediciones) porque los tres
espejos fijos estaban muertos. Estos tests fijan lo que la mantiene viva.
"""
import unittest
from unittest import mock

import src.fetch_x as fx


class FakeResp:
    def __init__(self, status=200, payload=None, text="", ctype="application/json"):
        self.status_code = status
        self._payload = payload
        self.text = text
        self.headers = {"content-type": ctype}

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(str(self.status_code))


class XLayerTests(unittest.TestCase):
    def setUp(self):
        fx._DISCOVERED = None
        fx._DEAD_MIRRORS.clear()
        fx._GOOD_MIRROR = ""
        fx._CACHE_LOADED = True
        fx._CACHE_DATA = {}
        patcher = mock.patch.dict("os.environ", {"X_CACHE_DISABLE": "1"}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(setattr, fx, "_DISCOVERED", None)
        self.addCleanup(fx._DEAD_MIRRORS.clear)
        self.addCleanup(setattr, fx, "_GOOD_MIRROR", "")

    # -- espejos ----------------------------------------------------------
    def test_dead_defaults_are_gone(self):
        joined = " ".join(fx.DEFAULT_X_RSS_MIRRORS)
        for dead in ("xcancel.com", "privacydev.net", "poast.org"):
            self.assertNotIn(dead, joined)
        self.assertGreaterEqual(len(fx.DEFAULT_X_RSS_MIRRORS), 4)

    def test_discovery_keeps_only_healthy_rss_hosts_ranked(self):
        payload = {"hosts": [
            {"domain": "b.example.org", "healthy": True, "rss": True, "points": 50},
            {"domain": "a.example.org", "healthy": True, "rss": True, "points": 90},
            {"domain": "norss.example.org", "healthy": True, "rss": False, "points": 99},
            {"domain": "sick.example.org", "healthy": False, "rss": True, "points": 99},
            {"domain": "abc.onion", "healthy": True, "rss": True, "points": 99},
            {"domain": "evil.example.org/path?x=1", "healthy": True, "rss": True, "points": 99},
        ]}
        with mock.patch.object(fx.requests, "get", return_value=FakeResp(payload=payload)):
            found = fx._discover_mirrors()
        self.assertEqual(found, ["https://a.example.org", "https://b.example.org"])

    def test_discovery_failure_falls_back_to_defaults(self):
        import requests
        with mock.patch.object(fx.requests, "get", side_effect=requests.ConnectionError("x")):
            mirrors = fx._rss_mirrors()
        self.assertEqual(mirrors, list(fx.DEFAULT_X_RSS_MIRRORS))

    def test_down_mirror_is_not_retried_and_good_one_goes_first(self):
        fx._DISCOVERED = []
        first, second = fx.DEFAULT_X_RSS_MIRRORS[:2]
        probes = []

        def probe(url):
            probes.append(url)
            return "down" if url.startswith(first) else "ok"

        item = {"title": "hola", "link": f"{second}/OpenAI/status/1", "image_url": ""}
        with mock.patch.object(fx, "_probe_rss", side_effect=probe), \
             mock.patch.object(fx, "fetch_rss", return_value=[dict(item)]):
            fx._fetch_from_candidates(["/OpenAI/rss"], limit=5)
            fx._fetch_from_candidates(["/karpathy/rss"], limit=5)
        self.assertIn(first, fx._DEAD_MIRRORS)
        self.assertEqual(sum(1 for u in probes if u.startswith(first)), 1)
        self.assertTrue(probes[-1].startswith(second))
        self.assertEqual(fx._rss_mirrors()[0], second)

    # -- contenido --------------------------------------------------------
    def test_reposts_and_replies_are_dropped_by_default(self):
        items = [{"title": "RT by @OpenAI: de otro"}, {"title": "R to @sama: respuesta"},
                 {"title": "Pinned: fijado"}, {"title": "Post propio"}]
        kept = fx._drop_reposts_and_replies([dict(i) for i in items], False, False)
        self.assertEqual([i["title"] for i in kept], ["fijado", "Post propio"])
        self.assertEqual(len(fx._drop_reposts_and_replies([dict(i) for i in items], True, True)), 4)

    def test_mirror_links_and_images_point_to_the_original(self):
        self.assertEqual(fx._to_x_link("http://nitter.mizuki.st/karpathy/status/2119114537442189652#m"),
                         "https://x.com/karpathy/status/2119114537442189652")
        self.assertEqual(fx._to_twimg("https://nitter.example.org/pic/media%2FGabc123.jpg"),
                         "https://pbs.twimg.com/media/Gabc123.jpg")
        self.assertEqual(fx._to_twimg("https://nitter.example.org/pic/orig/media%2FGabc123.jpg"),
                         "https://pbs.twimg.com/media/Gabc123.jpg")
        # Avatares, rutas cifradas o cualquier otra cosa: sin imagen antes que enlazar al espejo.
        self.assertEqual(fx._to_twimg("https://nitter.example.org/pic/profile_images%2F1%2Fa.jpg"), "")
        self.assertEqual(fx._to_twimg("https://nitter.example.org/pic/enc/abcdef"), "")
        self.assertEqual(fx._to_twimg("https://evil.example.org/x.png"), "")

    def test_fxtwitter_fallback_maps_and_filters(self):
        payload = {"code": 200, "results": [
            {"url": "https://x.com/otro/status/1", "text": "repost", "created_timestamp": 1794421033,
             "reposted_by": {"screen_name": "OpenAI"}},
            {"url": "https://x.com/OpenAI/status/2", "text": "hilo", "created_timestamp": 1794334002,
             "replying_to": {"screen_name": "OpenAI"}},
            {"url": "https://x.com/OpenAI/status/3", "text": "Introducing\n\nGPT-6 Cyber", "created_timestamp": 1793898553,
             "media": {"photos": [{"url": "https://pbs.twimg.com/media/Gx.jpg"}]}},
        ]}
        with mock.patch.object(fx.requests, "get", return_value=FakeResp(payload=payload)):
            items = fx._fetch_fxtwitter("OpenAI", 6, False, False)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["link"], "https://x.com/OpenAI/status/3")
        self.assertEqual(items[0]["title"], "Introducing GPT-6 Cyber")
        self.assertEqual(items[0]["published"], "2026-11-05T17:09:13+00:00")
        self.assertEqual(items[0]["image_url"], "https://pbs.twimg.com/media/Gx.jpg")

    def test_fxtwitter_rate_limit_is_a_miss_not_a_crash(self):
        with mock.patch.object(fx.requests, "get", return_value=FakeResp(status=404, payload={"code": 404, "results": []})):
            self.assertEqual(fx._fetch_fxtwitter("karpathy", 6, False, False), [])

    def test_user_fetch_uses_mirror_then_fxtwitter(self):
        own = {"title": "Post propio", "link": "https://x.com/OpenAI/status/9", "image_url": ""}
        with mock.patch.object(fx, "_fetch_from_candidates", return_value=[{"title": "RT by @OpenAI: x"}, dict(own)]) as cand, \
             mock.patch.object(fx, "_fetch_fxtwitter") as fxt:
            got = fx.fetch_x_user("OpenAI", limit=6)
        self.assertEqual(cand.call_args.args[0], ["/OpenAI/rss"])
        fxt.assert_not_called()
        self.assertEqual([i["title"] for i in got], ["Post propio"])

        with mock.patch.object(fx, "_fetch_from_candidates", return_value=[]), \
             mock.patch.object(fx, "_fetch_fxtwitter", return_value=[dict(own)]) as fxt, \
             mock.patch.object(fx, "_fetch_jina_profile_markdown") as jina:
            got = fx.fetch_x_user("OpenAI", limit=6)
        fxt.assert_called_once()
        jina.assert_not_called()
        self.assertEqual(len(got), 1)

    def test_og_image_is_not_requested_from_x(self):
        import src.fetch as fetch
        with mock.patch.object(fetch.requests, "get", side_effect=AssertionError("peticion a x.com")):
            self.assertEqual(fetch.fetch_og_image("https://x.com/OpenAI/status/3"), "")


class CoverTests(unittest.TestCase):
    def _svg(self, **item):
        import base64
        from src.render import item_fallback_image
        return base64.b64decode(item_fallback_image(item).split(",", 1)[1]).decode("utf-8")

    def test_cover_shows_theme_and_source_but_not_the_headline(self):
        svg = self._svg(title_es="Nvidia sube precios", title="Nvidia raises prices",
                        strategic_theme="compute_chips_dc", source="Reuters AI")
        self.assertIn("Compute &amp; chips", svg)
        self.assertIn("Reuters AI", svg)
        self.assertNotIn("Nvidia", svg)

    def test_every_theme_has_its_own_valid_cover(self):
        import xml.etree.ElementTree as ET
        from src.cover import THEME_STYLE
        seen = set()
        for theme in list(THEME_STYLE) + ["other", "", "tema_desconocido"]:
            svg = self._svg(title="t", strategic_theme=theme, source='Fuente & "Co" <x>')
            ET.fromstring(svg)
            self.assertLess(len(svg), 6000)
            seen.add(svg)
        self.assertGreaterEqual(len(seen), 7)

    def test_cover_is_stable_per_item_and_varies_between_items(self):
        a1 = self._svg(title="Noticia A", url="https://e.com/a", strategic_theme="agents_automation", source="S")
        a2 = self._svg(title="Noticia A", url="https://e.com/a", strategic_theme="agents_automation", source="S")
        b = self._svg(title="Noticia B", url="https://e.com/b", strategic_theme="agents_automation", source="S")
        self.assertEqual(a1, a2)
        self.assertNotEqual(a1, b)


if __name__ == "__main__":
    unittest.main()
