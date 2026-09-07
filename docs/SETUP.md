# One-time setup and launch

The engine runs on your existing Windows computer. No VPS, LLM subscription, paid ads, new domain or Python dependencies are required. Keep the computer awake, online and logged into the user that owns the scheduled task. A service that continues while the computer is off requires different hosting; that is not configured here.

Expect account verification, domain verification and a checkout test. These cannot be honestly reduced to entering a single password. This guide explains all required values instead of assuming accounts or API access from other repositories. Use a dedicated sending subdomain of a domain you already own. Do not buy a domain for this experiment.

## 1. Install and try the offline demo

Install Python 3.11+ if needed and clone/pull the repo into `C:\src\Margins`. Double-click `C:\src\Margins\Margins.cmd`, choose 3. All sample records are fictional. Demo files are never used for customer delivery or publication.

## 2. SAM.gov

Create/sign in to your own SAM.gov account and obtain the public API key in Account Details. This is an account API key, not a request to register Dokaz as a federal contractor. Confirm the quota assigned to your role and set `sam_daily_limit` at or below it (default 8, never more than 8 in this version). The API returns source metadata; it does not guarantee complete local-government coverage.

Official guide: https://open.gsa.gov/api/get-opportunities-public-api/

## 3. Stripe — test mode first

Use Dokaz's Stripe business account if available. Do not reuse a restricted key without checking its permissions. Create a dedicated product called `Margins Cleaning Brief` and a recurring USD price of **$79 monthly**, quantity one, without a trial. Create a Payment Link for that price. Do not enable customer-adjustable quantities or unrelated upsells. Configure receipt emails and business/support details. Review the product's applicable tax settings for your business; the code does not make that determination.

Enable Stripe's hosted customer portal with cancellation at period end. Copy its login URL. Customers can manage billing without a Margins account. Set accurate terms/support links on checkout and review the language in the generated site before launch.

Create a restricted read key with read access to subscriptions, invoices, customers, prices and payment links (including line items). The engine does not need payment/refund write permissions. Save the price ID (`price_...`), Payment Link ID (`plink_...`), checkout URL (`https://buy.stripe.com/...`) and portal login URL (`https://billing.stripe.com/p/login/...`). The URL and ID are different values. Stripe's key modes and objects must match.

Run menu option 1, then 2 and 6. A local `config.json` and `.env` are created; do not commit them. On Windows use your normal protected user account and disk encryption where available; no portable secret manager is bundled.

Official docs: https://docs.stripe.com/payment-links and https://docs.stripe.com/no-code/customer-portal

## 4. Resend

Create/use an account on the free plan and verify an existing Dokaz sending subdomain through its DNS records. Do not replace existing email/MX records. Use the exact DNS configuration supplied by Resend for that subdomain. A testing sender such as onboarding@resend.dev cannot deliver to arbitrary customers. Use a dedicated API key for the verified domain.

Set `sender_email` to the verified address and `support_email` to an inbox you read. The support address is also the recipient of the explicit owner self-test command. Configure `business_address` with a business mailing address suitable for publication; it appears in the site and briefs.

Run menu option 7 once and verify the email arrived. An API success means provider acceptance, not inbox delivery. Check delivery events in Resend for bounces/complaints. Suppress problem addresses with the CLI; cancellation/refunds remain in Stripe. There is no live webhook receiver or automatic complaint-event polling in this version.

Free-tier controls: 90 newly attempted messages/day and 2,800/month, including owner tests. Keep this account/key isolated from other apps or lower your practical subscriber ceiling; the local counter cannot see provider usage by other apps. Resend may change pricing or quotas; verify during setup. The program never upgrades the account.

## 5. Cloudflare Pages

Use a free Cloudflare account. Install Node.js LTS if necessary, then install Wrangler from the official package (`npm install -g wrangler`). Authenticate using `wrangler login`. Create a Direct Upload Pages project (`wrangler pages project create margins-cleaning --production-branch main`), using an available project name. This account action is performed locally by you; no Cloudflare account was changed by the build.

Set `cloudflare_project` to that project name, `site_url` to its HTTPS `pages.dev` URL (no trailing slash), and `wrangler_path` to the complete result of `where wrangler` for `wrangler.cmd`. The engine invokes that executable with fixed deployment arguments, never downloaded source text. Keep Wrangler current according to Cloudflare's documentation. A permanent public free URL avoids buying a new domain.

Do not use GitHub Pages as the commercial checkout host. This repo is source control; the intended storefront host is Cloudflare Pages. Publish generated `dist/` only, never the repo or `data/`.

Official docs: https://developers.cloudflare.com/pages/get-started/direct-upload/

## 6. Test the connected path

With Stripe still in test mode:

1. Complete a test subscription checkout using Stripe's documented test method, with your own delivery email. Do not enter a real card in test mode.
2. Run one cycle. It retrieves real SAM records and reconciles test subscriptions; sending remains off. Inspect `python -m margins status` and the generated `dist/index.html`. Production subscriber addresses never enter `dist/`.
3. Verify the owner delivery test. Inspect the locally stored pending brief or its source code to verify the product scope.
4. Test portal cancellation in Stripe test mode. Confirm a subscription cancelled immediately is no longer active after a cycle. Cancellation at period end remains active until the paid period expires.
5. Confirm source deadlines and links against several real SAM notices. The build could not do this without your API key.

## 7. Go live

Re-run setup with the live Stripe read key and live dedicated price/Payment Link/portal. Setup deliberately resets launch, sending and publishing flags. The live price must match $79/month. Run Verify, Self-test, and one cycle. Run `python -m margins launch` and confirm locally only after the account checks and test purchase/cancellation above. Run another cycle to publish the live storefront. Visit the published URL, check source links, checkout pricing, cancellation and contact details, then install the scheduled task from menu option 9.

The script does not purchase anything, start a subscription on your behalf or recover existing credentials. The task runs every 30 minutes; ingestion, publication and per-subscriber briefs are limited to daily. Paid subscriber delivery begins on the next successful cycle (normally within 30 minutes while the computer is available).

## Launch limitations

- Automatic local publication is capped at one attempt/day and 31/month. A failed publication may wait until the next day to protect quotas. Cloudflare's provider limit is higher; this is our own lower cap.
- Static pages show the snapshot time. Browser code hides the visible checkout link after 30 hours, but an independently saved Stripe Payment Link still works. A prolonged outage requires disabling the Payment Link in Stripe. This build cannot guarantee that billing stops when the desktop is offline.
- The feed detects metadata changes, not all amendments inside documents. It starts with a 90-day posted window and rotates one older tracked record/day. Records not observed for 36 hours are omitted. It does not claim exhaustive coverage.
- Traffic acquisition and paying demand are unverified. No outreach messages or ad purchases are made by the code.
