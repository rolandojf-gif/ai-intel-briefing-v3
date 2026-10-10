import json
from datetime import date, datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src import newtab_daily as daily


class NewtabDailyTests(unittest.TestCase):
    def test_calendar_does_not_reset_on_month_boundary(self):
        self.assertTrue(daily.gemini_day(date(2026, 10, 10)))
        self.assertFalse(daily.gemini_day(date(2026, 10, 11)))
        self.assertTrue(daily.gemini_day(date(2026, 10, 12)))
        for n in range(1, 50):
            d = daily.ANCHOR.fromordinal(daily.ANCHOR.toordinal() + n)
            self.assertNotEqual(daily.gemini_day(d), daily.gemini_day(d.fromordinal(d.toordinal()-1)))

    def test_rss_filters_duplicates_old_news_and_invalid_links(self):
        now = datetime(2026, 10, 11, 8, tzinfo=timezone.utc)
        base = {'title': 'OpenAI launches new Codex agent API', 'published': '2026-10-11T07:00:00+00:00', 'summary': 'New AI coding agent model API pricing available', 'source': 'OpenAI'}
        items = [
            {**base, 'link': 'https://openai.com/news/codex'},
            {**base, 'link': 'https://openai.com/news/codex?utm_source=copy'},
            {**base, 'link': 'https://openai.com/news/old', 'published': '2026-10-01T07:00:00+00:00'},
            {**base, 'link': 'javascript:alert(1)'},
            {**base, 'title': 'NVIDIA rolls out Blackwell AI GPU datacenter systems', 'link':'https://nvidia.com/news/gpu'},
        ]
        chosen = daily.select_new(items, date(2026,10,11), now=now, seen=(set(),set()))
        self.assertEqual(len(chosen), 2)
        self.assertTrue(all(i['layer']=='rss' and i['analysis_type']=='heuristic' for i in chosen))

    def test_repeated_from_previous_day_is_excluded(self):
        now = datetime(2026, 10, 11, 8, tzinfo=timezone.utc)
        item = {'title': 'Anthropic unveils new agent pricing and API', 'link': 'https://anthropic.com/x', 'published': '2026-10-11T07:00:00Z', 'summary': 'Claude agents API'}
        chosen = daily.select_new([item], date(2026,10,11), now=now, seen=({'https://anthropic.com/x'},set()))
        self.assertEqual(chosen, [])

    def test_rss_does_not_call_gemini_and_labels_previous_thesis(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)/'data'; newtab=Path(temp)/'newtab';data.mkdir()
            (data/'2026-10-10.json').write_text(json.dumps({'date':'2026-10-10','items':[{'title':'A'}],'briefing':{'thesis':'Análisis anterior'}}))
            item = {'title': 'New AI agent platform arrives with model API', 'link':'https://news.example/agent', 'published':'2026-10-11T06:00:00Z','source':'RSS'}
            with patch.object(daily,'DATA',data),patch.object(daily,'NEWTAB',newtab), patch.object(daily,'collect_rss',return_value=[item]),patch.object(daily,'select_new',return_value=[{**item,'layer':'rss'}]):
                daily.run(date(2026,10,11),mode='rss')
            output = json.loads((newtab/'latest.json').read_text())
            self.assertEqual(output['edition_type'],'rss')
            self.assertEqual(output['analysis_date'],'2026-10-10')
            self.assertEqual(output['briefing']['thesis'],'Análisis anterior')
            self.assertEqual(output['counts']['signal'],0)

    def test_zero_new_does_not_replace_latest(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp); old=path/'latest.json';old.write_text('{"date":"2026-10-10"}')
            with patch.object(daily,'NEWTAB',path),patch.object(daily,'collect_rss',return_value=[]),patch.object(daily,'select_new',return_value=[]):
                self.assertFalse(daily.publish_rss(date(2026,10,11)))
            self.assertEqual(old.read_text(),'{"date":"2026-10-10"}')


if __name__=='__main__': unittest.main()
