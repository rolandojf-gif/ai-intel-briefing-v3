import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from src.newtab_market import publish_market, refresh_market


class MarketPublisherTests(unittest.TestCase):
    def test_publishes_only_valid_market_fields_with_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'market.json'
            overview = {
                'macro': [{'label':'Bitcoin','available':True,'price_str':'82,752.42 US$',
                           'change_str':'+0.25%','positive':True,
                           'sparkline_points':[1,2,3], 'sparkline_svg':'<script>bad</script>'}],
                'companies': [{'name':'NVIDIA','ticker':'NVDA','exchange':'NASDAQ',
                               'logo':'https://example.com/logo','available':True,
                               'price_str':'229.28 US$','change_str':'-0.52%',
                               'positive':False,'sparkline_points':[10,9,8]}],
            }
            self.assertTrue(publish_market(overview, dest, datetime(2026,10,11,8,tzinfo=timezone.utc)))
            published=json.loads(dest.read_text())
            self.assertEqual(published['quotes_ok'],2)
            self.assertEqual(published['generated_at'],'2026-10-11T08:00:00+00:00')
            self.assertEqual(published['companies'][0]['sparkline_points'],[10.0,9.0,8.0])
            self.assertNotIn('sparkline_svg',dest.read_text())

    def test_retains_previous_on_complete_outage(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'market.json'
            dest.write_text('{"previous":true}')
            self.assertFalse(publish_market({'macro':[{'available':False}], 'companies':[]},dest))
            self.assertEqual(dest.read_text(),'{"previous":true}')
            self.assertFalse(publish_market(None,dest))
            self.assertEqual(dest.read_text(),'{"previous":true}')

    def test_refresh_calls_market_provider_once(self):
        with patch('src.market.get_market_overview',return_value={'macro':[],'companies':[]}) as fetch, patch('src.newtab_market.publish_market',return_value=False) as publish:
            self.assertFalse(refresh_market())
            fetch.assert_called_once()
            publish.assert_called_once()
