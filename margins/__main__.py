from __future__ import annotations
import argparse
import getpass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from datetime import timedelta
from .core import (ROOT, API, Blocked, config, connect, lock, now, stamp, date, getmeta,
                   setmeta, ingest, inventory, sync_subscribers, queue_briefs, deliver,
                   reserve, safe_url, upsert)
from .site import render


def check(settings):
    missing = []
    for key in ('SAM_API_KEY', 'STRIPE_SECRET_KEY', 'RESEND_API_KEY'):
        if not os.environ.get(key):
            missing.append(key)
    for key in ('stripe_price_id', 'stripe_payment_link_id', 'sender_email', 'support_email', 'business_address'):
        if not settings.get(key):
            missing.append(key)
    for key, hosts in [('payment_link', {'buy.stripe.com'}), ('portal_url', {'billing.stripe.com'}), ('site_url', None)]:
        if not safe_url(settings.get(key), hosts):
            missing.append(key+' (valid HTTPS URL)')
    if missing:
        raise Blocked('Setup incomplete: '+', '.join(missing))
    live = settings.get('live_mode', False)
    key = os.environ['STRIPE_SECRET_KEY']
    if ('_live_' in key) is not live or not key.startswith(('rk_', 'sk_')):
        raise Blocked('Stripe key mode does not match live_mode.')
    if live and '/test_' in settings['payment_link']:
        raise Blocked('Test checkout cannot be used in live mode.')


def verify(settings, db, api):
    check(settings)
    key = os.environ['STRIPE_SECRET_KEY']
    price = api.request('https://api.stripe.com/v1/prices/'+settings['stripe_price_id'], key)
    if not (price.get('active') and price.get('livemode') is settings['live_mode']
            and price.get('currency') == 'usd' and price.get('unit_amount') == 7900
            and price.get('recurring', {}).get('interval') == 'month'
            and price.get('recurring', {}).get('interval_count') == 1):
        raise Blocked('Stripe price must be active $79 USD per month in the configured mode.')
    link = api.request('https://api.stripe.com/v1/payment_links/'+settings['stripe_payment_link_id'], key)
    if not (link.get('active') and link.get('livemode') is settings['live_mode']
            and link.get('url') == settings['payment_link']):
        raise Blocked('Stripe Payment Link is inactive, wrong mode, or URL does not match.')
    lines = api.request('https://api.stripe.com/v1/payment_links/'+settings['stripe_payment_link_id']+'/line_items', key)
    records = lines.get('data', [])
    if lines.get('has_more') or len(records) != 1 or records[0].get('price', {}).get('id') != settings['stripe_price_id'] or records[0].get('quantity') != 1:
        raise Blocked('Payment Link must sell exactly one unit of the configured subscription.')
    if link.get('subscription_data', {}).get('trial_period_days'):
        raise Blocked('Disable checkout trials; this version delivers only after a paid invoice.')
    setmeta(db, 'price_verified', stamp())
    print('Verified Stripe price, mode and checkout link. This does not verify tax configuration or a purchase.')


def publish(settings, db):
    if not settings.get('publishing_enabled'):
        return
    if not settings.get('launch_verified'):
        raise Blocked('Finish launch verification before automatic publishing.')
    if getmeta(db, 'published_day') == str(now().date()):
        return
    project = settings.get('cloudflare_project', '')
    executable = settings.get('wrangler_path') or shutil.which('wrangler')
    if not re.fullmatch('[a-z0-9-]{1,58}', project) or not executable or not Path(executable).is_file():
        raise Blocked('Set cloudflare_project and the absolute installed wrangler_path.')
    reserve(db, 'publish', 1, 31)
    proc = subprocess.run([executable, 'pages', 'deploy', str(ROOT/'dist'), '--project-name', project,
                           '--branch', 'main', '--commit-dirty=true'], cwd=ROOT, capture_output=True, timeout=180)
    if proc.returncode:
        raise Blocked('Cloudflare publication failed. Check local Wrangler login/project; no provider output logged.')
    setmeta(db, 'published_day', str(now().date()))


def maintenance(db, settings):
    cutoff = stamp(now()-timedelta(days=90))
    with db:
        db.execute('DELETE FROM outbox WHERE created<?', (cutoff,))
        db.execute('DELETE FROM subscribers WHERE active=0 AND checked_at<?', (cutoff,))
        db.execute('DELETE FROM changes WHERE at<?', (stamp(now()-timedelta(days=180)),))
        db.execute('DELETE FROM opportunities WHERE last_seen<?', (cutoff,))
    if getmeta(db, 'backup_day') != str(now().date()):
        import sqlite3
        folder = Path(settings['data_dir'])/'backups'
        folder.mkdir(exist_ok=True)
        destination = sqlite3.connect(folder/(str(now().date())+'.sqlite3'))
        db.backup(destination)
        destination.close()
        for file in sorted(folder.glob('*.sqlite3'))[:-7]:
            file.unlink()
        setmeta(db, 'backup_day', str(now().date()))


