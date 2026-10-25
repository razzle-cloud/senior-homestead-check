#!/usr/bin/env python3
"""Load census_ tables into decatur_tax.sqlite, adding objects only.

Safety:
  * refuses to run unless the backup file exists
  * copies only objects named census_* and creates *_v1 snapshots (never overwrites them)
  * never ALTERs, UPDATEs or DROPs any pre-existing table or view
  * afterwards re-fingerprints every pre-existing object and compares with the baseline
Re-runnable: drops and recreates only census_* objects.
"""
import hashlib, json, os, sqlite3, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MAIN = os.path.join(ROOT, "decatur_tax.sqlite")
BACKUP = os.path.join(ROOT, "decatur_tax.backup-before-census-2026-09-27.sqlite")
STAGE = os.path.join(HERE, "census_stage.sqlite")
BASELINE = os.path.expanduser("~/baseline_hashes.json")

for p in (MAIN, BACKUP, STAGE, BASELINE):
    if not os.path.exists(p):
        sys.exit(f"missing {p}; aborting")

def fingerprints(conn, names):
    out = {}
    for t in names:
        h = hashlib.md5(); n = 0
        for r in conn.execute(f'SELECT * FROM "{t}" ORDER BY 1,2'):
            h.update(repr(r).encode()); n += 1
        out[t] = [n, h.hexdigest()]
    return out

base = json.load(open(BASELINE))
db = sqlite3.connect(MAIN)
db.execute("PRAGMA journal_mode=MEMORY")   # no journal file (folder does not allow deletes)

before = fingerprints(db, base.keys())
bad = [k for k in base if before[k] != base[k]]
if bad:
    sys.exit(f"pre-existing objects changed since baseline, aborting: {bad}")

# ---- drop previous census_ objects only
for typ, name in db.execute("SELECT type, name FROM sqlite_master WHERE name LIKE 'census\\_%' ESCAPE '\\' AND type IN ('view','table') ORDER BY type='table'").fetchall():
    db.execute(f'DROP {typ.upper()} "{name}"')

# ---- copy census_ tables from stage
db.execute("ATTACH DATABASE ? AS stage", (STAGE,))
for name, sql in db.execute("SELECT name, sql FROM stage.sqlite_master WHERE type='table' AND name LIKE 'census\\_%' ESCAPE '\\'").fetchall():
    db.execute(sql)
    db.execute(f'INSERT INTO main."{name}" SELECT * FROM stage."{name}"')
db.commit()
db.execute("DETACH DATABASE stage")

# ---- v1 snapshots of current results (created once, never overwritten)
existing = {r[0] for r in db.execute("SELECT name FROM sqlite_master")}
for name in ["r_parcel_clean", "r_gap_candidates", "r_filing_rates", "r_senior_takeup", "r_settings",
             "r_city_levy_2026", "r_gap_summary", "r_gap_by_decile", "r_gap_parcels", "r_goal2_clean", "r_data_quality"]:
    snap = name + "_v1"
    if snap not in existing:
        db.execute(f'CREATE TABLE "{snap}" AS SELECT * FROM "{name}"')
db.commit()

