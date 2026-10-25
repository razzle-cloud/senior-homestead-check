#!/usr/bin/env python3
"""Build census_stage.sqlite: net-new census_ tables for the Decatur project.

Inputs (fetched from official Census sources, no API key):
  census_export.json  ACS 2020-2024 5-year tables (tract + Decatur city) and
                      2020 Census DHC tables (blocks inside Decatur + tracts),
                      from data.census.gov
  labels.json         variable labels, from api.census.gov metadata
  tracts.geojson      2024 tract boundaries, from TIGERweb
  ../map/geo.json     parcel points (parcel_id, lat, lon) already used by the map
"""
import json, sqlite3, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "census_stage.sqlite")
E = json.load(open(os.path.join(HERE, "census_export.json")))
L = json.load(open(os.path.join(HERE, "labels.json")))
T = json.load(open(os.path.join(HERE, "tracts.geojson")))
P = json.load(open(os.path.join(HERE, "..", "map", "geo.json")))["parcels"]

ACS_SRC = "ACS 2020-2024 5-year (data.census.gov ACSDT5Y2024)"
DHC_SRC = "2020 Census DHC (data.census.gov DECENNIALDHC2020)"

if os.path.exists(OUT):
    os.remove(OUT)
db = sqlite3.connect(OUT)
db.executescript("""
CREATE TABLE census_sources(source_key TEXT PRIMARY KEY, description TEXT, url TEXT, fetched TEXT, notes TEXT);
CREATE TABLE census_variables(variable TEXT PRIMARY KEY, table_id TEXT, dataset TEXT, label TEXT, concept TEXT);
CREATE TABLE census_acs_values(geo_level TEXT, geoid TEXT, geo_name TEXT, table_id TEXT, variable TEXT,
    estimate REAL, moe REAL, PRIMARY KEY(geo_level, geoid, variable));
CREATE TABLE census_dhc_values(geo_level TEXT, geoid TEXT, tract_geoid TEXT, geo_name TEXT, table_id TEXT,
    variable TEXT, value REAL, PRIMARY KEY(geo_level, geoid, variable));
CREATE TABLE census_tracts(tract_geoid TEXT PRIMARY KEY, tract_name TEXT, land_area_sqm REAL,
    blocks_in_city INTEGER, hh_2020_tract REAL, hh_2020_in_city REAL,
    owner_hh_2020_tract REAL, owner_hh_2020_in_city REAL,
    owner_65plus_2020_tract REAL, owner_65plus_2020_in_city REAL,
    city_share_owner_hh REAL, city_share_owner_65plus REAL, city_parcels INTEGER,
    geometry_geojson TEXT);
CREATE TABLE census_parcel_tract(parcel_id TEXT PRIMARY KEY, tract_geoid TEXT, lat REAL, lon REAL, method TEXT);
""")

def num(v):
    if v in (None, "", "null"):
        return None
    try:
        x = float(v)
    except ValueError:
        return None
    # Census uses large negative sentinels (e.g. -666666666) for "not available"
    return None if x <= -555555555 else x

# ---- variables
for k, (lab, con) in L["acs"].items():
    db.execute("INSERT OR REPLACE INTO census_variables VALUES(?,?,?,?,?)",
               (k, k.split("_")[0], "acs5_2024", lab.replace("Estimate!!", "").replace("!!", " > "), con))
for k, (lab, con) in L["dhc"].items():
    db.execute("INSERT OR REPLACE INTO census_variables VALUES(?,?,?,?,?)",
               (k, k.split("_")[0], "dhc_2020", lab.strip().lstrip("!").replace("!!", " > ").strip(), con))

# ---- ACS values (tract + place)
for level_key, level in (("acs_tract", "tract"), ("acs_place", "place")):
    for tbl, blob in E[level_key].items():
        cols = blob["cols"]
        gi, ni = cols.index("GEO_ID"), cols.index("NAME")
        ests = [c for c in cols if c.endswith("E") and "_" in c]
        for r in blob["rows"]:
            geo = r[gi].split("US")[-1]
            for c in ests:
                m = c[:-1] + "M"
                est = num(r[cols.index(c)])
                moe = num(r[cols.index(m)]) if m in cols else None
                db.execute("INSERT INTO census_acs_values VALUES(?,?,?,?,?,?,?)",
                           (level, geo, r[ni], tbl, c, est, moe))

