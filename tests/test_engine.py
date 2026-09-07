import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from margins.core import *
from margins.site import render

T = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)

def notice(**extra):
    return dict({'noticeId': 'abc123', 'title': 'Office cleaning', 'active': 'Yes',
        'naicsCode': '561720', 'type': 'Solicitation', 'postedDate': '2026-09-01',
        'responseDeadLine': '2026-09-20T17:00:00-07:00',
        'placeOfPerformance': {'state': {'code': 'WA'}}}, **extra)

def subscription(**extra):
    return dict({'id': 'sub_1', 'status': 'active', 'livemode': False,
        'customer': {'email': 'test@example.com'},
        'latest_invoice': {'paid': True, 'status': 'paid', 'amount_paid': 7900},
        'items': {'data': [{'price': {'id': 'price_margins'}}]}}, **extra)

class Fake:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = {'data_dir': self.tmp.name, 'stripe_price_id': 'price_margins', 'live_mode': False,
            'sender_email': 'brief@example.com', 'support_email': 'support@example.com',
            'portal_url': 'https://billing.stripe.com/p/login/example', 'sending_enabled': True}
        self.db = connect(self.settings)
        self.env = patch.dict(os.environ, SAM_API_KEY='sam-test', STRIPE_SECRET_KEY='rk_test_fake', RESEND_API_KEY='re_fake')
        self.env.start()
    def tearDown(self):
        self.env.stop()
        self.db.close()
        self.tmp.cleanup()
    def seed(self):
        upsert(self.db, notice(), T)
        self.db.commit()
        setmeta(self.db, 'source_ok', stamp(T))
        setmeta(self.db, 'billing_ok', stamp(T))
        self.db.execute('INSERT INTO subscribers VALUES (?,?,1,?)', ('sub_1', 'test@example.com', stamp(T)))
        self.db.commit()
    def test_upsert_preserves_first_seen_and_detects_changes(self):
        upsert(self.db, notice(), T)
        upsert(self.db, notice(), T+timedelta(hours=1))
        self.assertEqual(self.db.execute('SELECT count(*) FROM changes').fetchone()[0], 0)
        upsert(self.db, notice(responseDeadLine='2026-10-01'), T+timedelta(hours=2))
        self.assertEqual(self.db.execute('SELECT count(*) FROM changes').fetchone()[0], 1)
        self.assertEqual(self.db.execute('SELECT first_seen FROM opportunities').fetchone()[0], stamp(T))
    def test_closed_award_other_naics_and_stale_hidden(self):
        for modification in ({'active':'No'}, {'type':'Award Notice'}, {'naicsCode':'000000'},
                             {'responseDeadLine':'2026-08-01'}, {'responseDeadLine':'garbage'}):
            upsert(self.db, notice(**modification), T)
            self.assertEqual(inventory(self.db, T), [])
        upsert(self.db, notice(), T-timedelta(days=3))
        self.assertEqual(inventory(self.db, T), [])
    def test_missing_deadline_included_and_date_only_conservative(self):
        upsert(self.db, notice(responseDeadLine=''), T)
        self.assertEqual(len(inventory(self.db, T)), 1)
        upsert(self.db, notice(responseDeadLine='2026-09-07'), T)
        self.assertEqual(inventory(self.db, T), [])
    def test_source_id_validated_and_contacts_not_stored(self):
        with self.assertRaises(ValueError): normalize(notice(noticeId='../../evil'))
        result = normalize(notice(pointOfContact=[{'email':'private@example.com'}]))
        self.assertNotIn('private@example.com', json.dumps(result))
    def test_sam_pagination_uses_page_index(self):
        fake = Fake([{'opportunitiesData':[notice()], 'totalRecords':2},
                     {'opportunitiesData':[notice(noticeId='other')], 'totalRecords':2}])
        ingest(self.db, self.settings, fake, T)
        self.assertEqual([c[1]['params']['offset'] for c in fake.calls], [0,1])
        self.assertEqual(len(inventory(self.db,T)),2)
        ingest(self.db,self.settings,fake,T)
        self.assertEqual(len(fake.calls),2)
    def test_partial_snapshot_does_not_update(self):
        fake = Fake([{'opportunitiesData':[notice()], 'totalRecords':999}])
        with self.assertRaises(Blocked): ingest(self.db,dict(self.settings,sam_pages=1),fake,T)
        self.assertEqual(self.db.execute('SELECT count(*) FROM opportunities').fetchone()[0],0)
        self.assertEqual(getmeta(self.db,'source_ok'),'')
    def test_disappeared_notice_loses_freshness(self):
        upsert(self.db,notice(),T-timedelta(hours=1))
        ingest(self.db,self.settings,Fake([{'opportunitiesData':[],'totalRecords':0}]),T)
        self.assertEqual(inventory(self.db,T),[])
    def test_entitlement_excludes_wrong_product_unpaid_test_and_cancelled(self):
        self.assertTrue(entitled(subscription(),'price_margins',False))
        for modification in ({'status':'canceled'}, {'livemode':True}, {'pause_collection':{'behavior':'void'}},
                             {'latest_invoice': {'paid':False}}, {'latest_invoice':{'paid':True,'status':'paid','amount_paid':0}}):
            self.assertFalse(entitled(subscription(**modification),'price_margins',False))
        self.assertFalse(entitled(subscription(),'other',False))
    def test_stripe_complete_sync_and_cancel(self):
        sync_subscribers(self.db,self.settings,Fake([{'data':[subscription()],'has_more':False}]))
        self.assertEqual(self.db.execute('SELECT active FROM subscribers').fetchone()[0],1)
        sync_subscribers(self.db,self.settings,Fake([{'data':[],'has_more':False}]))
        self.assertEqual(self.db.execute('SELECT active FROM subscribers').fetchone()[0],0)
    def test_stripe_failure_preserves_snapshot_but_no_success_stamp(self):
        self.seed()
        fake = Fake([{'data':[subscription()],'has_more':True},Blocked('down')])
        with self.assertRaises(Blocked): sync_subscribers(self.db,self.settings,fake)
        self.assertEqual(getmeta(self.db,'billing_ok'),stamp(T))
    def test_queue_idempotent_and_stale_source_blocks(self):
        self.seed()
        queue_briefs(self.db,self.settings,T)
        queue_briefs(self.db,self.settings,T)
        self.assertEqual(self.db.execute('SELECT count(*) FROM outbox').fetchone()[0],1)
        with self.assertRaises(Blocked): queue_briefs(self.db,self.settings,T+timedelta(days=2))
    @patch('margins.core.time.sleep')
    def test_send_retry_same_payload_and_idempotency_key(self, sleep):
        self.seed()
        queue_briefs(self.db,self.settings,T)
        failed = Fake([Blocked('timeout')])
        with self.assertRaises(Blocked): deliver(self.db,self.settings,failed,T)
        success = Fake([{'id':'email_1'}])
        self.assertEqual(deliver(self.db,self.settings,success,T),1)
        self.assertEqual(failed.calls[0][1],success.calls[0][1])
        self.assertEqual(deliver(self.db,self.settings,Fake([]),T),0)
        self.assertEqual(self.db.execute("SELECT count FROM usage WHERE kind='email'").fetchone()[0],1)
    def test_old_ambiguous_send_requires_review(self):
        self.seed()
        queue_briefs(self.db,self.settings,T)
        self.db.execute('UPDATE outbox SET first_attempt=?',(stamp(T-timedelta(hours=24)),))
        self.db.commit()
        deliver(self.db,self.settings,Fake([]),T)
        self.assertEqual(self.db.execute('SELECT state FROM outbox').fetchone()[0],'review')
    def test_cancellation_suppression_and_email_change_prevent_send(self):
        self.seed()
        queue_briefs(self.db,self.settings,T)
        self.db.execute('UPDATE subscribers SET email=?',('changed@example.com',))
        self.db.commit()
        self.assertEqual(deliver(self.db,self.settings,Fake([]),T),0)
        self.assertEqual(self.db.execute('SELECT state FROM outbox').fetchone()[0],'cancelled')
    def test_stale_billing_blocks_and_sending_default_off(self):
        self.seed()
        with self.assertRaises(Blocked): deliver(self.db,self.settings,Fake([]),T+timedelta(hours=1))
        self.assertEqual(deliver(self.db,dict(self.settings,sending_enabled=False),Fake([]),T),0)
    def test_budget_blocks(self):
        reserve(self.db,'test',1,2,T)
        with self.assertRaises(Blocked): reserve(self.db,'test',1,2,T)
        reserve(self.db,'test',1,2,T+timedelta(days=1))
        with self.assertRaises(Blocked): reserve(self.db,'test',1,2,T+timedelta(days=2))
    def test_csv_formula_neutralized(self):
        text = csv_data([{'title':'  =HYPERLINK("evil")'}])
        self.assertIn("'  =HYPERLINK",text)
    def test_site_escapes_source_never_leaks_customer_and_disables_demo_checkout(self):
        self.seed()
        upsert(self.db,notice(title='<script>alert(1)</script>'),T)
        output = Path(self.tmp.name)/'site'
        with patch('margins.site.now',return_value=T),patch('margins.site.inventory',return_value=inventory(self.db,T)):
            render(self.db,dict(self.settings,payment_link='https://buy.stripe.com/example',launch_verified=True,live_mode=True),output,True)
        page = (output/'index.html').read_text()
        self.assertIn('&lt;script&gt;',page)
        self.assertNotIn('href="https://buy.stripe.com/example"',page)
        self.assertNotIn('test@example.com',page)
        self.assertIn('href="./style.css"',page)
        self.assertIn('noindex',page)
    def test_source_error_blocks_checkout(self):
        self.seed()
        setmeta(self.db,'source_error','failed')
        with patch('margins.site.now',return_value=T):
            render(self.db,dict(self.settings,payment_link='https://buy.stripe.com/example',launch_verified=True,live_mode=True),Path(self.tmp.name)/'site')
        self.assertNotIn('id="checkout"',(Path(self.tmp.name)/'site/index.html').read_text())
    def test_url_restrictions(self):
        for url in ['javascript:alert(1)','http://buy.stripe.com/x','https://buy.stripe.com.evil/x','https://u:p@buy.stripe.com/x']:
            self.assertEqual(safe_url(url,{'buy.stripe.com'}),'')

if __name__ == '__main__': unittest.main()
