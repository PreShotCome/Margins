"""Margins business engine. Standard library only; no generative or paid compute."""
from __future__ import annotations
import base64
import contextlib
import csv
import hashlib
import html
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[1]

class Blocked(RuntimeError):
    pass

def now():
    return datetime.now(UTC)

def stamp(dt=None):
    return (dt or now()).isoformat()

def date(value):
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        # Source timestamps without an offset are not precise instants. Conservative UTC.
        return result.replace(tzinfo=UTC) if result.tzinfo is None else result.astimezone(UTC)
    except (ValueError, TypeError):
        return None

def clean(value, limit=500):
    return re.sub(r'[\x00-\x1f\x7f]', ' ', str(value or '')).strip()[:limit]

def safe_url(value, hosts=None):
    value = str(value or '')
    p = urlparse(value)
    if p.scheme != 'https' or not p.hostname or p.username or p.password:
        return ''
    if hosts and p.hostname not in hosts:
        return ''
    return value

def config():
    path = ROOT / 'config.json'
    settings = json.loads(path.read_text()) if path.exists() else {}
    secret_path = ROOT / '.env'
    if secret_path.exists():
        for line in secret_path.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())
    settings['data_dir'] = str(ROOT / settings.get('data_dir', 'data'))
    return settings

SCHEMA = '''
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS opportunities(
 id TEXT PRIMARY KEY, body TEXT NOT NULL, fingerprint TEXT NOT NULL,
 first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, changed_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS changes(
 id INTEGER PRIMARY KEY, notice_id TEXT NOT NULL, at TEXT NOT NULL,
 before_json TEXT NOT NULL, after_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS subscribers(
 id TEXT PRIMARY KEY, email TEXT NOT NULL, active INTEGER NOT NULL, checked_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outbox(
 id TEXT PRIMARY KEY, subscriber_id TEXT NOT NULL, day TEXT NOT NULL,
 payload TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
 created TEXT NOT NULL, first_attempt TEXT, provider_id TEXT, attempts INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS usage(kind TEXT, day TEXT, count INTEGER NOT NULL,
 PRIMARY KEY(kind, day));
CREATE TABLE IF NOT EXISTS suppression(email TEXT PRIMARY KEY);
'''

def connect(settings):
    folder = Path(settings['data_dir'])
    folder.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(folder / 'margins.sqlite3', timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript(SCHEMA)
    return db

def getmeta(db, key, default=''):
    row = db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
    return row[0] if row else default

def setmeta(db, key, value):
    db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (key, str(value)))
    db.commit()

@contextlib.contextmanager
def lock(settings):
    """OS lock releases on process death; prevents manual/scheduled duplicate cycles."""
    path = Path(settings['data_dir'])
    path.mkdir(parents=True, exist_ok=True)
    with (path / 'run.lock').open('a+b') as f:
        f.seek(0)
        f.write(b'0')
        f.flush()
        f.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise Blocked('Another Margins cycle is running.') from exc
        try:
            yield
        finally:
            f.seek(0)
            if os.name == 'nt':
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

class API:
    def request(self, url, key='', params=None, payload=None, idem=None):
        if urlparse(url).hostname not in {'api.sam.gov', 'api.stripe.com', 'api.resend.com'}:
            raise Blocked('Unexpected API host.')
        if params:
            url += '?' + urlencode(params, doseq=True)
        headers = {'Accept': 'application/json', 'User-Agent': 'Margins/1.0'}
        if key:
            headers['Authorization'] = 'Bearer ' + key
        if idem:
            headers['Idempotency-Key'] = idem
        body = None
        if payload is not None:
            body = json.dumps(payload).encode()
            headers['Content-Type'] = 'application/json'
        try:
            with build_opener(NoRedirect()).open(Request(url, body, headers), timeout=35) as r:
                data = r.read(12_000_001)
                if len(data) > 12_000_000:
                    raise Blocked('API response exceeded size limit.')
                return json.loads(data)
        except HTTPError as exc:
            # Never print provider body, full request URL, query API key, or customer data.
            raise Blocked(f'{urlparse(url).hostname} returned HTTP {exc.code}.') from None
        except (URLError, TimeoutError, ValueError, OSError):
            raise Blocked(f'{urlparse(url).hostname} unavailable or returned invalid JSON.') from None

def reserve(db, kind, daily, monthly=10**8, dt=None):
    day = (dt or now()).date().isoformat()
    with db:
        count = db.execute('SELECT count FROM usage WHERE kind=? AND day=?', (kind, day)).fetchone()
        total = db.execute('SELECT COALESCE(SUM(count),0) FROM usage WHERE kind=? AND day LIKE ?',
                           (kind, day[:7]+'%')).fetchone()[0]
        if (count and count[0] >= daily) or total >= monthly:
            raise Blocked(f'{kind} free-tier budget exhausted; no automatic upgrade.')
        db.execute('INSERT INTO usage VALUES (?,?,1) ON CONFLICT(kind,day) DO UPDATE SET count=count+1', (kind, day))

