# Operating and validating Margins

## Daily automatic cycle

The Windows scheduler invokes `python -m margins run` every 30 minutes. An OS-level lock prevents concurrent runs. A completed daily source snapshot is reused for the remainder of that UTC day; a complete paginated result is required before promotion. Stripe entitlement is reconciled every cycle. An active subscription must belong to the configured price/mode and have a positive paid latest invoice. Free trials and zero-dollar invoices are intentionally excluded.

Each subscriber/day gets one immutable outbox payload. Provider acceptance is recorded after sending. If the process crashes after a request, its deterministic Resend idempotency key is reused within 23 hours. Requests older than that become `review`, never blindly resent after the provider's 24-hour guarantee expires. Five failed attempts pause that message. Old unattempted briefs expire. Removing/changing a subscriber email, cancelling immediate entitlement, or suppressing an address prevents the pending delivery.

Retries can fail; this is not an exactly-once-delivery guarantee. Provider acceptance is not proof the recipient read or even received the email. Review Resend events for bounces/complaints and use suppression. A customer who stops email may still need cancellation/refund in Stripe.

## Status and recovery

Run launcher option 5 or `python -m margins status`. It shows last source/billing/cycle successes, notice count, cached entitlement count and outbox states. An old timestamp is an outage signal, not zero demand. No customer list or secrets are printed.

- SAM error: inspect the key/quota and official provider status. Delivery pauses. Do not invent a replacement source or increase quota beyond the account limit.
- Stripe error: entitlement cannot be freshly confirmed; no mail is sent from that cycle.
- Email failure: fix provider credentials or domain delivery settings, then rerun. A `review` row requires checking its provider idempotency key/provider logs before any manual resend.
- Publication error: reauthenticate Wrangler locally and confirm the Pages project. Its full stdout is intentionally not stored in application logs.
- Computer shutdown: start the launcher and run a cycle after reconnecting. Old briefs do not all flood customers.
- Major outage: disable the Payment Link in Stripe and notify/refund affected paying customers as appropriate. An offline desktop cannot change an external checkout link.

A successful daily cycle writes a SQLite backup under `data/backups/`, retaining seven copies. To restore: stop the scheduled task, copy the newest known-good backup over `data/margins.sqlite3`, remove WAL/SHM only after all app processes are stopped, and reconcile billing before sending. Restoring an old outbox can create ambiguous deliveries; keep sending off until delivery history is reconciled with Resend.

Remove schedule: `powershell -File scripts/schedule.ps1 -Remove`. Set `sending_enabled` and `publishing_enabled` false in `config.json` to pause them. Never expose `data/` through a static host or push it to Git. Local inactive records are deleted after 90 days, change records after 180 days, backup copies within another seven days. Provider records have separate retention.

## Acquisition experiment

Automatic asset creation is not automatic traffic. The free board publishes an honest sample, links to original sources, and creates state pages only for existing sample records. It supplies RSS and sitemap.xml. It never creates fabricated reviews, customer counts, earnings, fake government affiliations or thousands of empty keyword pages.

Initial zero-cash path is organic discovery. Submit the real sitemap through your search-console account once the site is live. Indexing may take time and may not produce traffic. Use your hosting/search-console metrics for visits and Stripe's actual payment reports for conversion/revenue; the local subscriber count is not accounting revenue. No analytics account is silently created. No search submission, community post, commercial message, or customer contact was performed during the build.

At day 14: is ingestion correct, is delivery reliable, and are useful pages indexed?
At day 30: how many relevant visitors and actual new purchases arrived? If zero traffic, price changes alone are not a solution.
At day 60: calculate refunds, retention, time spent on support, and contribution from actual receipts. A possible early validation bar is 100 qualified visits and 3 paying customers, not a forecast. If there is no traction, reconsider distribution before expanding features. Organic-only acquisition may never hit $4,000/month.

If you later authorize outreach, a separate opt-in campaign/community plan can be prepared. Nothing in this build assumes blanket authority to send messages or reuse tenant/resident contacts. The product's customers are independent cleaning contractors, not residents from Ian's property-management work.

## Financial measurement

Use actual settled receipts minus processing/billing fees, refunds, disputes, hosting, email, incremental power, acquisition and other expenses. Sales tax collected is not revenue. The built-in economics command is a scenario calculator only. The $4,000 target is before income tax/owner labor in that model; take-home profit requires a separate calculation. Never optimize the price on invented conversions.

There is deliberately no automated refund/legal/tax agent. These exceptions and initial merchant verification are the human operations that prevent an honest '100% hands-off forever' promise.
