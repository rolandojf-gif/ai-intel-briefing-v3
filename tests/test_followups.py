import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from src.followups import excerpt, followups, with_open_stories
from src.render import render_index


def snapshot(day, state, items=()):
    return {"date": day, "memory": {"followups": state}, "items": list(items)}


def signal(rid, text, watch="", url=None):
    return {"_rid": rid, "title": text, "title_es": text, "title_en": text, "watch_next": watch,
            "url": url or f"https://example.org/{rid}", "evidence_kind": "confirmed",
            "source": "Fuente", "evidence": {"quote": text}}


def decision(origin, number, quote, correction=False):
    return {"follow_up": {"quote": quote, "origin": origin, "number": number, "correction": correction}}


class FollowUpTests(unittest.TestCase):
    def test_apple_and_market_reaction_same_edition(self):
        items = json.loads(Path("docs/data/2026-11-20.json").read_text())["items"]
        a, b = [next(i for i in items if i["source"] == name).copy() for name in ("TechCrunch AI", "Bloomberg Tech")]
        for rid, (it, kind) in enumerate(((a, "speculation"), (b, "reported")), 1):
            it.update(_rid=rid, evidence_kind=kind, evidence={"quote": it["title"]})
        link = decision("batch", 1, a["title"])
        state = followups("2026-11-20", [], [a,b], {2:link}, [])
        update, = state["updates"]
        self.assertEqual((update["status"], update["before"]["url"], update["after"]["url"]),
                         ("development", a["url"], b["url"]))
        self.assertEqual(update["before"]["date"], update["after"]["date"])
        self.assertIn(a["url"], [x["url"] for x in state["open"]])
        for bad in (decision("batch", 99, a["title"]), decision("batch", 1, "An invented quote"), {}):
            self.assertFalse(followups("2026-11-20", [], [a,b], {2:bad}, [])["updates"])

    def test_repeated_update_does_not_acquire_a_new_date(self):
        origin = signal(1, "A lab plans to publish its figures")
        initial = snapshot("2026-11-18", {}, [origin])
        reaction = signal(2, "The regulator requests audited figures")
        refs = [excerpt(origin)]
        decisions = {2: decision("history", 1, origin["title"])}
        day = followups("2026-11-19", [initial], [reaction], decisions, refs)
        reprint = dict(reaction, summary="Updated newsletter navigation")
        history = [initial, snapshot("2026-11-19", day, [reaction])]
        next_day = followups("2026-11-20", history, [reprint], decisions, refs)
        self.assertEqual(next_day["updates"], day["updates"])

    def test_hito_persists_across_silence_and_closes_only_once(self):
        milestone = "OpenAI publishes audited adoption figures"
        origin = signal(1, "OpenAI considers releasing adoption numbers", milestone)
        opened = followups("2026-11-18", [], [origin], {}, [])
        first = snapshot("2026-11-18", opened, [origin])
        quiet = followups("2026-11-19", [first], [], {}, [])
        history = [first, snapshot("2026-11-19", quiet)]
        self.assertIn(excerpt(origin), with_open_stories(["Other headline"], history, []))
        actual = signal(5, milestone)
        closed = followups("2026-11-20", history, [actual], {}, [])
        self.assertEqual(closed["updates"][0]["status"], "confirmed")
        self.assertFalse(closed["open"])
        reaction = signal(6, "Analysts welcome the adoption report")
        later = followups("2026-11-21", history+[snapshot("2026-11-20", closed)], [reaction],
                          {"6": decision("history", 1, origin["title"])}, [excerpt(origin)])
        self.assertFalse(later["updates"][0]["before"]["watch"])
        self.assertFalse(later["open"])

    def test_only_documented_deadlines_expire_once(self):
        watch = "OpenAI publishes a report by 2026-11-19"
        origin = signal(1, "OpenAI plans to issue its report by 2026-11-19", watch)
        opened = followups("2026-11-18", [], [origin], {}, [])
        history = [snapshot("2026-11-18", opened)]
        self.assertFalse(followups("2026-11-19", history, [], {}, [])["updates"])
        expired = followups("2026-11-20", history, [], {}, [])
        self.assertEqual(expired["updates"][0]["status"], "expired")
        self.assertIsNone(expired["updates"][0]["after"])
        later = followups("2026-11-21", [snapshot("2026-11-20", expired)], [], {}, [])
        self.assertEqual(later["updates"], expired["updates"])
        origin["evidence"]["quote"] = origin["title"] = "OpenAI considers an unspecified deadline"
        opened = followups("2026-11-18", [], [origin], {}, [])
        self.assertFalse(opened["open"][0]["due"])

    def test_correction_requires_changed_source_and_original_reference(self):
        old = signal(1, "The company published a margin of 24%")
        first = snapshot("2026-11-18", {}, [old])
        new = signal(2, "Correction: our operating margin was 14%", url=old["url"])
        response = {2:decision("history", 1, old["title"], correction=True)}
        change = followups("2026-11-20", [first], [new], response, [excerpt(old)])
        self.assertEqual(change["updates"][0]["status"], "correction")
        copy = dict(old, _rid=2)
        self.assertFalse(followups("2026-11-20", [first], [copy], response, [excerpt(old)])["updates"])

    def test_renderer_safety_limit_archive_and_visit_lifecycle(self):
        card = {"url":"javascript:alert(1)", "es":"<img onerror=alert()>", "en":"Before", "watch":"hito"}
        update = {"date":"2026-11-20", "status":"development", "before":card, "after":card}
        day = snapshot("2026-11-20", {"updates":[update]*4})
        html = render_index([], snapshot=day, market={})
        self.assertNotIn("javascript:alert(1)", html)
        self.assertNotIn("<img onerror", html)
        self.assertEqual(html.count('data-updated="'), 3)
        self.assertNotIn('id="visit-changes"', render_index([], snapshot=day, archive={"prev":"2026-11-19"}, market={}))
        if not shutil.which("node"):
            self.skipTest("node unavailable")
        script = re.search(r"// La visita.*?(\(function\(\)\{.*?\}\)\(\);)",html,re.S).group(1)
        js = """const assert=require('node:assert/strict');let value=null, panel;
            const localStorage={getItem:()=>value,setItem:(k,v)=>{value=v}};
            const document={getElementById:()=>panel};
            function visit(day){const row={dataset:{updated:'2026-11-20'},hidden:true};
              panel={hidden:true,dataset:{edition:day},querySelectorAll:()=>[row]};""" + script + """
              return !panel.hidden && !row.hidden;}
            assert.equal(visit('2026-11-18'),false); assert.equal(visit('2026-11-20'),true);
            assert.equal(visit('2026-11-20'),true); assert.equal(visit('2026-11-19'),false);
            assert.equal(visit('2026-11-21'),false);
            localStorage.getItem=()=>{throw Error()};assert.equal(visit('2026-11-22'),false);"""
        subprocess.run(["node", "-e", js], check=True, capture_output=True)

    def test_visit_comparison_keeps_long_social_posts_scannable_in_both_languages(self):
        day = json.loads(Path("docs/data/2026-11-25.json").read_text())
        before = next(u["before"] for u in day["memory"]["followups"]["updates"]
                      if u["before"]["source"] == "X @GoogleDeepMind")
        html = render_index(day["items"], briefing=day["briefing"], snapshot=day, market={})
        panel = html.split('id="visit-changes"', 1)[1].split("</section>", 1)[0]
        self.assertIn('class="vc-list"', panel)
        link = re.search(r'href="' + re.escape(before["url"]) + r'"[^>]*>(.*?)</a>', panel).group(1)
        titles = re.findall(r'<span class="l-e[sn]"[^>]*>([^<]+)</span>', link)
        self.assertEqual(len(titles), 2)
        for title in titles:
            self.assertLessEqual(len(title), 140)
        self.assertIn("Las computadoras cuánticas", titles[0])
        self.assertIn("Quantum computers", titles[1])
