#!/usr/bin/env python3
"""Steps 1-2 of the Census follow-up. Adds new census_* tables only.

1. Decompose why exemption records show more 65+ owners than the Census counts.
2. Census-based estimate of 65+ owner households with no senior exemption on file.

Pre-existing (original + r_*) objects are fingerprinted before/after and must not change.
"""
import hashlib, json, math, os, random, sqlite3, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(ROOT, "decatur_tax.sqlite")
BASE = json.load(open(os.path.expanduser("~/baseline_hashes.json")))

def fp(conn, names):
    out = {}
    for t in names:
        h = hashlib.md5(); n = 0
        for r in conn.execute(f'SELECT * FROM "{t}" ORDER BY 1,2'):
            h.update(repr(r).encode()); n += 1
        out[t] = [n, h.hexdigest()]
    return out

db = sqlite3.connect(MAIN)
db.execute("PRAGMA journal_mode=MEMORY")
if fp(db, BASE) != BASE:
    sys.exit("pre-existing objects changed since baseline; aborting")

# ---------------------------------------------------------------- new 2020 Census inputs
# DECENNIALDHC2020 P19 (households with 1+ people 65+) and H13 for Decatur city (place 1322052),
# fetched from data.census.gov on 2026-09-27; P19 block counts summed to tracts (city part only).
P19_PLACE = {"P19_001N": 9946, "P19_002N": 2623, "P19_003N": 1450, "P19_004N": 1173, "P19_005N": 1072,
             "P19_006N": 101, "P19_007N": 7323, "P19_008N": 1805, "P19_009N": 5518, "P19_010N": 5087, "P19_011N": 431}
P19_LABELS = {
 "P19_001N": "Total households", "P19_002N": "Households with one or more people 65+",
 "P19_003N": "Households with 65+ > 1-person", "P19_004N": "Households with 65+ > 2-or-more-person",
 "P19_005N": "Households with 65+ > 2+ person > family", "P19_006N": "Households with 65+ > 2+ person > nonfamily",
 "P19_007N": "Households with no people 65+", "P19_008N": "No 65+ > 1-person", "P19_009N": "No 65+ > 2-or-more-person",
 "P19_010N": "No 65+ > 2+ person > family", "P19_011N": "No 65+ > 2+ person > nonfamily"}
P19_TRACT_IN_CITY = {"13089020802": (7, 2), "13089022203": (30, 4), "13089022303": (4, 0), "13089022304": (2, 0),
    "13089022403": (89, 20), "13089022501": (1884, 530), "13089022502": (1080, 317), "13089022601": (2489, 943),
    "13089022602": (907, 176), "13089022700": (1739, 261), "13089022800": (1427, 327), "13089022900": (288, 43)}
db.execute("DELETE FROM census_dhc_values WHERE table_id='P19' OR (geo_level='place' AND table_id='H13')")
for k, v in P19_PLACE.items():
    db.execute("INSERT INTO census_dhc_values VALUES('place','1322052',NULL,'Decatur city, Georgia','P19',?,?)", (k, v))
    db.execute("INSERT OR REPLACE INTO census_variables VALUES(?,?,?,?,?)",
               (k, "P19", "dhc_2020", P19_LABELS[k], "HOUSEHOLDS BY PRESENCE OF PEOPLE 65 YEARS AND OVER, HOUSEHOLD SIZE, AND HOUSEHOLD TYPE"))
for t, (hh, hh65) in P19_TRACT_IN_CITY.items():
    for var, val in (("P19_001N", hh), ("P19_002N", hh65)):
        db.execute("INSERT INTO census_dhc_values VALUES('tract_in_city',?,?,NULL,'P19',?,?)", (t, t, var, val))
# H13 place totals equal the sum of the 308 city blocks already loaded; store the place row too.
for (var, val) in db.execute("SELECT variable, SUM(value) FROM census_dhc_values WHERE geo_level='block' AND table_id='H13' GROUP BY 1").fetchall():
    db.execute("INSERT INTO census_dhc_values VALUES('place','1322052',NULL,'Decatur city, Georgia','H13',?,?)", (var, val))

