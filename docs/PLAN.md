# Margins — business and implementation plan

## Decision
Build an original Dokaz Industries product: a specialized federal janitorial-contract intelligence subscription. Working product name: Margins Cleaning Brief. No inherited application code or business ideas from the existing estate. Initial audience: US commercial cleaning contractors already able to bid on federal work. Sell time saved reviewing opportunities, not access to exclusive data or guaranteed contract wins.

## Offer and hypothesis
$79/month, cancel through Stripe's hosted customer portal. Nationwide janitorial notices (NAICS 561720), source links, changes to tracked notice metadata, and upcoming deadlines. No AI-generated eligibility claims. Only currently open solicitation/combined-solicitation notices appear as bid opportunities. Sources-sought, awards, and expired notices are excluded. Missing deadlines are explicitly identified. Subscribers receive a daily brief with a CSV attachment. A free public board exposes a limited current sample plus useful location pages and RSS. Public data remains available free at SAM.gov.

This is a demand hypothesis, not validated passive income. General-purpose competitors and free SAM searches exist. A narrow workflow, clear change history, and dependable delivery must justify the price. Do not describe keyword rules as AI or imply complete federal coverage.

## Economics
Startup cash budget: $0 software and hosting on free tiers, using an existing Windows computer, internet, and Dokaz domain. No ads, domain purchase, paid AI, inventory, trades, or automatic plan upgrades. Power, existing equipment, and internet are real costs but not new purchases. Runtime can stop when the computer sleeps. Third-party account verification may require more than entering a login once.

Planning model: US domestic cards 2.9% + $0.30; Stripe Billing 0.7%; refund/chargeback reserve 5% of gross; $50/month operating allowance. Contribution per $79 subscriber = $71.906. 57 subscribers = $4,503 gross and approximately $4,049 operating contribution after allowance. This is before income taxes, owner labor, unusual disputes, and any sales-tax obligations. Actual merchant fees, refunds, retention and acquisition must be measured. No profit guarantee or date promised.

## Acquisition
Primary zero-cash route: a useful crawlable free bid board, genuine state-specific pages only when source data exists, XML sitemap, RSS, and internal links to original notices. Publish at most daily. Never fabricate geographic pages, testimonials, revenue, award values, or deadlines. Search indexing, ranking, traffic, and purchases are not guaranteed. Checkout and renewal are hosted by Stripe. No unsolicited email, social posts, ad purchases, or messages are authorized by this build.

Checkpoints after a real launch: day 14, confirm reliable data and delivery and search indexing; day 30, evaluate actual qualified visits and checkout conversion; day 60, review retention/refunds and paid willingness. A useful validation threshold is 100 qualified visitors and 3 paying customers; these are decision thresholds, not forecasts. If no qualified traffic arrives, passive acquisition is unproven and a distribution change needs owner work or explicit outreach authorization. Do not keep building features and call that traction.

## Architecture
Python 3.11+ standard-library local service with SQLite. SAM API ingestion bounded by a daily request quota and page cap; initial 90-day backfill plus rotating refresh of older tracked notices. Keep only source metadata required for the service, not contracting-officer personal contact information. Detect content fingerprints, preserve change evidence, and expire stale records. Stripe read-only polling scopes to the configured recurring price; only paid active subscriptions receive service. Resend delivery uses deterministic per-subscription/day idempotency and a durable outbox. Retry within the provider idempotency window; uncertain older sends stop for review. No public inbound server or webhook is needed. Render a static storefront and current source board; publish to Cloudflare Pages using its CLI on the operator machine. SQLite, logs, outbox, and all secrets stay outside git. A Windows launcher handles setup, demo, status, one cycle, and the background task.

## Build sequence
1. Store this plan in the repo before code.
2. Implement storage, ingestion, filtering, change tracking, briefs, billing entitlement, outbox, daily limits, and status.
3. Add a source-backed static storefront with checkout and billing links, RSS, sitemap, and gated publishing.
4. Add one-time setup and Windows Task Scheduler installation.
5. Test normalization, duplicate runs, pagination, entitlement failures, source outages, escaping, spending/delivery limits, and idempotency behavior.
6. Push reviewable code. Live launch requires configured owner accounts and verified end-to-end test delivery; never mark a demo as live.

## Account setup and limits
SAM.gov API key; a dedicated Stripe restricted read key and $79/month recurring price/payment link; Stripe customer portal; Resend key and verified sending domain; Cloudflare free Pages project and local Wrangler login. Keep a strict free-tier cap of 90 emails/day and 2,800/month; cap publication to 28/month and SAM calls to the configured account quota (default 8/day). No third-party API keys are assumed merely because repositories mention a provider. Do not recover or copy committed credentials.

## Automation boundary
Automatable: ingestion, filtering, state pages, checkout, entitlement reconciliation, scheduled briefs, change detection, retries, expiration, publication and renewal/cancellation handling. Not guaranteed automatable: customer acquisition, merchant identity verification, domain ownership, disputes/refunds, tax setup, API policy changes, hardware outages, and unusual customer support. This implementation must explicitly report setup blockers rather than claim it is already making money.

## Evidence reviewed 2026-09-07
- https://open.gsa.gov/api/get-opportunities-public-api/ — API key, daily quotas, pagination, source fields and active-record behavior.
- https://stripe.com/pricing — domestic card fees.
- https://stripe.com/billing/pricing — usage-based subscription billing fees.
- https://docs.stripe.com/api/subscriptions/list — price-scoped subscription pagination.
- https://docs.stripe.com/no-code/customer-portal — self-service billing login link.
- https://resend.com/pricing — free-tier allowance must be rechecked at setup.
- https://resend.com/docs/api-reference/emails/send-email — delivery and idempotency.
- https://developers.cloudflare.com/pages/platform/limits/ — free static publication limits.
- https://govbidalerts.org/pricing — competitive context; advertised cheaper general-purpose plans demonstrate that our pricing is unvalidated.

## Definition of done
Working tested repository and Windows entry point; no fake production data or success claims. Commercial launch is a separate operational state: valid account setup, fresh live source data, tested provider integration, working checkout/cancellation, and published storefront. The revenue target is an outcome to measure, not a software completion criterion.
