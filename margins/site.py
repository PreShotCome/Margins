"""Source-backed static storefront. No browser tracking or personal data in output."""
import html
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
from .core import inventory, safe_url, date, now, getmeta, timedelta

STYLE = '''
:root{color-scheme:light;--ink:#14263b;--muted:#506079;--blue:#1150d5;--line:#d9e1ec}
*{box-sizing:border-box}body{margin:0;background:#f5f8fc;color:var(--ink);font:17px/1.6 system-ui,sans-serif}
a{color:var(--blue);text-underline-offset:4px}a:focus-visible,summary:focus-visible{outline:3px solid #f3b642;outline-offset:5px}
header,main,footer{max-width:1100px;margin:auto;padding:24px}header{display:flex;justify-content:space-between;gap:24px;flex-wrap:wrap;border-bottom:1px solid var(--line)}
.brand{font-size:23px;font-weight:800;letter-spacing:-1px;text-decoration:none;color:var(--ink)}nav{display:flex;gap:20px;flex-wrap:wrap}
.hero{display:grid;grid-template-columns:1.6fr 1fr;gap:50px;padding:54px 0}.eyebrow{font-size:14px;font-weight:700;text-transform:uppercase;letter-spacing:2px;color:var(--blue)}
h1{font-size:clamp(36px,5.6vw,64px);line-height:1.04;letter-spacing:-2px;margin:20px 0}h2{font-size:28px;line-height:1.2}h3{font-size:19px;margin:8px 0}
p{max-width:70ch}.muted{color:var(--muted)}.price{font-size:42px;font-weight:800}.plan{background:var(--ink);color:white;padding:30px;align-self:center}.plan a{color:white}.button{display:inline-block;background:var(--blue);color:white!important;padding:12px 20px;text-decoration:none;font-weight:650}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.card{background:white;padding:24px;border:1px solid var(--line);border-top:4px solid var(--blue)}.tag{font-size:14px;font-weight:650;color:var(--blue)}.status{padding:14px 18px;background:#e7eefb;border-left:4px solid var(--blue)}
section{margin:36px 0}details{border-top:1px solid var(--line);padding:18px 0}summary{cursor:pointer;font-weight:650}footer{font-size:14px;border-top:1px solid var(--line)}.small{font-size:14px}.locations{display:flex;gap:15px;flex-wrap:wrap}
@media(max-width:700px){.hero,.grid{grid-template-columns:1fr}.hero{gap:20px;padding:25px 0}header,main,footer{padding:18px}h1{letter-spacing:-1px}}
'''
e = html.escape