def normalize(raw):
    ident = clean(raw.get('noticeId'), 100)
    if not re.fullmatch(r'[A-Za-z0-9_-]+', ident):
        raise ValueError('Invalid notice ID')
    state = ((raw.get('placeOfPerformance') or {}).get('state') or {}).get('code', '')
    state = clean(state, 2).upper()
    if not re.fullmatch('[A-Z]{2}', state):
        state = 'US'
    deadline = raw.get('responseDeadLine') or raw.get('reponseDeadLine') or ''
    return {'id': ident, 'title': clean(raw.get('title')), 'state': state,
            'agency': clean(raw.get('fullParentPathName'), 300),
            'naics': clean(raw.get('naicsCode'), 6), 'type': clean(raw.get('type')),
            'active': str(raw.get('active', '')).lower() in ('yes', 'true'),
            'deadline': clean(deadline, 60), 'posted': clean(raw.get('postedDate'), 60),
            'set_aside': clean(raw.get('typeOfSetAsideDescription') or raw.get('setAside')),
            'solicitation': clean(raw.get('solicitationNumber'), 100),
            'url': 'https://sam.gov/opp/' + ident + '/view'}

def upsert(db, raw, dt=None):
    item = normalize(raw)
    body = json.dumps(item, sort_keys=True)
    fp = hashlib.sha256(body.encode()).hexdigest()
    ts = stamp(dt)
    old = db.execute('SELECT * FROM opportunities WHERE id=?', (item['id'],)).fetchone()
    if old and old['fingerprint'] != fp:
        db.execute('INSERT INTO changes(notice_id,at,before_json,after_json) VALUES (?,?,?,?)',
                   (item['id'], ts, old['body'], body))
    db.execute('''INSERT INTO opportunities VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
      body=excluded.body,fingerprint=excluded.fingerprint,last_seen=excluded.last_seen,
      changed_at=CASE WHEN opportunities.fingerprint != excluded.fingerprint
      THEN excluded.changed_at ELSE opportunities.changed_at END''',
      (item['id'], body, fp, old['first_seen'] if old else ts, ts,
       ts if not old or old['fingerprint'] != fp else old['changed_at']))


def ingest(db, settings, api, dt=None):
    dt = dt or now()
    if getmeta(db, 'source_day') == dt.date().isoformat():
        return
    key = os.environ.get('SAM_API_KEY')
    if not key:
        raise Blocked('SAM_API_KEY is missing.')
    staged = []
    # Rolling 90-day snapshot; offset is PAGE INDEX, not row offset, per GSA documentation.
    params = {'api_key': key, 'postedFrom': (dt-timedelta(days=90)).strftime('%m/%d/%Y'),
              'postedTo': dt.strftime('%m/%d/%Y'), 'ncode': '561720', 'limit': 1000}
    pages = min(int(settings.get('sam_pages', 4)), 4)
    complete = False
    for page in range(pages):
        reserve(db, 'sam', min(int(settings.get('sam_daily_limit', 8)), 8), dt=dt)
        response = api.request('https://api.sam.gov/opportunities/v2/search', params={**params, 'offset': page})
        batch = response.get('opportunitiesData')
        if not isinstance(batch, list) or not isinstance(response.get('totalRecords'), int):
            raise Blocked('SAM response schema changed.')
        staged.extend(batch)
        if len(staged) >= response['totalRecords']:
            complete = True
            break
        if not batch:
            break
    if not complete:
        raise Blocked('SAM snapshot incomplete; previous snapshot retained. Review page/quota limits.')
    with db:
        for raw in staged:
            upsert(db, raw, dt)
        # A missing item is not proof of cancellation. Remove freshness instead of asserting it.
        ids = {clean(r.get('noticeId'), 100) for r in staged}
        for row in db.execute('SELECT id, body FROM opportunities').fetchall():
            posted = date(json.loads(row['body'])['posted'])
            if row['id'] not in ids and posted and posted >= dt-timedelta(days=90):
                db.execute('UPDATE opportunities SET last_seen=? WHERE id=?',
                           (stamp(dt-timedelta(days=30)), row['id']))
    setmeta(db, 'source_ok', stamp(dt))
    setmeta(db, 'source_day', dt.date().isoformat())
    # Independently refresh at most one old tracked notice daily. Stale ones remain hidden.
    old = db.execute('SELECT body FROM opportunities ORDER BY last_seen LIMIT 1').fetchone()
    if old:
        item = json.loads(old[0])
        posted = date(item['posted'])
        if posted and posted < dt-timedelta(days=89):
            reserve(db, 'sam', min(int(settings.get('sam_daily_limit', 8)), 8), dt=dt)
            response = api.request('https://api.sam.gov/opportunities/v2/search', params={
                'api_key': key, 'noticeid': item['id'], 'postedFrom': (dt-timedelta(days=364)).strftime('%m/%d/%Y'),
                'postedTo': dt.strftime('%m/%d/%Y'), 'limit': 1})
            with db:
                for raw in response.get('opportunitiesData', []):
                    upsert(db, raw, dt)

