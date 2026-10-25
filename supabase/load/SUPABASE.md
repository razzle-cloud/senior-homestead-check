# Supabase database: decatur-exemptions

Migrated from `decatur_tax.sqlite` on 2026-10-06. The SQLite file and the original MySQL dump remain the archive and were not modified.

- **Project:** `decatur-exemptions` (ref `kwmfcuwqplcfruolrjhz`), organization Spunlogic, region us-east-1, Postgres 17 with PostGIS.
- **Size:** about 155 MB; 50 tables, 619,376 rows, plus map layers.

## Structure

| Schema | What it holds | Contains names/addresses? |
|---|---|---|
| `raw` | Original pulls: city tax bills and bill lines, city and county parcels, county exemptions, profiles, sales, owner history, fetch logs, exemption code reference | Yes |
| `analysis` | Cleaned parcel table, gap candidates, filing rates, senior take-up, tax rates and rules, `_v1` snapshots, and the original and enhancement views (`v_summary`, `v_parcel_master`, `r_gap_summary`, and others) | Yes |
| `census` | ACS 2020-2024 and 2020 Census values, tract benchmarks and outlines, take-up checks, unfiled-senior estimate, long-tenure priority list | Parcel IDs only |
| `geo` | `parcels` (8,164 outlines), `streets` (2,534), `city_limits`, and the `parcel_status` map view | Site address in `parcel_status` |
| `share` | 8 aggregate-only views for a future public site: `gap_summary`, `filing_rates`, `senior_takeup`, `gaps_by_value_decile`, `gaps_by_tract` (suppressed under 25 homes), `census_profile`, `census_excess_decomposition`, `unfiled_senior_estimate` | No |

## Security

- None of these schemas is exposed through Supabase's API; only `public` is exposed, and it is empty.
- Row-level security is on for every table with no policies, so API roles are denied by default.
- `anon` and `authenticated` have no privileges on any table or view; verified after the load.
- To publish the `share` views later: add `share` to the API's exposed schemas, then grant `usage` on the schema and `select` on those views to `anon`. Review each view first.

## Verification (2026-10-06)

- Row counts match the SQLite export for all 50 tables.
- `analysis.v_summary` reproduces all 13 original headline numbers (7,693 parcels; 26 county-senior-not-city; 1,167 reverse; 1,021 Goal 2; and so on).
- `r_gap_summary`, `r_data_quality` and `r_gap_by_decile` are identical to their `_v1` snapshots.
- Census take-up figures match (1,633 proven 65+; 6,415 homestead; 521 pre-1990 owners).
- All parcel geometries are valid; the city limits cover 4.58 sq mi.

## Reloading

On the Mac: `zsh ~/Documents/Decatur-Senior-Exemptions/supabase_export/run_load.sh`, using the Session pooler connection string. The script truncates and reloads everything in one transaction, so it is safe to rerun. Regenerate the CSVs first with `python3 export_for_supabase.py` if the SQLite data changes.

## Notes on the Postgres versions of the views

- Summed true/false conditions are cast to integers.
- `group_concat` became `string_agg`, two-argument `MIN` became `LEAST`, and `strftime` became `extract`.
- `NTILE` sorts NULLs first, to match SQLite.
- `v_parcel_master.tenure_years` uses the current year, as the original did.


## Data pull v2 (added 2026-10-06)

`pull_v2/` holds rewritten pull scripts that write straight into the Supabase database. See `pull_v2/README.md` for run steps. Compared with the original scripts, they detect blocks and never mark a blocked item done, fetch only what is missing or out of date, keep a daily request budget, and copy each table into the `archive` schema before changing it. The original project in Downloads is unchanged.

After the v2 scripts have been used, don't rerun `supabase_export/run_load.sh`: it would replace the newer data with the September 2026 SQLite copy.
