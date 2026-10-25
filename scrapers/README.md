# Data pull, version 2 (writes to Supabase)

These scripts refresh the property data directly in the `decatur-exemptions` Supabase database. They are a rewritten copy of the original pull scripts. The original project in `~/Downloads/decatur-dekalb-tax-main` and `decatur_tax.sqlite` are not touched.

## What changed from version 1

| | Version 1 | Version 2 |
|---|---|---|
| Database | Local MySQL | Supabase (`raw` schema) |
| "Too many requests" from the city site | Saved as zero records and marked **done** | Marked **blocked**, pauses 15–30 minutes, stops after the second block |
| County block pages | Could be saved as "no data" | 403/429, "access denied" pages and pages with no data tables count as blocks |
| What gets fetched | Everything not yet fetched | Only what is missing, failed, blocked or from an older tax year (options add more) |
| Request limits | Delay only | Delay with random jitter, plus a daily budget per site across all runs |
| Safety | Overwrote rows in place | Each table is copied into the `archive` schema before the first write each day (last 3 copies kept) |
| Parcel list for county pages | 2024 city parcel layer only | City layer plus the county's residential parcels, so new parcels are included |
| Removed exemptions | Stayed in the table | Exemption rows for a parcel and year are replaced on each fetch |
| County GIS layer | Fixed to `Tax_Parcels_2025` | Picks the newest `Tax_Parcels_YYYY` automatically |
| Raw pages | Saved as plain files | Saved gzipped in `raw/` (about 5x smaller) |

Every run is recorded in `raw.pull_runs` (requests, rows, blocks, how it ended).

## One-time setup

1. Open `config.py` and set `CONTACT` to an email address the website operators can reach. Live pulls will not start without it. You can use `export PULL_CONTACT=...` instead.
2. Check `CITY_YEARS` and `COUNTY_TAX_YEAR`. They are set to 2026.
3. In Terminal, run `cd ~/Documents/Decatur-Senior-Exemptions/pull_v2` and then `zsh run_v2.sh coverage.py`.

   The first run sets up the Python libraries, which takes a minute. It then asks for your Supabase connection string, the same Session pooler string you used for the load, and prints the coverage report. It makes no web requests.

## Running

Always start with `--plan`. It shows what would be fetched and how many days that takes at the daily budget, without contacting any site.

```
zsh run_v2.sh pull_county.py --plan
zsh run_v2.sh pull_county.py --limit 20            # small live test first
zsh run_v2.sh pull_county.py --max-minutes 240     # main pages (exemptions, owner profile)
zsh run_v2.sh pull_county.py --modes all --max-minutes 240
zsh run_v2.sh pull_gis.py                          # parcel layers; about 10 requests
zsh run_v2.sh pull_city_bills.py --plan
zsh run_v2.sh coverage.py
```

Runs can be stopped with Ctrl-C at any time. Rerunning carries on where the last run stopped. `run_v2.sh` keeps the Mac awake while a pull is running.

**Current state:** 48 county residential parcels have never had their county pages fetched. `pull_county.py` picks these up first, which takes about 96 requests. The 2026 city bills are complete, so `pull_city_bills.py` currently has nothing to do.

**At the next tax-year change:** set `COUNTY_TAX_YEAR = 2027`. All exemption, profile and owner-history pages then count as out of date, about 23,000 requests in total. At the default budget of 6,000 per day, that is about four days of runs. Sales and building pages are not year-specific and are not refetched.

### Useful options

| Option | Scripts | What it does |
|---|---|---|
| `--plan` | county, city | List the work; no requests |
| `--limit N` | county | Stop after N pages |
| `--max-minutes N` | county, city | Stop cleanly after N minutes |
| `--refresh-days N` | county, city | Also refetch anything older than N days |
| `--changed-gis` | county | Also refetch parcels whose values in the county GIS layer changed since the last archived copy. Run `pull_gis.py` first. |
| `--parcel "15 000 00 000"` | county | Only this parcel (repeatable) |
| `--reparse` | county | Re-read saved pages from `raw/`; no requests. `--raw-dir` points elsewhere. |
| `--force` | county, city | Refetch everything selected |
| `--list-layers` | gis | Show the county's `Tax_Parcels_YYYY` layers |

## If a site blocks the pull

- **What the script does.** It logs the item as `blocked`, pauses 15–30 minutes, slows down by half, and tries again. After a second block it stops and says so. Blocked items are retried on the next run.
- **What to do.** Wait several hours, ideally until the next day, before running again. Don't lower the delays in `config.py`.
- **The city tax site.** It throttled the original pull. Run the city script only when coverage shows a gap, and keep its budget at 400 requests a day or less.

## Undoing a bad pull

Before writing, each run copies the tables it changes into the `archive` schema, for example `archive.county_exemptions__20261007`. The last 3 copies of each table are kept. To roll back a table, run this in the Supabase SQL editor:

```sql
begin;
truncate raw.county_exemptions;
insert into raw.county_exemptions select * from archive.county_exemptions__20261007;
commit;
```

## Important

- **Don't rerun `supabase_export/run_load.sh` after using these scripts.** It replaces the `raw` tables with the September 2026 SQLite data and discards everything pulled since.
- **Analysis tables are not rebuilt automatically.** `analysis.r_parcel_clean`, the gap tables and the Census tables are built from the raw data. They keep the September numbers until they are rebuilt. The `_v1` snapshots keep the original results for comparison.
- **The database password is never saved** by these scripts. It is read with hidden input each time unless you set `DATABASE_URL` in your shell.

## Files

| File | Purpose |
|---|---|
| `config.py` | Settings: contact email, years, delays, budgets |
| `common.py` | Database connection, upserts, archive copies, run log, polite HTTP session with block handling |
| `pull_gis.py` | City and county parcel layers |
| `pull_city_bills.py` | City tax bills |
| `pull_county.py` | County tax commissioner pages |
| `coverage.py` | Read-only completeness report |
| `run_v2.sh` | Sets up Python, asks for the connection string, runs a script |
| `sql/05_pull_v2_prep.sql` | The database changes these scripts need (already applied to Supabase) |
| `tests/test_offline.py` | 33 offline checks against a local test database with simulated site responses, including blocks |