def inventory(db, dt=None):
    dt = dt or now()
    results = []
    for row in db.execute('SELECT * FROM opportunities'):
        item = json.loads(row['body'])
        deadline = date(item['deadline'])
        if not item['active'] or item['naics'] != '561720':
            continue
        if item['type'].lower() not in ('solicitation', 'combined synopsis/solicitation', 'o', 'k'):
            continue
        # If source omits a timezone, hide on the deadline day rather than claim precise availability.
        if item['deadline'] and deadline is None:
            continue
        if deadline and (deadline <= dt or (not re.search(r'(Z|[+-]\d{2}:\d{2})$', item['deadline']) and deadline.date() <= dt.date())):
            continue
        if date(row['last_seen']) < dt-timedelta(hours=36):
            continue
        item.update(first_seen=row['first_seen'], changed_at=row['changed_at'], last_seen=row['last_seen'])
        results.append(item)
    return sorted(results, key=lambda x: (x['deadline'] or '9999', x['id']))

def entitled(sub, price, live):
    invoice = sub.get('latest_invoice')
    return (sub.get('status') == 'active' and sub.get('livemode') is live
            and not sub.get('pause_collection') and isinstance(invoice, dict)
            and invoice.get('paid') is True and invoice.get('status') == 'paid'
            and invoice.get('amount_paid', 0) > 0
            and any(i.get('price', {}).get('id') == price for i in sub.get('items', {}).get('data', [])))

def sync_subscribers(db, settings, api):
    key = os.environ.get('STRIPE_SECRET_KEY', '')
    price = settings.get('stripe_price_id', '')
    if not key or not price:
        raise Blocked('Stripe key or dedicated recurring price is missing.')
    live = settings.get('live_mode', False)
    staged, cursor = [], None
    for _ in range(100):
        params = {'price': price, 'status': 'active', 'limit': 100,
                  'expand[]': ['data.customer', 'data.latest_invoice']}
        if cursor:
            params['starting_after'] = cursor
        response = api.request('https://api.stripe.com/v1/subscriptions', key, params)
        if not isinstance(response.get('data'), list) or not isinstance(response.get('has_more'), bool):
            raise Blocked('Stripe response schema changed.')
        for sub in response['data']:
            if entitled(sub, price, live):
                customer = sub.get('customer')
                email = customer.get('email', '') if isinstance(customer, dict) else ''
                if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
                    raise Blocked('An entitled customer has no valid delivery email; fix in Stripe.')
                staged.append((sub['id'], email.lower(), 1, stamp()))
        if not response['has_more']:
            break
        if not response['data'] or response['data'][-1]['id'] == cursor:
            raise Blocked('Stripe pagination did not advance.')
        cursor = response['data'][-1]['id']
    else:
        raise Blocked('Stripe pagination limit reached.')
    with db:
        db.execute('UPDATE subscribers SET active=0')
        db.executemany('INSERT OR REPLACE INTO subscribers VALUES (?,?,?,?)', staged)
    setmeta(db, 'billing_ok', stamp())

def csv_data(items):
    out = io.StringIO(newline='')
    fields = ['title', 'state', 'agency', 'deadline', 'set_aside', 'solicitation', 'url']
    writer = csv.writer(out)
    writer.writerow(fields)
    for item in items:
        values = []
        for field in fields:
            value = str(item.get(field, ''))
            if value.lstrip().startswith(('=', '+', '-', '@')):
                value = "'" + value
            values.append(value)
        writer.writerow(values)
    return out.getvalue()