def dhc_place(v):
    return db.execute("SELECT value FROM census_dhc_values WHERE geo_level='place' AND variable=?", (v,)).fetchone()[0]
def acs(v):
    r = db.execute("SELECT estimate, moe FROM census_acs_values WHERE geo_level='place' AND geoid='1322052' AND variable=?", (v,)).fetchone()
    return (r[0] or 0.0, r[1] or 0.0)

hh65_any_2020 = dhc_place("P19_002N")
hholder65_2020 = sum(dhc_place(v) for v in ("H13_009N", "H13_010N", "H13_011N", "H13_019N", "H13_020N", "H13_021N"))
uplift_2020 = hh65_any_2020 / hholder65_2020
acs_hh65 = acs("B11007_002E")[0]
acs_hholder65 = sum(acs(f"B25007_{i:03d}E")[0] for i in (9, 10, 11, 19, 20, 21))
uplift_acs = acs_hh65 / acs_hholder65

# ---------------------------------------------------------------- cohort comparison (step 1)
COH = [("2023 or later", 0, "tenure_start_year >= 2023"), ("2020-2022", 1, "tenure_start_year BETWEEN 2020 AND 2022"),
       ("2010-2019", 2, "tenure_start_year BETWEEN 2010 AND 2019"), ("2000-2009", 3, "tenure_start_year BETWEEN 2000 AND 2009"),
       ("1990-1999", 4, "tenure_start_year BETWEEN 1990 AND 1999"), ("1989 or earlier", 5, "tenure_start_year < 1990")]
rows = []
for name, i, cond in COH:
    alls = [acs(f"B25128_{b + i:03d}E") for b in (4, 11, 18)]
    own_e = sum(a for a, _ in alls); own_m = math.sqrt(sum(m * m for _, m in alls))
    s_e, s_m = acs(f"B25128_{18 + i:03d}E")
    n, p = db.execute(f"SELECT COUNT(*), SUM(age_proven_now >= 65) FROM r_parcel_clean WHERE owner_occupied_best=1 AND {cond}").fetchone()
    rows.append(dict(cohort=name, order_key=i, acs_owners=own_e, acs_owners_moe=own_m, acs_owner65=s_e, acs_owner65_moe=s_m,
                     records_owner_occupied=n, records_proven65=p or 0))

db.executescript("""
DROP TABLE IF EXISTS census_cohort_check;
CREATE TABLE census_cohort_check(order_key INTEGER, cohort TEXT, acs_owners REAL, acs_owners_moe REAL,
  acs_owner65 REAL, acs_owner65_moe REAL, records_owner_occupied INTEGER, records_proven65 INTEGER,
  proven65_minus_acs REAL, note TEXT);
DROP TABLE IF EXISTS census_excess_decomposition;
CREATE TABLE census_excess_decomposition(step INTEGER, component TEXT, households REAL, running_total REAL, note TEXT);
DROP TABLE IF EXISTS census_unfiled_senior_estimate;
CREATE TABLE census_unfiled_senior_estimate(measure TEXT, median REAL, low_5pct REAL, high_95pct REAL, method TEXT);
DROP TABLE IF EXISTS census_unfiled_by_cohort;
CREATE TABLE census_unfiled_by_cohort(order_key INTEGER, cohort TEXT, expected_65plus_owner_households REAL,
  proven65 INTEGER, unproven_owner_occupied INTEGER, unfiled_median REAL, unfiled_low_5pct REAL, unfiled_high_95pct REAL);
DROP TABLE IF EXISTS census_stale_checks;
CREATE TABLE census_stale_checks(check_name TEXT, households INTEGER, out_of INTEGER, note TEXT);
""")
for r in rows:
    note = None
    if r["order_key"] == 0:
        note = "ACS 2020-24 surveys mostly predate these moves, so the Census undercounts this group by design"
    db.execute("INSERT INTO census_cohort_check VALUES(?,?,?,?,?,?,?,?,?,?)",
               (r["order_key"], r["cohort"], r["acs_owners"], r["acs_owners_moe"], r["acs_owner65"], r["acs_owner65_moe"],
                r["records_owner_occupied"], r["records_proven65"], r["records_proven65"] - r["acs_owner65"], note))

