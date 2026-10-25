# decatur_tax.sqlite

A single-file SQLite copy of the `decatur_tax` MySQL database from
`~/Downloads/decatur-dekalb-tax-main/sql/dump/decatur_tax.sql`. The MySQL dump
was only read; it is unchanged (SHA-1 2a334d84…d13d745 before and after).

Open it with any SQLite tool (DB Browser for SQLite, DBeaver, TablePlus,
Python `sqlite3`, or `sqlite3 decatur_tax.sqlite` on the command line). No
server needed.

## Contents
- The same 12 tables with the same rows (city_bill_lines 307,332; city_bills 24,876;
  city_parcels 8,653; county_sales 43,523; county_owner_history 61,636; etc.).
- The same 9 analysis views (v_parcel_master, v_goal1_*, v_goal2_candidates, v_summary, …),
  translated from MySQL to SQLite SQL.
- One helper table, `derived_street_key`, which replaces MySQL's stored function
  `street_key()` (used by the owner-occupied test). Nothing else is added.

## Verified against the MySQL results (out/*.csv)
- All 13 v_summary metrics identical.
- v_parcel_master: 7,693 rows x 58 columns = 446,194 cells, 0 differences.
- Goal 1, Goal 1 reverse and Goal 2 lists contain exactly the same parcels.

## Notes
- `tenure_years` is computed from today's date, as in MySQL, so it ticks up each January.
- Decimal columns are stored as SQLite NUMERIC (whole amounts come back as integers).
- To rebuild: `python3 convert_mysql_to_sqlite.py <decatur_tax.sql> decatur_tax.sqlite`

---

# Research enhancements (sections 1-3)

Added by `enhance_sections_1_3.py` (re-runnable). New objects only, prefixed `r_` or `ref_`;
the original tables and views are unchanged (v_summary still matches the MySQL results).

| Object | What it is |
|---|---|
| `r_parcel_clean` | One row per residential parcel with cleaned tenure, owner type, vacant/condo/common-area flags, recent-sale flags, best owner-occupancy, age/income proven by existing codes, value decile, and `in_analysis_universe`. |
| `r_data_quality` | Counts of every problem found and how it was handled. |
| `ref_exemption_rules` | Official city and county exemption terms, plus the amount seen on 2026 bills. |
| `ref_tax_rates` | 2026 city tax rates by levy, read from the bills. |
| `r_city_levy_2026` | Per-parcel 2026 bill: assessed value and exempt value on the general and school levies (first-half bill). |
| `r_gap_candidates` | One row per parcel per missing exemption: tier, status, strength, evidence, and `est_annual_homeowner_savings_city_tax` (unclaimed relief). |
| `r_gap_parcels` | Gap rows joined to address, owner, value decile, tenure. Start here for lists. |
| `r_gap_summary`, `r_gap_by_decile` | Counts and unclaimed relief (city tax) by gap type and by value decile. |
| `r_goal2_clean` | The "likely senior, filed nowhere" list rebuilt on cleaned data, with 20+/30+ year and bottom 10/20/30% flags. |
| `r_dictionary`, `r_settings` | Column notes and build settings. |

Tiers: A = age proven by an existing code, a city benefit missing. B = basic homestead filed with only one
office. C = likely senior, filed nowhere (population estimate; strength high/medium/low). D = county senior tier
missing (small dollars for Decatur residents).

Dollars are **unclaimed relief**: what the homeowner would save per year on their City of Decatur tax bill by
filing the missing exemption. They are not county tax, and they are not money the city "saves"; exemptions only
apply once filed, so these owners are paying more than they need to, not being billed in error.
Method: exempt value x 2026 city tax rate, capped at the taxable value left. Checked against the
credits the city actually applied (city bills are semiannual; 2 x first-half credit matched on 99.8% of
GH-1, GH-2, GH-3 and S-3 bills).

Known limits: county-side dollars are not computed (county bills are not in the database). County code H6
is labelled "Sr 65" by the county but its 2026 sheet lists age 62 and 65, so 62 is used. On city bills S-3
already includes S-6 ($250,000 total).

Example queries:
```sql
SELECT * FROM r_gap_summary;
SELECT * FROM r_gap_by_decile;
SELECT * FROM r_gap_parcels WHERE tier IN ('A','B') AND status='proven' ORDER BY est_annual_homeowner_savings_city_tax DESC;
SELECT * FROM r_data_quality;
```

## Update: age floors, county dollars, filing rates

- **County codes fixed:** county codes now come from the county profile page, which matches the county
  history on every parcel. The original exemptions-page scrape missed 77 parcels (H6IF, LDF, H6DF, H5WS).
  The old value is kept in `r_parcel_clean.county_codes_exemptions_page`.
- **Age floors:** `age_floor_now` = the code's minimum age + years the senior code has been held (county
  grant year, cross-checked with the 2019-2026 county history; 93% agreement). `age_proven_now` is the
  higher of that and the age the codes alone prove. It newly proves 9 households are 70+.