# ---- DHC values (blocks in city + whole tracts)
for level_key, level in (("dhc_block", "block"), ("dhc_tract", "tract")):
    for tbl, blob in E[level_key].items():
        cols = blob["cols"]
        gi, ni = cols.index("GEO_ID"), cols.index("NAME")
        vs = [c for c in cols if c.endswith("N") and "_" in c]
        for r in blob["rows"]:
            geo = r[gi].split("US")[-1]
            for c in vs:
                db.execute("INSERT INTO census_dhc_values VALUES(?,?,?,?,?,?,?)",
                           (level, geo, geo[:11], r[ni], tbl, c, num(r[cols.index(c)])))

# ---- point in polygon (ray casting, handles holes via even-odd over all rings)
def rings_of(geom):
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    return geom["coordinates"]

def inside(lon, lat, geom):
    hit = False
    for poly in rings_of(geom):
        for ring in poly:
            n = len(ring)
            j = n - 1
            for i in range(n):
                xi, yi = ring[i]; xj, yj = ring[j]
                if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
                    hit = not hit
                j = i
    return hit

feats = [(f["properties"]["GEOID"], f["geometry"]) for f in T["features"]]
unassigned = 0
for p in P:
    lat, lon = p.get("lat"), p.get("lon")
    tg = None
    if lat is not None and lon is not None:
        for g, geom in feats:
            if inside(lon, lat, geom):
                tg = g
                break
    if tg is None:
        unassigned += 1
    db.execute("INSERT OR REPLACE INTO census_parcel_tract VALUES(?,?,?,?,?)",
               (p["id"], tg, lat, lon, "parcel centroid in 2024 TIGER tract polygon"))

# ---- tract summary + city-share weights from 2020 blocks
def dhc(level, geoid_col_val, var, tract=None):
    if level == "tract":
        r = db.execute("SELECT value FROM census_dhc_values WHERE geo_level='tract' AND geoid=? AND variable=?",
                       (geoid_col_val, var)).fetchone()
        return r[0] if r else None
    r = db.execute("SELECT SUM(value) FROM census_dhc_values WHERE geo_level='block' AND tract_geoid=? AND variable=?",
                   (tract, var)).fetchone()
    return r[0]

for g, geom in feats:
    props = next(f["properties"] for f in T["features"] if f["properties"]["GEOID"] == g)
    nb = db.execute("SELECT COUNT(DISTINCT geoid) FROM census_dhc_values WHERE geo_level='block' AND tract_geoid=?", (g,)).fetchone()[0]
    hh_t, hh_c = dhc("tract", g, "H13_001N"), dhc("block", None, "H13_001N", g)
    o_t, o_c = dhc("tract", g, "H13_002N"), dhc("block", None, "H13_002N", g)
    s_t = sum((dhc("tract", g, v) or 0) for v in ("H13_009N", "H13_010N", "H13_011N"))
    s_c = sum((dhc("block", None, v, g) or 0) for v in ("H13_009N", "H13_010N", "H13_011N"))
    npar = db.execute("SELECT COUNT(*) FROM census_parcel_tract WHERE tract_geoid=?", (g,)).fetchone()[0]
    db.execute("INSERT INTO census_tracts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
               (g, props["NAME"], props.get("AREALAND"), nb, hh_t, hh_c, o_t, o_c, s_t, s_c,
                (o_c / o_t) if o_t else None, (s_c / s_t) if s_t else None, npar, json.dumps(geom)))