# ---- views
db.executescript("""
CREATE VIEW census_records_citywide AS
SELECT COUNT(*) AS residential_parcels,
       SUM(owner_occupied_best) AS likely_owner_occupied,
       SUM(has_city_basic OR has_county_basic OR has_city_senior OR has_county_senior) AS any_homestead,
       SUM(has_city_senior OR has_county_senior) AS any_senior_exemption,
       SUM(age_proven_now >= 65) AS records_prove_65plus,
       SUM(age_proven_now >= 75) AS records_prove_75plus,
       SUM(age_proven_now >= 85) AS records_prove_85plus,
       SUM(owner_occupied_best = 1 AND tenure_start_year < 1990) AS owner_occ_tenure_pre1990,
       SUM(owner_occupied_best = 1 AND tenure_start_year < 1990 AND age_proven_now >= 65) AS owner_occ_pre1990_proven65
FROM r_parcel_clean;

CREATE VIEW census_takeup_check AS
WITH r AS (SELECT * FROM census_records_citywide),
m(measure_key, comparison, records_definition, records) AS (
  SELECT 'owner_hh', 'homestead coverage', 'parcels with any homestead exemption (city or county)', any_homestead FROM r
  UNION ALL SELECT 'owner_hh', 'owner-occupancy check', 'parcels flagged likely owner-occupied (r_parcel_clean.owner_occupied_best)', likely_owner_occupied FROM r
  UNION ALL SELECT 'owner_65plus', 'senior coverage (strict)', 'parcels whose exemption records prove an owner is 65+ now', records_prove_65plus FROM r
  UNION ALL SELECT 'owner_65plus', 'senior coverage (broad)', 'parcels with any senior exemption, city or county (includes 62-64)', any_senior_exemption FROM r
  UNION ALL SELECT 'owner_75plus', 'senior coverage 75+ (lower bound)', 'parcels whose records prove an owner is 75+ now', records_prove_75plus FROM r
  UNION ALL SELECT 'owner_moved_pre1990', 'tenure check', 'likely owner-occupied parcels with tenure starting before 1990', owner_occ_tenure_pre1990 FROM r
)
SELECT b.measure_key, b.measure, m.comparison,
       ROUND(b.acs_estimate) AS acs_2024_estimate, ROUND(b.acs_moe) AS acs_moe_90,
       ROUND(b.acs_estimate - b.acs_moe) AS acs_low, ROUND(b.acs_estimate + b.acs_moe) AS acs_high,
       b.dhc_2020 AS census_2020_count,
       m.records_definition, m.records,
       ROUND(1.0 * m.records / b.acs_estimate, 3) AS records_per_census,
       ROUND(1.0 * m.records / (b.acs_estimate + b.acs_moe), 3) AS ratio_low,
       ROUND(1.0 * m.records / NULLIF(b.acs_estimate - b.acs_moe, 0), 3) AS ratio_high,
       ROUND(1.0 * m.records / NULLIF(b.dhc_2020, 0), 3) AS records_per_2020_count
FROM m JOIN census_city_benchmarks b USING (measure_key);

CREATE VIEW census_tract_takeup AS
WITH rec AS (
  SELECT t.tract_geoid,
         COUNT(*) AS residential_parcels,
         SUM(p.has_city_basic OR p.has_county_basic OR p.has_city_senior OR p.has_county_senior) AS any_homestead,
         SUM(p.age_proven_now >= 65) AS records_prove_65plus,
         SUM(p.has_city_senior OR p.has_county_senior) AS any_senior_exemption
  FROM census_parcel_tract t JOIN r_parcel_clean p USING (parcel_id)
  GROUP BY t.tract_geoid)
SELECT c.tract_geoid, c.tract_name, ROUND(c.city_share_owner_hh, 3) AS city_share,
       rec.residential_parcels,
       ROUND(h.acs_in_city) AS acs_owner_hh_in_city, ROUND(h.acs_in_city_moe) AS acs_owner_hh_moe, rec.any_homestead,
       ROUND(s.acs_in_city) AS acs_owner65_in_city, ROUND(s.acs_in_city_moe) AS acs_owner65_moe,
       s.dhc_2020_in_city AS census2020_owner65_in_city,
       rec.records_prove_65plus, rec.any_senior_exemption,
       ROUND(1.0 * rec.records_prove_65plus / NULLIF(s.acs_in_city, 0), 2) AS proven65_per_census65,
       CASE WHEN c.city_share_owner_hh >= 0.95 THEN 'core tract (entirely in city)'
            ELSE 'edge tract (mostly outside city; ratios unreliable)' END AS reliability
FROM census_tracts c
LEFT JOIN rec USING (tract_geoid)
LEFT JOIN census_tract_benchmarks h ON h.tract_geoid = c.tract_geoid AND h.measure_key = 'owner_hh'
LEFT JOIN census_tract_benchmarks s ON s.tract_geoid = c.tract_geoid AND s.measure_key = 'owner_65plus';

CREATE VIEW census_decatur_profile AS
SELECT measure_key, measure, universe, ROUND(acs_estimate) AS acs_2024_estimate, ROUND(acs_moe) AS acs_moe_90,
       ROUND(100 * acs_share, 1) AS pct_of_universe, ROUND(100 * acs_share_moe, 1) AS pct_moe_90,
       dhc_2020 AS census_2020_count, note
FROM census_city_benchmarks;
""")
db.commit()

# ---- verify
after = fingerprints(db, base.keys())
changed = [k for k in base if after[k] != base[k]]
new = sorted(r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')") if r[0] not in base and r[0] != "sqlite_stat1")
print("pre-existing objects checked:", len(base), "| changed:", changed or "none")
print("new objects:", new)
print("v_summary rows:", db.execute("SELECT COUNT(*) FROM v_summary").fetchone()[0])
db.close()