- **County dollars:** `est_annual_homeowner_savings_county_tax` = basic exemption credit + HOST/EHOST
  homestead credit, estimated from what 600 recent county filers receive (parameters in `r_settings`).
  Checked on 1,117 homesteads: median error 7%, totals ~7% high. Freeze growth and the state HTRG grant
  are excluded.
- **`r_filing_rates`:** among likely owner-occupied homes, the share with a basic homestead at both
  offices, city only, county only, or neither, by value decile, property type, owner type, purchase year
  and length of ownership.
- **`r_senior_takeup`:** among households whose age (and income) is proven by **county** records only, the
  share claiming each city senior benefit. Using county evidence only avoids circularity.


## Census data (added 2026-09-27)

Additions only. No existing table or view was changed. All 36 pre-existing objects were fingerprinted before and after the load and matched. A restore point was saved first as `decatur_tax.backup-before-census-2026-09-27.sqlite`.

**Sources** (official Census, no API key; details in `census_sources`):
- ACS 2020-2024 five-year estimates, with 90% margins of error, for Decatur city and the 13 DeKalb tracts that touch it.
- 2020 Census block counts (DHC) for the 308 blocks inside Decatur, used to weight edge tracts by their share inside the city.
- 2024 TIGER tract boundaries, used to place each parcel in a tract.

**New tables:** `census_sources`, `census_variables` (labels), `census_acs_values`, `census_dhc_values`, `census_tracts` (city-share weights and outlines), `census_parcel_tract` (parcel to tract), `census_city_benchmarks`, `census_tract_benchmarks`.

**New views:**
- `census_takeup_check`: Census counts compared with exemption records, citywide.
- `census_tract_takeup`: the same comparison by tract (the six core tracts lie entirely inside the city).
- `census_decatur_profile`: senior profile, including living alone, income bands, cost burden and internet access.
- `census_records_citywide`: the record counts used in the comparisons.

**Snapshots:** each `r_*` table and view was copied to `*_v1` so later revisions can be compared with today's results.

**Scripts:** `census/build_census_stage.py` builds `census/census_stage.sqlite` from the fetched files; `census/load_census.py` copies it in. Re-runnable; it only replaces `census_*` objects.

**Headline check:** exemption records prove an owner is 65+ on 1,633 parcels, while the Census counts about 1,323 +/- 212 owner households with a 65+ householder (1,363 in the 2020 count). The records are about 23% higher (6-47% given the margin of error). Tenure agrees closely: 521 likely owner-occupied parcels have tenure starting before 1990, against the Census's 494 +/- 103 owners who moved in before 1990.


### Follow-up checks (added 2026-09-27, later)

Script: `census/census_step12.py`, additions only. It adds the 2020 P19 counts (households with anyone 65+) and these new tables:
- `census_excess_decomposition` explains why records show more 65+ owners than the Census: 1,323 Census householders 65+, plus about 139 homes where a 65+ spouse or co-owner lives with a younger householder, plus 129 owners 65+ who moved in 2023 or later (too recent for the ACS). That leaves a remainder of about 42, well inside the margin of error.
- `census_cohort_check` compares 65+ owners with proven-65+ records by move-in period.
- `census_stale_checks`: evidence of stale exemptions is small. About 6 of 286 homes sold in 2025 still carry a city senior exemption with no county senior exemption, and 1 proven-65+ exemption is held by an estate. The 174 trust-held exemptions are routine living trusts.
- `census_unfiled_senior_estimate` and `census_unfiled_by_cohort`: a Census-based estimate of 65+ owner households with no senior exemption. About 150 (90% range 30-330) counting by move-in period, or 0-230 when periods are netted against each other, versus the 1,526 flagged by the Tier C rule.
- `census_priority_long_tenure`: 69 owner-occupied homes held since before 1990 with no record proving 65+ (63 with no senior code at all). The ACS says about 9 in 10 such owners are 65+, so this is the most likely group of unfiled seniors.


## Supabase (added 2026-10-06)

The database now also lives in the Supabase project `decatur-exemptions`, in private schemas (`raw`, `analysis`, `census`, `geo`, `share`) that aren't exposed through the API. Everything was verified against this SQLite file: all 50 table counts, `v_summary` and the Census checks match. Full details are in `supabase_export/SUPABASE.md`; the export and reload tools are in `supabase_export/`. This SQLite file remains the archive.


## Data pull v2 (added 2026-10-06)

`pull_v2/` holds rewritten pull scripts that write straight into the Supabase database. See `pull_v2/README.md` for run steps. Compared with the original scripts, they detect blocks and never mark a blocked item done, fetch only what is missing or out of date, keep a daily request budget, and copy each table into the `archive` schema before changing it. The original project in Downloads is unchanged.

After the v2 scripts have been used, don't rerun `supabase_export/run_load.sh`: it would replace the newer data with the September 2026 SQLite copy.