db.executemany("INSERT INTO census_sources VALUES(?,?,?,?,?)", [
    ("acs5_2024", ACS_SRC, "https://data.census.gov (api/access/data/table?id=ACSDT5Y2024.<table>)", "2026-09-27",
     "Tract estimates for the 13 DeKalb tracts that touch Decatur, and Decatur city (place 1322052). Estimates with 90% margins of error."),
    ("dhc_2020", DHC_SRC, "https://data.census.gov (api/access/data/table?id=DECENNIALDHC2020.<table>)", "2026-09-27",
     "Block counts for the 308 blocks inside Decatur and totals for the same 13 tracts. Used to weight tracts by the share inside the city. Census applies differential-privacy noise to block counts."),
    ("tiger_2024", "TIGERweb ACS2024 Census Tracts (layer 8)", "https://tigerweb.geo.census.gov", "2026-09-27",
     "Tract boundaries used to place each parcel in a tract."),
    ("labels", "Census API variable metadata", "https://api.census.gov/data/2024/acs/acs5/groups/<table>.json", "2026-09-27",
     "Labels only; the metadata endpoints do not need an API key."),
])
db.commit()
for t in ("census_variables", "census_acs_values", "census_dhc_values", "census_tracts", "census_parcel_tract"):
    print(t, db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
print("parcels without tract:", unassigned)
for r in db.execute("SELECT tract_geoid, tract_name, blocks_in_city, city_parcels, owner_hh_2020_tract, owner_hh_2020_in_city, round(city_share_owner_hh,3), owner_65plus_2020_in_city FROM census_tracts ORDER BY 1"):
    print(r)

# ======================================================================
# Derived benchmarks (sums and shares with correct Census MOE formulas)
# ======================================================================
import math
db.executescript("""
CREATE TABLE census_city_benchmarks(measure_key TEXT PRIMARY KEY, measure TEXT, universe TEXT,
    acs_estimate REAL, acs_moe REAL, acs_universe REAL, acs_share REAL, acs_share_moe REAL,
    dhc_2020 REAL, variables TEXT, note TEXT);
CREATE TABLE census_tract_benchmarks(tract_geoid TEXT, measure_key TEXT, acs_estimate REAL, acs_moe REAL,
    city_share REAL, acs_in_city REAL, acs_in_city_moe REAL, dhc_2020_in_city REAL,
    PRIMARY KEY(tract_geoid, measure_key));
""")

def acs(level, geoid, v):
    r = db.execute("SELECT estimate, moe FROM census_acs_values WHERE geo_level=? AND geoid=? AND variable=?",
                   (level, geoid, v)).fetchone()
    return (r[0] or 0.0, r[1] or 0.0) if r else (0.0, 0.0)

def acs_sum(level, geoid, vs):
    e = m2 = 0.0
    for v in vs:
        a, b = acs(level, geoid, v); e += a; m2 += b * b
    return e, math.sqrt(m2)

def share_moe(x, mx, y, my):
    if not y:
        return None, None
    p = x / y
    inner = mx * mx - p * p * my * my
    if inner < 0:                      # Census rule: use the ratio formula when negative
        inner = mx * mx + p * p * my * my
    return p, math.sqrt(inner) / y

def dhc_city(vs):
    return db.execute(f"SELECT SUM(value) FROM census_dhc_values WHERE geo_level='block' AND variable IN ({','.join('?'*len(vs))})", vs).fetchone()[0]

PLACE = "1322052"
own65 = ["B25007_009E", "B25007_010E", "B25007_011E"]
pre90 = [f"B25128_{i:03d}E" for i in (9, 16, 23)]          # owner, moved in 1989 or earlier, each age band
spec = [
 # key, measure, universe, numerator vars, denominator vars, dhc vars, note
 ("owner_hh", "Owner-occupied households", "all households", ["B25003_002E"], ["B25003_001E"], ["H13_002N"], None),
 ("owner_60_64", "Owner households, householder 60-64", "owner households", ["B25007_008E"], ["B25007_002E"], ["H13_008N"], "62+ exemptions start inside this band"),
 ("owner_65plus", "Owner households, householder 65+", "owner households", own65, ["B25007_002E"], ["H13_009N","H13_010N","H13_011N"], "Main benchmark for senior take-up"),
 ("owner_75plus", "Owner households, householder 75+", "owner households", ["B25007_010E","B25007_011E"], ["B25007_002E"], ["H13_010N","H13_011N"], None),
 ("owner_85plus", "Owner households, householder 85+", "owner households", ["B25007_011E"], ["B25007_002E"], ["H13_011N"], None),
 ("owner_moved_pre1990", "Owner households that moved in before 1990 (all ages)", "owner households", pre90, ["B25128_002E"], None, "Tenure check"),
 ("owner65_moved_pre1990", "Owner households 65+ that moved in before 1990", "owner households that moved in before 1990", ["B25128_023E"], pre90, None, "Share of long-tenure owners who are 65+"),
 ("owner65_moved_pre2000", "Owner households 65+ that moved in before 2000", "owner households 65+", ["B25128_022E","B25128_023E"], ["B25128_017E"], None, None),
 ("hh65_any", "Households with anyone 65+", "all households", ["B11007_002E"], ["B11007_001E"], None, "All tenures"),
 ("hh65_alone", "People 65+ living alone (householders)", "households with anyone 65+", ["B11007_003E"], ["B11007_002E"], None, "All tenures; hardest to reach"),
 ("hh65_income_lt25k", "Householders 65+ with household income under $25k", "householders 65+", [f"B19037_{i:03d}E" for i in range(54,58)], ["B19037_053E"], None, "All tenures; near the GS-1 household limit ($25k)"),
 ("hh65_income_lt60k", "Householders 65+ with household income under $60k", "householders 65+", [f"B19037_{i:03d}E" for i in range(54,64)], ["B19037_053E"], None, "All tenures; near the GH-3/S-5 limits (~$60-62k, different income bases)"),
 ("owner65_cost_burden_30", "Owners 65+ spending 30%+ of income on housing", "owner householders 65+", ["B25093_027E","B25093_028E"], ["B25093_023E"], None, None),
 ("owner65_cost_burden_35", "Owners 65+ spending 35%+ of income on housing", "owner householders 65+", ["B25093_028E"], ["B25093_023E"], None, None),
 ("pop65_no_internet", "People 65+ with no computer or no internet subscription", "people 65+ in households", ["B28005_018E","B28005_019E"], ["B28005_014E"], None, "Barrier to online filing"),
 ("median_home_value", "Median value, owner-occupied homes", None, ["B25077_001E"], None, None, "Median; not additive"),
 ("median_income_hh65", "Median household income, householder 65+", None, ["B19049_005E"], None, None, "Median; not additive"),
]
for key, meas, uni, nv, dv, hv, note in spec:
    e, m = acs_sum("place", PLACE, nv)
    ue = um = p = pm = None
    if dv:
        ue, um = acs_sum("place", PLACE, dv)
        p, pm = share_moe(e, m, ue, um)
    d = dhc_city(hv) if hv else None
    db.execute("INSERT INTO census_city_benchmarks VALUES(?,?,?,?,?,?,?,?,?,?,?)",
               (key, meas, uni, e, m, ue, p, pm, d, ",".join(nv), note))

for (g, share, share65) in db.execute("SELECT tract_geoid, city_share_owner_hh, city_share_owner_65plus FROM census_tracts").fetchall():
    for key, vs, sh, hv in (("owner_hh", ["B25003_002E"], share, ["H13_002N"]),
                            ("owner_65plus", own65, share65 if share65 is not None else share, ["H13_009N","H13_010N","H13_011N"])):
        e, m = acs_sum("tract", g, vs)
        sh = sh or 0.0
        d = db.execute(f"SELECT SUM(value) FROM census_dhc_values WHERE geo_level='block' AND tract_geoid=? AND variable IN ({','.join('?'*len(hv))})", [g]+hv).fetchone()[0]
        db.execute("INSERT INTO census_tract_benchmarks VALUES(?,?,?,?,?,?,?,?)", (g, key, e, m, sh, e*sh, m*sh, d))
db.commit()
for r in db.execute("SELECT measure_key, round(acs_estimate), round(acs_moe), round(acs_share,3), round(acs_share_moe,3), dhc_2020 FROM census_city_benchmarks"):
    print(r)
