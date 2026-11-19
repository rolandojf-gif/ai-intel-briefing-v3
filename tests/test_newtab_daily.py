import json
from datetime import date, datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src import newtab_daily as daily


class NewtabDailyTests(unittest.TestCase):
    def test_gemini_runs_every_day_by_default(self):
        import os
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('GEMINI_ALTERNATE', None)
            for n in range(0, 10):
                self.assertTrue(daily.gemini_day(date(2026, 11, 16 + n)))

    @patch.dict('os.environ', {'GEMINI_ALTERNATE': '1'})
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
            with patch.object(daily,'DATA',data),patch.object(daily,'NEWTAB',newtab), patch.object(daily,'collect_rss',return_value=[item]),patch.object(daily,'select_new',return_value=[{**item,'layer':'rss'}]),patch.object(daily,'add_images',side_effect=lambda items: items):
                daily.run(date(2026,10,11),mode='rss')
            output = json.loads((newtab/'latest.json').read_text())
            self.assertEqual(output['edition_type'],'rss')
            self.assertEqual(output['analysis_date'],'2026-10-10')
            self.assertEqual(output['briefing']['thesis'],'Análisis anterior')
            self.assertEqual(output['counts']['signal'],0)

    def test_publish_records_utc_generation_timestamp(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            with patch.object(daily, 'NEWTAB', path):
                daily.publish({'date': '2026-10-11', 'edition_type': 'rss', 'items': []})
            stored = json.loads((path / 'latest.json').read_text(encoding='utf-8'))
            stamp = datetime.fromisoformat(stored['generated_at'])
            self.assertEqual(stamp.utcoffset().total_seconds(), 0)
            self.assertEqual(stored['date'], '2026-10-11')

    def test_zero_new_does_not_replace_latest(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp); old=path/'latest.json';old.write_text('{"date":"2026-10-10"}')
            with patch.object(daily,'NEWTAB',path),patch.object(daily,'collect_rss',return_value=[]),patch.object(daily,'select_new',return_value=[]):
                self.assertFalse(daily.publish_rss(date(2026,10,11)))
            self.assertEqual(old.read_text(),'{"date":"2026-10-10"}')


if __name__=='__main__': unittest.main()


class SecondScheduledAttemptTests(unittest.TestCase):
    def test_second_attempt_skips_when_the_edition_is_out(self):
        import os
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp) / 'data'; newtab = Path(temp) / 'newtab'; data.mkdir(); newtab.mkdir()
            day = date(2026, 10, 12)  # dia de Gemini (ancla 10-oct, alterno)
            with patch.object(daily, 'DATA', data), patch.object(daily, 'NEWTAB', newtab):
                self.assertFalse(daily.already_published(day, True))
                (data / '2026-10-12.json').write_text(json.dumps({'degraded': True, 'items': [{'t': 1}]}))
                self.assertFalse(daily.already_published(day, True))     # degradado: se reintenta
                (data / '2026-10-12.json').write_text(json.dumps({'degraded': False, 'items': [{'t': 1}]}))
                self.assertTrue(daily.already_published(day, True))
                self.assertFalse(daily.already_published(date(2026, 10, 13), False))
                (newtab / '2026-10-13.json').write_text('{}')
                self.assertTrue(daily.already_published(date(2026, 10, 13), False))
                with patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'schedule'}), \
                     patch('src.main.main', side_effect=AssertionError('no debe regenerar')):
                    daily.run(day)   # ya publicada: no llama a Gemini


class NetlifySchedulerTests(unittest.TestCase):
    def test_runs_launched_by_netlify_skip_when_edition_is_out(self):
        import os
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp) / 'data'; newtab = Path(temp) / 'newtab'; data.mkdir(); newtab.mkdir()
            day = date(2026, 11, 19)
            (data / '2026-11-19.json').write_text(json.dumps({'degraded': False, 'items': [{'t': 1}]}))
            env = {'GITHUB_EVENT_NAME': 'workflow_dispatch', 'FROM_SCHEDULER': '1', 'FORCE_GEMINI': '1'}
            with patch.object(daily, 'DATA', data), patch.object(daily, 'NEWTAB', newtab), \
                 patch.dict(os.environ, env), patch('src.main.main', side_effect=AssertionError('no debe regenerar')):
                daily.run(day)