def cycle(settings):
    with lock(settings), connect(settings) as db:
        api = API()
        check(settings)
        try:
            ingest(db, settings, api)
            setmeta(db, 'source_error', '')
        except (Blocked, ValueError, KeyError, TypeError) as exc:
            setmeta(db, 'source_error', 'Feed refresh failed; inspect setup and source quota.')
            render(db, settings, ROOT/'dist')
            # Publish a paused checkout if permitted, even when the source is down.
            try:
                publish(settings, db)
            except Blocked:
                pass
            raise Blocked('Source refresh failed. Delivery paused. Run doctor and retry later.') from None
        sync_subscribers(db, settings, api)
        if settings.get('sending_enabled') and not settings.get('launch_verified'):
            raise Blocked('Finish launch verification before enabling subscription delivery.')
        queue_briefs(db, settings)
        sent = deliver(db, settings, api)
        render(db, settings, ROOT/'dist')
        publish(settings, db)
        maintenance(db, settings)
        setmeta(db, 'last_cycle', stamp())
        setmeta(db, 'last_error', '')
        print(f'Cycle complete. {len(inventory(db))} current notices; {sent} messages accepted by provider.')


def demo(settings):
    # In-memory fixtures never enter production database and are never published.
    import sqlite3
    from .core import SCHEMA
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    for index, state in enumerate(['WA', 'OR', 'CA', 'TX']):
        upsert(db, {'noticeId': 'DEMO'+str(index), 'title': 'Fictional federal custodial services — '+state,
                    'active': 'Yes', 'naicsCode': '561720', 'type': 'Solicitation',
                    'postedDate': str(now().date()), 'responseDeadLine': stamp(now()+timedelta(days=index+10)),
                    'fullParentPathName': 'Demonstration agency — not a real solicitation',
                    'placeOfPerformance': {'state': {'code': state}}, 'setAside': 'Example only'})
    setmeta(db, 'source_ok', stamp())
    local = dict(settings, site_url='', launch_verified=False)
    render(db, local, ROOT/'demo-output', demo=True)
    from .core import brief, csv_data
    (ROOT/'demo-output'/'sample-brief.txt').write_text(brief(db, inventory(db), local), encoding='utf-8')
    (ROOT/'demo-output'/'sample.csv').write_text(csv_data(inventory(db)), encoding='utf-8')
    print('Demo generated: demo-output/index.html and sample-brief.txt. All records are fictional. No network requests.')


def wizard():
    settings = config()
    existing = ROOT/'config.json'
    if not existing.exists():
        settings = json.loads((ROOT/'config.example.json').read_text())
    print('One-time setup. Press Enter to retain existing values. Keys are hidden and stored only in .env.')
    print('Use Stripe TEST MODE first. See docs/SETUP.md for account setup and restricted key permissions.')
    values = {k: os.environ.get(k, '') for k in ('SAM_API_KEY', 'STRIPE_SECRET_KEY', 'RESEND_API_KEY')}
    for key in values:
        answer = getpass.getpass(key+(' [configured]' if values[key] else '')+': ')
        if answer:
            if '\n' in answer or '\r' in answer:
                raise Blocked('Key contains a line break.')
            values[key] = answer
    for key in ('stripe_price_id', 'stripe_payment_link_id', 'payment_link', 'portal_url', 'sender_email',
                'support_email', 'business_address', 'site_url', 'cloudflare_project', 'wrangler_path'):
        answer = input(f'{key} [{settings.get(key, "")}]: ').strip()
        if answer:
            settings[key] = answer
    settings.update(live_mode='_live_' in values['STRIPE_SECRET_KEY'], launch_verified=False,
                    sending_enabled=False, publishing_enabled=False)
    # Preserve relative data directory when settings were loaded as an absolute path.
    (ROOT/'.env').write_text(''.join(k+'='+v+'\n' for k, v in values.items()), encoding='utf-8')
    if os.name != 'nt':
        (ROOT/'.env').chmod(0o600)
    existing.write_text(json.dumps(settings, indent=2)+'\n')
    with connect(dict(settings, data_dir=str(ROOT/settings.get('data_dir', 'data')))) as db:
        setmeta(db, 'owner_test', '')
        setmeta(db, 'price_verified', '')
    print('Saved. Delivery and publishing remain off. Next: python -m margins doctor, then verify.')


