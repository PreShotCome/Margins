import json
from pathlib import Path
from unittest.mock import patch
import unittest
import test_engine as fixture
from test_engine import Fake, T, notice, subscription
from margins.__main__ import cycle, verify, maintenance
from margins.core import *

class FlowTests(unittest.TestCase):
    setUp = fixture.EngineTests.setUp
    tearDown = fixture.EngineTests.tearDown
    # Integration cases share the fixture setup but not the parent tests.
    def test_cycle_real_storage_from_source_to_durable_outbox(self):
        settings = dict(self.settings, sending_enabled=False, publishing_enabled=False)
        provider = Fake([{'opportunitiesData':[notice()], 'totalRecords':1},
                         {'data':[subscription()],'has_more':False}])
        with patch('margins.__main__.API',return_value=provider),patch('margins.__main__.check'),patch('margins.__main__.ROOT',Path(self.tmp.name)),patch('margins.core.now',return_value=T):
            cycle(settings)
        self.assertEqual(self.db.execute('SELECT count(*) FROM outbox').fetchone()[0],1)
        self.assertTrue((Path(self.tmp.name)/'dist/index.html').exists())
        self.assertTrue((Path(self.tmp.name)/'backups').exists())
    def test_cycle_source_outage_never_calls_billing_or_email(self):
        provider = Fake([Blocked('SAM unavailable')])
        with patch('margins.__main__.API',return_value=provider),patch('margins.__main__.check'),patch('margins.__main__.ROOT',Path(self.tmp.name)):
            with self.assertRaises(Blocked): cycle(self.settings)
        self.assertEqual(len(provider.calls),1)
        self.assertIn('Checkout is paused',(Path(self.tmp.name)/'dist/index.html').read_text())
    def test_verify_rejects_wrong_price_and_link(self):
        settings = dict(self.settings,stripe_payment_link_id='plink_a',payment_link='https://buy.stripe.com/abc')
        price = {'active':True,'livemode':False,'currency':'usd','unit_amount':7900,'recurring':{'interval':'month','interval_count':1}}
        link = {'active':True,'livemode':False,'url':settings['payment_link']}
        lines = {'data':[{'price':{'id':'price_margins'},'quantity':1}],'has_more':False}
        with patch('margins.__main__.check'):
            verify(settings,self.db,Fake([price,link,lines]))
            with self.assertRaises(Blocked): verify(settings,self.db,Fake([dict(price,unit_amount=79000)]))
            with self.assertRaises(Blocked): verify(settings,self.db,Fake([price,dict(link,url='https://buy.stripe.com/other')]))