def render(db, settings, output, demo=False):
    output = Path(output)
    # This directory is generated only; replace through a staging directory to avoid partial output.
    stage = output.with_name(output.name + '-staging')
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    items = inventory(db)
    source = date(getmeta(db, 'source_ok'))
    fresh = source is not None and source > now()-timedelta(hours=30) and not getmeta(db, 'source_error')
    base = safe_url(settings.get('site_url', '')).rstrip('/')
    checkout = safe_url(settings.get('payment_link', ''), {'buy.stripe.com'})
    portal = safe_url(settings.get('portal_url', ''), {'billing.stripe.com'})
    ready = fresh and not demo and settings.get('live_mode') and settings.get('launch_verified') and checkout and portal
    support = settings.get('support_email', '')
    footer = f'''<footer>Margins Cleaning Brief · Dokaz Industries<br>
    Independent service. Not affiliated with SAM.gov or the US government.
    Original notices are free at <a href="https://sam.gov/opportunities">SAM.gov</a>.
    <p><a href="{e(base)}/privacy.html">Privacy</a> · <a href="{e(base)}/terms.html">Terms</a>
    {(' · <a href="'+e(portal)+'">Manage subscription</a>') if portal else ''}</p>
    <p>{e(support)}<br>{e(settings.get('business_address',''))}</p></footer>'''
    def page(title, body, path, description):
        canonical = f'<link rel="canonical" href="{e(base)}/{e(path)}">' if base else ''
        robots = '<meta name="robots" content="noindex">' if demo or not fresh else ''
        doc = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <title>{e(title)} | Margins</title><meta name="description" content="{e(description)}">
        {canonical}{robots}<script src="{e(base)}/freshness.js" defer></script><link rel="stylesheet" href="{e(base)}/style.css">
        <link rel="alternate" type="application/rss+xml" title="Cleaning bid sample" href="{e(base)}/feed.xml">
        </head><body><header><a class="brand" href="{e(base)}/">MARGINS<span class="small"> / CLEANING</span></a>
        <nav><a href="{e(base)}/#board">Free bid board</a><a href="{e(base)}/#subscribe">Daily brief</a></nav></header>
        <main>{body}</main>{footer}</body></html>'''
        if not base:
            prefix = '../' if '/' in path else './'
            doc = doc.replace('href="/', 'href="'+prefix).replace('src="/', 'src="'+prefix)
        target = stage / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(doc, encoding='utf-8')
    def card(item):
        return f'''<article class="card"><span class="tag">{e(item['state'])} · FEDERAL CLEANING</span>
        <h3><a href="{e(item['url'])}" rel="noopener">{e(item['title'])}</a></h3>
        <p class="muted">{e(item['agency'])}</p><p>Due: {e(item['deadline'] or 'Not provided — verify with source')}</p>
        <p class="small">Set-aside: {e(item['set_aside'] or 'Not provided')}<br>Last observed: {e(item['last_seen'][:10])}</p></article>'''
    status = 'DEMONSTRATION — fictional records; checkout disabled.' if demo else (
        'Source snapshot: '+source.strftime('%Y-%m-%d %H:%M UTC') if fresh else 'Live feed is not ready. Checkout is paused.')
    sample = items[:6] if fresh else []
    states = sorted({i['state'] for i in sample})
    action = f'<a class="button" id="checkout" href="{e(checkout)}">Subscribe for $79/month</a>' if ready else '<p>Subscriptions are not open yet.</p>'
    body = f'''<div class="hero"><div><div class="eyebrow">For commercial cleaning contractors</div>
      <h1>Find the bid.<br>Keep the deadline.</h1><p class="muted">A daily brief of federal janitorial opportunities,
      tracked changes, and upcoming deadlines. Spend less time repeating the same search.</p>
      <a href="#board">Browse the free sample</a></div><aside class="plan" id="subscribe">
      <div class="eyebrow" style="color:#adccff">Margins Cleaning Brief</div><div class="price">$79<span class="small"> / month</span></div>
      <p>Nationwide federal cleaning notices. Daily email. Full feed CSV. Metadata change tracking.</p>
      {action}<p class="small">Monthly recurring charge. Cancel through the billing portal. Applicable taxes may be added.
      No contract wins or minimum notice count promised.</p></aside></div>
      <p class="status" id="freshness" data-observed="{e(source.isoformat() if source else "")}">{e(status)}</p><section id="board"><h2>The free bid board</h2>
      <p class="muted">A sample of up to six currently tracked notices. Verify all requirements in the original solicitation.</p>
      <div class="grid">{''.join(card(i) for i in sample) or '<p>No current source-backed notices to display.</p>'}</div></section>
      <section><h2>Browse this sample by location</h2><div class="locations">
      {''.join(f'<a href="{e(base)}/states/{s.lower()}.html">{s}</a>' for s in states) or '<p>Location pages appear when live notices are available.</p>'}</div></section>
      <section><h2>What you receive</h2><div class="grid"><div class="card"><h3>One brief each day</h3>
      <p>Open solicitation notices, source deadlines, locations, and stated set-asides. Every entry links to SAM.gov.</p></div>
      <div class="card"><h3>Changes you can inspect</h3><p>See tracked metadata changes and download the current feed as CSV.
      Attachment amendments and full bid documents still need your review.</p></div></div></section>
      <section><h2>Before you subscribe</h2><details><summary>Can I find this data free?</summary><p>Yes. SAM.gov is free.
      The subscription pays for repeated filtering, tracked metadata changes, and delivery. It is not exclusive data.</p></details>
      <details><summary>Does this cover my local city or school district?</summary><p>No. This version covers federal
      NAICS 561720 notices with available source metadata. It does not aggregate state, county, or city procurement portals.</p></details>
      <details><summary>Will I qualify for these contracts?</summary><p>The brief does not determine eligibility or submit bids.
      Review the solicitation, registrations, certifications, site visits, and other requirements yourself.</p></details>
      <details><summary>What happens when there are no bids?</summary><p>The daily brief reports that no open notices passed the filters.
      No minimum volume is promised. Source outages pause delivery rather than presenting old records as fresh.</p></details>
      <details><summary>How do I cancel or get help?</summary><p>Use the billing portal to cancel renewal. Contact {e(support or 'the operator once subscriptions open')}
      for delivery problems, refunds, and support. Refund requests require human review.</p></details></section>'''
    page('Federal cleaning contract opportunities', body, 'index.html', 'Federal janitorial bid samples and daily source-linked contract briefs for commercial cleaning contractors.')
    paths = ['index.html']
    for state in states:
        path = f'states/{state.lower()}.html'
        page(f'{state} federal cleaning bids', f'<h1>{state} cleaning bids</h1><p>{e(status)}</p><div class="grid">'+
             ''.join(card(i) for i in sample if i['state'] == state)+'</div><p><a href="'+e(base)+'/#subscribe">See the nationwide daily brief</a></p>',
             path, f'Current sample of federal cleaning notices with a {state} place of performance.')
        paths.append(path)
    page('Privacy', '''<h1>Privacy</h1><p>Dokaz Industries operates Margins Cleaning Brief. The static site uses no application cookies,
    advertising trackers, or email open pixels. The hosting provider may keep security and access logs.</p>
    <p>Stripe processes payments and provides subscription IDs, subscription status, and delivery email addresses.
    Resend processes the delivery email and brief. We do not store card numbers. Customer records and delivery logs
    are stored on the operator's computer to provide service and diagnose delivery failures.</p>
    <p>Local subscriber and message records are removed after 90 days of inactivity (backup copies expire within seven more days); payment-provider records follow
    their own retention requirements. Contact the support address below for access or deletion requests.
    Public bid pages contain procurement metadata, not subscriber information. No subscriber list is sold.</p>''',
    'privacy.html', 'How Margins handles subscription and delivery information.')
    page('Terms', '''<h1>Subscription terms</h1><p>Margins Cleaning Brief is a Dokaz Industries information service priced at
    $79 per month, plus applicable taxes. It renews monthly until cancelled through Stripe's customer portal.
    Cancellation stops future renewal; paid service ordinarily continues through the paid period.</p>
    <p>Coverage is limited to filtered federal janitorial opportunity metadata available through the SAM.gov API.
    No completeness, eligibility determination, successful bid, exclusive access, or minimum volume is promised.
    Confirm all requirements and deadlines with the issuing agency. The service does not submit bids or provide legal advice.</p>
    <p>Delivery depends on source availability, email providers and the operator's infrastructure. Temporary outages
    may pause briefs. Contact support for non-delivery, billing disputes, and refund requests; these require human review.
    Rights that cannot be excluded by law remain unaffected.</p>''', 'terms.html', 'Pricing, cancellation, coverage, and support terms for Margins.')
    (stage / 'style.css').write_text(STYLE)
    (stage / 'freshness.js').write_text('''const status = document.getElementById('freshness');