def brief(db, items, settings, dt=None):
    dt = dt or now()
    text = [f'Margins Cleaning Brief | {dt.date()}', '',
            f'{len(items)} currently tracked open federal cleaning notices. Nationwide coverage, NAICS 561720.',
            'Metadata refreshed from SAM.gov. This is a filtered feed, not a complete procurement search.',
            'Confirm scope, eligibility, site visits, amendments and time zone in the original solicitation.', '']
    for item in items[:30]:
        deadline = item['deadline'] or 'Not provided; verify with source'
        text += [item['title'], f"Location: {item['state']} | Due: {deadline}",
                 f"Agency: {item['agency']}", f"Set-aside: {item['set_aside'] or 'Not provided'}"]
        changes = db.execute('SELECT before_json,after_json FROM changes WHERE notice_id=? AND at>=? ORDER BY id DESC LIMIT 1',
                             (item['id'], stamp(dt-timedelta(days=1)))).fetchone()
        if changes:
            before, after = map(json.loads, changes)
            fields = [k for k in before if before[k] != after[k]]
            text.append('Changed metadata: ' + ', '.join(fields))
            if before['deadline'] != after['deadline']:
                text.append(f"Deadline changed: {before['deadline'] or 'unknown'} -> {after['deadline'] or 'unknown'}")
        elif date(item['first_seen']) >= dt-timedelta(days=1):
            text.append('New to this feed')
        text += [item['url'], '']
    if not items:
        text += ['No open notices passed today’s filters. No opportunity or contract win is promised.', '']
    text += ['The attached CSV includes every currently tracked open notice.',
             'Metadata change detection does not inspect attachments or guarantee detection of every amendment.',
             'Manage or cancel your subscription: ' + settings.get('portal_url', ''),
             'Delivery/support: ' + settings.get('support_email', ''),
             'Dokaz Industries | ' + settings.get('business_address', '')]
    return '\n'.join(text)

def queue_briefs(db, settings, dt=None):
    dt = dt or now()
    fresh = date(getmeta(db, 'source_ok'))
    if not fresh or fresh < dt-timedelta(hours=30):
        raise Blocked('Source data is stale; customer delivery paused.')
    items = inventory(db, dt)
    content = brief(db, items, settings, dt)
    for sub in db.execute('SELECT * FROM subscribers WHERE active=1').fetchall():
        if db.execute('SELECT 1 FROM suppression WHERE email=?', (sub['email'],)).fetchone():
            continue
        ident = hashlib.sha256(f"{sub['id']}:{dt.date()}".encode()).hexdigest()
        payload = {'from': settings['sender_email'], 'to': [sub['email']],
                   'reply_to': settings['support_email'], 'subject': f'Margins Cleaning Brief — {dt.date()}',
                   'text': content, 'attachments': [{'filename': 'cleaning-opportunities.csv',
                   'content': base64.b64encode(csv_data(items).encode()).decode()}]}
        db.execute('INSERT OR IGNORE INTO outbox(id,subscriber_id,day,payload,created) VALUES (?,?,?,?,?)',
                   (ident, sub['id'], str(dt.date()), json.dumps(payload), stamp(dt)))
    db.commit()

def deliver(db, settings, api, dt=None):
    dt = dt or now()
    if not settings.get('sending_enabled'):
        return 0
    billing = date(getmeta(db, 'billing_ok'))
    if not billing or billing < dt-timedelta(minutes=10):
        raise Blocked('Fresh billing verification required for delivery.')
    key = os.environ.get('RESEND_API_KEY', '')
    if not key:
        raise Blocked('RESEND_API_KEY is missing.')
    sent = 0
    for row in db.execute("SELECT * FROM outbox WHERE state='pending' ORDER BY created,id").fetchall():
        sub = db.execute('SELECT * FROM subscribers WHERE id=? AND active=1', (row['subscriber_id'],)).fetchone()
        payload = json.loads(row['payload'])
        if not sub or sub['email'] != payload['to'][0] or db.execute('SELECT 1 FROM suppression WHERE email=?', (payload['to'][0],)).fetchone():
            db.execute("UPDATE outbox SET state='cancelled' WHERE id=?", (row['id'],))
            db.commit()
            continue
        first = date(row['first_attempt'])
        if first and dt-first >= timedelta(hours=23):
            db.execute("UPDATE outbox SET state='review' WHERE id=?", (row['id'],))
            db.commit()
            continue
        if not first and row['day'] != str(dt.date()):
            db.execute("UPDATE outbox SET state='expired' WHERE id=?", (row['id'],))
            db.commit()
            continue
        if row['attempts'] >= 5:
            continue
        if not first:
            reserve(db, 'email', 90, 2800, dt)
        db.execute('UPDATE outbox SET first_attempt=COALESCE(first_attempt,?),attempts=attempts+1 WHERE id=?',
                   (stamp(dt), row['id']))
        db.commit()
        response = api.request('https://api.resend.com/emails', key, payload=payload, idem=row['id'])
        if not response.get('id'):
            raise Blocked('Email provider did not acknowledge delivery request.')
        db.execute("UPDATE outbox SET state='sent',provider_id=? WHERE id=?", (response['id'], row['id']))
        db.commit()
        sent += 1
        time.sleep(0.6)  # Resend default rate budget; each wait is less than a second.
    return sent