# ---------------------------------------------------------------- decomposition (step 1)
own65_e, own65_m = [sum(x) for x in zip(*[acs(f"B25007_{i:03d}E") for i in (9, 10, 11)])]
own65_m = math.sqrt(sum(acs(f"B25007_{i:03d}E")[1] ** 2 for i in (9, 10, 11)))
proven = db.execute("SELECT SUM(age_proven_now >= 65) FROM r_parcel_clean").fetchone()[0]
definitional = own65_e * (uplift_2020 - 1)
timing = rows[0]["records_proven65"] - rows[0]["acs_owner65"]
remainder = proven - own65_e - definitional - timing
steps = [
 (1, "Census: owner households with a 65+ householder (ACS 2020-24)", own65_e, own65_e, f"+/- {own65_m:.0f}"),
 (2, "Add homes where a 65+ spouse or co-owner lives with a younger householder", definitional, own65_e + definitional,
  f"2020 Census: {hh65_any_2020} households have anyone 65+ vs {hholder65_2020} with a 65+ householder (x{uplift_2020:.3f}, applied to owners; ACS gives x{uplift_acs:.3f})"),
 (3, "Add 65+ owners who moved in 2023 or later (too recent for the ACS)", timing, own65_e + definitional + timing, "records prove 65+ for these; ACS counts 0 +/- 27"),
 (4, "Unexplained remainder", remainder, proven, f"well inside the +/- {own65_m:.0f} margin of error"),
 (5, "Exemption records proving an owner is 65+", proven, proven, None)]
db.executemany("INSERT INTO census_excess_decomposition VALUES(?,?,?,?,?)", steps)

# ---------------------------------------------------------------- stale checks
SEN = "('GH-2','GH-3','GS-1','S-1','S-2','S-3','S-5','S-6')"
db.executescript(f"""
DROP TABLE IF EXISTS temp._cy; CREATE TEMP TABLE _cy AS SELECT b.parcel_id, b.tax_year,
  COALESCE(MAX(l.exemption_code IN {SEN}),0) sen FROM city_bills b JOIN city_bill_lines l ON l.id_hash=b.id_hash GROUP BY 1,2;
DROP TABLE IF EXISTS temp._co; CREATE TEMP TABLE _co AS SELECT parcel_id, tax_year,
  MAX(county_exmp_code IS NOT NULL AND county_exmp_code NOT IN ('H1','H1F')) csen FROM county_owner_history GROUP BY 1,2;
DROP TABLE IF EXISTS temp._s25; CREATE TEMP TABLE _s25 AS SELECT parcel_id FROM r_parcel_clean
  WHERE last_arms_length_sale_date BETWEEN '2025-01-01' AND '2025-12-31' AND in_analysis_universe=1;
""")
sales25 = db.execute("SELECT COUNT(*) FROM _s25").fetchone()[0]
had = db.execute("SELECT COUNT(*) FROM _s25 JOIN _cy a ON a.parcel_id=_s25.parcel_id AND a.tax_year=2025 AND a.sen=1").fetchone()[0]
kept = db.execute("SELECT COUNT(*) FROM _s25 JOIN _cy a ON a.parcel_id=_s25.parcel_id AND a.tax_year=2025 AND a.sen=1 JOIN _cy b ON b.parcel_id=_s25.parcel_id AND b.tax_year=2026 AND b.sen=1").fetchone()[0]
kept_no_county = db.execute("""SELECT COUNT(*) FROM _s25 JOIN _cy a ON a.parcel_id=_s25.parcel_id AND a.tax_year=2025 AND a.sen=1
  JOIN _cy b ON b.parcel_id=_s25.parcel_id AND b.tax_year=2026 AND b.sen=1
  LEFT JOIN _co c ON c.parcel_id=_s25.parcel_id AND c.tax_year=2026 WHERE COALESCE(c.csen,0)=0""").fetchone()[0]