def main():
    parser = argparse.ArgumentParser(description='Margins automated federal cleaning brief')
    parser.add_argument('command', choices=['setup','demo','doctor','verify','self-test','run','status','launch','suppress','economics'])
    parser.add_argument('--email', help='Email address to suppress (does not cancel billing)')
    args = parser.parse_args()
    settings = config()
    if args.command == 'setup':
        wizard()
        return
    if args.command == 'demo':
        demo(settings)
        return
    if args.command == 'economics':
        print('Planning only: $79/mo; 3.6% fees + $0.30; 5% gross reserve; $50 monthly allowance.')
        for count in (0, 10, 25, 57, 75):
            print(f'{count:2} subscribers | gross ${count*79:,.2f} | operating contribution ${count*(79*.914-.30)-50:,.2f}')
        print('Before income tax and owner labor. Assumes domestic cards. Revenue not verified by this model.')
        return
    if args.command == 'run':
        cycle(settings)
        return
    with lock(settings), connect(settings) as db:
        if args.command == 'doctor':
            try:
                check(settings)
                print('Required settings present; provider credentials not tested. Run verify next.')
            except Blocked as exc:
                print(str(exc))
            print('Sending:', bool(settings.get('sending_enabled')), '| Publishing:', bool(settings.get('publishing_enabled')))
            print('Windows automation requires this computer awake, logged in, and connected to the internet.')
        elif args.command == 'verify':
            verify(settings, db, API())
        elif args.command == 'self-test':
            check(settings)
            reserve(db, 'email', 90, 2800)
            payload = {'from': settings['sender_email'], 'to': [settings['support_email']],
                       'subject': 'Margins owner delivery test', 'text': 'Owner delivery test. No customer has been contacted.'}
            result = API().request('https://api.resend.com/emails', os.environ['RESEND_API_KEY'],
                                   payload=payload, idem='owner-test-'+str(now().date()))
            if not result.get('id'):
                raise Blocked('Email provider did not acknowledge owner test.')
            setmeta(db, 'owner_test', stamp())
            print('Owner test accepted by Resend. Check your inbox; API acceptance is not inbox delivery.')
        elif args.command == 'launch':
            if not settings.get('live_mode'):
                raise Blocked('Switch to verified live Stripe configuration before commercial launch.')
            verify(settings, db, API())
            fresh = date(getmeta(db, 'source_ok'))
            if not fresh or fresh < now()-timedelta(hours=30) or getmeta(db, 'source_error'):
                raise Blocked('Run a successful live-source cycle before launch.')
            if not getmeta(db, 'owner_test'):
                raise Blocked('Run self-test and verify inbox delivery first.')
            print('Confirm you checked the owner email, completed a TEST checkout/cancellation, configured taxes as needed,')
            print('reviewed the published terms, and want paid-customer emails and daily public publishing enabled.')
            if input('Type LAUNCH to enable: ') != 'LAUNCH':
                print('No launch settings changed.')
                return
            settings.update(launch_verified=True, sending_enabled=True, publishing_enabled=True)
            (ROOT/'config.json').write_text(json.dumps(settings, indent=2)+'\n')
            print('Enabled. Run a cycle and install the Windows scheduled task. No purchase is guaranteed.')
        elif args.command == 'suppress':
            if not args.email or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', args.email):
                raise Blocked('Provide a valid --email.')
            db.execute('INSERT OR IGNORE INTO suppression VALUES (?)', (args.email.lower(),))
            db.commit()
            print('Email delivery suppressed. Billing is unchanged; cancel/refund through Stripe when appropriate.')
        elif args.command == 'status':
            active = db.execute('SELECT count(*) FROM subscribers WHERE active=1').fetchone()[0]
            print('Configured mode:', 'LIVE' if settings.get('live_mode') else 'TEST')
            print('Source last success:', getmeta(db, 'source_ok', 'never'))
            print('Billing last success:', getmeta(db, 'billing_ok', 'never'))
            print('Cycle last success:', getmeta(db, 'last_cycle', 'never'))
            print('Current notices:', len(inventory(db)))
            print('Cached paid active subscriptions:', active, '(may be stale; not collected revenue)')
            for row in db.execute('SELECT state,count(*) FROM outbox GROUP BY state'):
                print('Outbox', row[0], row[1])
            print('Last error:', getmeta(db, 'last_error', 'none'))

if __name__ == '__main__':
    try:
        main()
    except (Blocked, subprocess.TimeoutExpired) as exc:
        message = str(exc) if isinstance(exc, Blocked) else 'Publication timed out; inspect Cloudflare before retrying.'
        print('STOPPED:', message, file=sys.stderr)
        try:
            with connect(config()) as db:
                setmeta(db, 'last_error', message)
        except Exception:
            pass
        sys.exit(1)
    except Exception:
        # Avoid accidental credential/PII leakage from SDK/URL exceptions.
        print('STOPPED: unexpected local error. Run unit tests and inspect configuration; no secrets logged.', file=sys.stderr)
        sys.exit(1)