const observed = status && Date.parse(status.dataset.observed);
if (observed && Date.now()-observed > 30*3600*1000) {
  status.textContent = 'This snapshot is out of date. Check the original source for current availability.';
  const checkout = document.getElementById('checkout');
  if (checkout) checkout.replaceWith(document.createTextNode('Subscriptions are temporarily paused.'));
}
''')
    rss = ET.Element('rss', version='2.0')
    channel = ET.SubElement(rss, 'channel')
    for key, value in [('title', 'Margins Cleaning Bid Sample'), ('link', base+'/'), ('description', status)]:
        ET.SubElement(channel, key).text = value
    for item in sample:
        node = ET.SubElement(channel, 'item')
        for key, value in [('title', item['title']), ('link', item['url']), ('guid', item['url']), ('description', f"{item['state']}; due {item['deadline'] or 'not provided'}")]:
            ET.SubElement(node, key).text = value
    ET.ElementTree(rss).write(stage/'feed.xml', encoding='utf-8', xml_declaration=True)
    sitemap = ET.Element('urlset', xmlns='http://www.sitemaps.org/schemas/sitemap/0.9')
    if base and fresh and not demo:
        for path in paths:
            ET.SubElement(ET.SubElement(sitemap, 'url'), 'loc').text = base+'/'+path
    ET.ElementTree(sitemap).write(stage/'sitemap.xml', encoding='utf-8', xml_declaration=True)
    (stage/'robots.txt').write_text('User-agent: *\n'+('Disallow: /\n' if demo else 'Allow: /\n')+('Sitemap: '+base+'/sitemap.xml\n' if base else ''))
    (stage/'_headers').write_text('/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n  Content-Security-Policy: default-src \'none\'; script-src \'self\'; style-src \'self\' \'unsafe-inline\'; base-uri \'none\'; frame-ancestors \'none\'; form-action https://buy.stripe.com\n')
    (stage/'_redirects').write_text('/index.html / 301\n')
    if output.exists():
        shutil.rmtree(output)
    stage.rename(output)
    return len(sample)