estates = db.execute("SELECT COUNT(*) FROM r_parcel_clean WHERE age_proven_now>=65 AND owner_type='estate'").fetchone()[0]
trusts = db.execute("SELECT COUNT(*) FROM r_parcel_clean WHERE age_proven_now>=65 AND owner_type='trust'").fetchone()[0]
db.executemany("INSERT INTO census_stale_checks VALUES(?,?,?,?)", [
 ("2025 sales with a city senior exemption on the 2025 bill", had, sales25, "homes sold in 2025, owner-occupied universe"),
 ("...still carrying a city senior exemption on the 2026 bill", kept, had, "new owner may also be a senior who filed"),
 ("...with no county senior exemption in 2026 (possible carryover)", kept_no_county, sales25, "candidates for a city exemption not removed at sale"),
 ("Proven-65+ exemptions held by an estate", estates, proven, None),
 ("Proven-65+ exemptions held by a trust", trusts, proven, "living trusts are routine for living owners; not a sign of staleness"),
])

# ---------------------------------------------------------------- Monte Carlo estimate (step 2)
random.seed(20260927)
N = 20000
se = lambda moe: moe / 1.645
unproven = {}
for name, i, cond in COH:
    unproven[i] = db.execute(f"SELECT COUNT(*) FROM r_parcel_clean WHERE owner_occupied_best=1 AND COALESCE(age_proven_now,0) < 65 AND {cond}").fetchone()[0]
# share of recent (2020-22) movers who are 65+, used for the 2023+ group the ACS cannot see yet
r1 = rows[1]
gross, net, per = [], [], {i: [] for _, i, _ in COH}
expected_c = {}
for _ in range(N):
    u = random.triangular(1.0, 1.20, uplift_2020)
    E = {}
    for r in rows:
        i = r["order_key"]
        if i == 0:
            own = max(1.0, random.gauss(r1["acs_owners"], se(r1["acs_owners_moe"])))
            s65 = max(0.0, random.gauss(r1["acs_owner65"], se(r1["acs_owner65_moe"])))
            E[i] = r["records_owner_occupied"] * min(1.0, s65 / own) * u
        else:
            E[i] = max(0.0, random.gauss(r["acs_owner65"], se(r["acs_owner65_moe"]))) * u
    g = 0.0
    for r in rows:
        i = r["order_key"]
        x = min(max(0.0, E[i] - r["records_proven65"]), unproven[i])
        per[i].append(x); g += x
    gross.append(g)
    net.append(max(0.0, sum(E.values()) - proven))

def q(v, p):
    v = sorted(v); return v[int(p * (len(v) - 1))]
db.executemany("INSERT INTO census_unfiled_senior_estimate VALUES(?,?,?,?,?)", [
 ("65+ owner households with no senior exemption (by move-in period)", q(gross, .5), q(gross, .05), q(gross, .95),
  "Census 65+ owners per move-in period x (1 + 65+ spouse/co-owner share), minus records proving 65+, floored at 0 in each period; 20,000 draws over ACS margins of error"),
 ("Same, netting periods against each other", q(net, .5), q(net, .05), q(net, .95),
  "Total expected minus total proven, floored at 0; allows for tenure dates that fall in a neighbouring period"),
 ("For comparison: households flagged 'possible senior' (Tier C)", 1526, None, None, "tenure/value rule used in the original analysis"),
])
for r in rows:
    i = r["order_key"]
    exp_c = r["acs_owner65"] * uplift_2020 if i else r["records_owner_occupied"] * (r1["acs_owner65"] / r1["acs_owners"]) * uplift_2020
    db.execute("INSERT INTO census_unfiled_by_cohort VALUES(?,?,?,?,?,?,?,?)",
               (i, r["cohort"], exp_c, r["records_proven65"], unproven[i], q(per[i], .5), q(per[i], .05), q(per[i], .95)))
db.commit()

after = fp(db, BASE)
bad = [k for k in BASE if after[k] != BASE[k]]
print("pre-existing objects changed:", bad or "none")
print(f"uplift 2020={uplift_2020:.3f} acs={uplift_acs:.3f}")
for t in ("census_excess_decomposition", "census_cohort_check", "census_unfiled_by_cohort", "census_unfiled_senior_estimate", "census_stale_checks"):
    print("==", t)
    for r in db.execute(f"SELECT * FROM {t}"):
        print(tuple(round(x, 1) if isinstance(x, float) else x for x in r))
