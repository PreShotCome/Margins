# Margins

An original Dokaz Industries business: **Margins Cleaning Brief**, a $79/month federal cleaning-contract intelligence subscription. Finds open NAICS 561720 notices, tracks metadata changes, builds a free source-linked board, checks paid Stripe subscriptions and delivers daily email/CSV briefs.

**Status: built and locally tested; not commercially launched.** No customers, traffic, earnings, live source retrieval or real purchases have been verified. This is an automated service implementation, not a guaranteed $4,000/month income source. Customer acquisition is the main unvalidated assumption.

## Start on Windows

If `C:\src\Margins` is already your cloned repository:

```powershell
cd C:\src\Margins
git pull origin main
.\Margins.cmd
```

If it is an empty folder without Git:

```powershell
git clone https://github.com/PreShotCome/Margins.git C:\src\Margins
C:\src\Margins\Margins.cmd
```

Python 3.11+ is required. The engine has **no Python package dependencies**. Menu option 3 builds a clearly labelled fictional demo without accounts or network calls. The launcher is `C:\src\Margins\Margins.cmd` after you pull or clone this repository there. The building session did not have access to the actual Windows drive.

Read [the business plan](docs/PLAN.md), then [the one-time setup guide](docs/SETUP.md). Do not enter secrets into GitHub issues, chat, or tracked source files.

## What is implemented

- Bounded daily SAM.gov ingestion with page-index pagination and a rolling 90-day snapshot.
- Open solicitation filtering, stale-record exclusion, source metadata fingerprints and deadline changes.
- Original static storefront, up to six free source records, real state pages only where sample data exists, RSS and XML sitemap.
- Stripe price/Payment Link validation, price-scoped paginated paid subscription reconciliation and hosted cancellation link.
- Durable email outbox, Resend idempotency, retry limits, uncertain-send review and CSV formula neutralization.
- Free-tier caps, local SQLite storage and rotating backups, source outage handling and local status.
- Windows menu, configuration wizard and scheduled task running every 30 minutes while logged in.
- Daily optional Cloudflare Pages publication using an installed/authenticated Wrangler CLI.

The software never submits bids, trades money, buys ads, upgrades provider plans, scrapes private contacts, or sends cold outreach. Customer email delivery requires explicit local launch configuration. The public site has no signup database, trackers or payment secrets.

## Money target

| Paid subscribers | Monthly gross | Modelled operating contribution |
|---:|---:|---:|
| 10 | $790 | $669 |
| 25 | $1,975 | $1,748 |
| 57 | $4,503 | $4,049 |
| 75 | $5,925 | $5,343 |

Assumes domestic-card payment fees of 2.9% + $0.30, 0.7% Billing fees, a 5% gross reserve, and a $50 monthly operating allowance. Before income tax and owner labor; not actual earnings. No conversion, churn, or demand has been validated. General-purpose competitors offer lower prices; willingness to pay must be tested.

Startup software/hosting cash can be $0 using existing equipment, internet and a verified Dokaz domain. Power is not free, and running a desktop solely for this can create additional electricity expense. No new purchase is made by the code. The <$10 cash requirement is conditional on those existing resources and staying on free plans.

## Commands

```text
python -m margins demo        # offline fictional storefront and sample brief
python -m margins setup       # hidden-key configuration wizard
python -m margins doctor      # presence/mode checks; no provider calls
python -m margins verify      # verifies Stripe price and Payment Link
python -m margins self-test   # sends only to the configured owner/support inbox
python -m margins run         # one bounded cycle
python -m margins status      # freshness, counts, outbox states; no customer addresses
python -m margins economics   # assumptions, not verified revenue
python -m margins launch      # local operational confirmation after setup/testing
python -m margins suppress --email customer@example.com
python -m unittest discover -s tests -v
```

Suppression stops email, not subscription charges. Refunds, disputes, tax decisions and exceptional support remain human tasks. There is no promise that the computer, APIs, deliverability or acquisition can run forever without attention.

## Repository map

- `margins/core.py`: APIs, storage, source normalization, subscriptions, briefs and outbox.
- `margins/site.py`: static storefront, source sample and discovery files.
- `margins/__main__.py`: setup, launch, maintenance, publication and status.
- `Margins.cmd`, `scripts/schedule.ps1`: Windows entry points.
- `docs/`: plan, setup, acquisition/operations and validation record.
- `tests/`: integration seams and failure-path tests with deterministic provider fixtures.

`config.json`, `.env`, `data/`, `dist/` and `demo-output/` are local generated/private files and ignored by Git. No application code was copied from existing repositories.
