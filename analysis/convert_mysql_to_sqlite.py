#!/usr/bin/env python3
"""
Convert the decatur_tax MySQL dump into a single SQLite file.

The MySQL dump is opened READ-ONLY and never modified. Output is a new file.

Usage:
  python3 convert_mysql_to_sqlite.py <path/to/decatur_tax.sql> <path/to/decatur_tax.sqlite>

What it does
  1. Recreates the 12 base tables with SQLite types (INTEGER / NUMERIC / TEXT),
     primary keys, unique keys and indexes.
  2. Loads every row from the dump's INSERT statements.
  3. Adds one helper table, derived_street_key, holding the street-name key that
     the MySQL street_key() function computed on the fly (SQLite has no stored
     functions). Nothing else is derived.
  4. Recreates the 9 analysis views from sql/analysis.sql, translated to SQLite
     SQL (GROUP_CONCAT, SUBSTRING_INDEX, LEAST, YEAR, CURDATE rewritten).
"""
import re, sqlite3, sys, os, time

src, dst = sys.argv[1], sys.argv[2]
if os.path.exists(dst):
    # rebuild in place: drop every existing object (no file deletion needed)
    _c = sqlite3.connect(dst)
    _c.execute('PRAGMA journal_mode=OFF')
    for typ, nm in _c.execute("SELECT type, name FROM sqlite_master WHERE type IN ('view','table') AND name NOT LIKE 'sqlite_%' ORDER BY type = 'table'").fetchall():
        _c.execute(f'DROP {typ.upper()} IF EXISTS "{nm}"')
    _c.commit(); _c.execute('VACUUM'); _c.close()
t0 = time.time()
with open(src, 'r', encoding='utf-8') as f:     # read-only
    txt = f.read()

db = sqlite3.connect(dst)
db.execute('PRAGMA journal_mode=OFF')
db.execute('PRAGMA synchronous=OFF')

def sqlite_type(mt):
    mt = mt.lower()
    if re.match(r'(big|small|tiny|medium)?int', mt): return 'INTEGER'
    if mt.startswith(('decimal', 'numeric', 'double', 'float')): return 'NUMERIC'
    return 'TEXT'   # char, varchar, text, date, datetime

# ---------------------------------------------------------------- tables
tables = {}
for m in re.finditer(r"CREATE TABLE `(\w+)` \((.*?)\n\) ENGINE[^\n]*", txt, re.S):
    name, body = m.group(1), m.group(2)
    cols, pk, idx, uniq, auto = [], None, [], [], None
    for line in body.split('\n'):
        line = line.strip().rstrip(',')
        if line.startswith('`'):
            cm = re.match(r"`(\w+)` (\w+(?:\([^)]*\))?)(.*)", line)
            c, t, rest = cm.groups()
            if 'AUTO_INCREMENT' in rest: auto = c
            cols.append((c, sqlite_type(t), 'NOT NULL' in rest))
        elif line.startswith('PRIMARY KEY'):
            pk = re.findall(r"`(\w+)`", line)
        elif line.startswith('UNIQUE KEY'):
            n, *cs = re.findall(r"`(\w+)`", line); uniq.append((n, cs))
        elif line.startswith('KEY'):
            n, *cs = re.findall(r"`(\w+)`", line); idx.append((n, cs))
    defs = []
    for c, t, nn in cols:
        if auto == c and pk == [c]:
            defs.append(f'"{c}" INTEGER PRIMARY KEY')
        else:
            defs.append(f'"{c}" {t}' + (' NOT NULL' if nn else ''))
    if pk and not (auto and pk == [auto]):
        defs.append('PRIMARY KEY (' + ','.join(f'"{c}"' for c in pk) + ')')
    for n, cs in uniq:
        defs.append('UNIQUE (' + ','.join(f'"{c}"' for c in cs) + ')')
    db.execute(f'CREATE TABLE "{name}" (\n  ' + ',\n  '.join(defs) + '\n)')
    for n, cs in idx:
        db.execute(f'CREATE INDEX "ix_{name}_{n}" ON "{name}" (' + ','.join(f'"{c}"' for c in cs) + ')')
    tables[name] = [c for c, _, _ in cols]

# ---------------------------------------------------------------- data
tok = re.compile(r"'((?:[^'\\]|\\.)*)'|(NULL)|(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)|(\()|(\))|,")
unesc_map = {'0': '\0', 'b': '\b', 'n': '\n', 'r': '\r', 't': '\t', 'Z': '\x1a'}
def unesc(s):
    if '\\' not in s: return s
    return re.sub(r'\\(.)', lambda m: unesc_map.get(m.group(1), m.group(1)), s)

counts = {}
for m in re.finditer(r"^INSERT INTO `(\w+)` VALUES (.*);$", txt, re.M):
    name, vals = m.group(1), m.group(2)
    rows, row, depth = [], None, 0
    for t in tok.finditer(vals):
        s, null, num, lp, rp = t.groups()
        if lp: row = []; continue
        if rp: rows.append(row); row = None; continue
        if row is None: continue
        if s is not None: row.append(unesc(s))
        elif null: row.append(None)
        elif num is not None: row.append(int(num) if re.fullmatch(r'-?\d+', num) else float(num))
    ph = ','.join('?' * len(tables[name]))
    db.executemany(f'INSERT INTO "{name}" VALUES ({ph})', rows)
    counts[name] = counts.get(name, 0) + len(rows)
db.commit()

# ------------------------------------------- helper: street_key replacement
def street_key(s):
    if s is None: return None
    p = s.strip().split(' ')
    second = p[1] if len(p) > 1 else p[-1]
    if second.upper() in ('W', 'E', 'N', 'S', 'WEST', 'EAST', 'NORTH', 'SOUTH'):
        k = p[2] if len(p) > 2 else p[-1]
    else:
        k = second
    return k.upper()
db.execute('''CREATE TABLE derived_street_key (
  parcel_id TEXT PRIMARY KEY,
  county_mail_key TEXT,   -- street_key(county_profile.owner_address)
  gis_mail_key TEXT,      -- street_key(city_parcels.mail_address)
  site_key TEXT           -- street_key('0 ' || city_parcels.street_name)
)''')
rows = db.execute('''SELECT p.parcel_id, pr.owner_address, p.mail_address, p.street_name
                     FROM city_parcels p LEFT JOIN county_profile pr ON pr.parcel_id = p.parcel_id''').fetchall()
db.executemany('INSERT INTO derived_street_key VALUES (?,?,?,?)',
               [(pid, street_key(a), street_key(b), street_key('0 ' + c) if c is not None else None)
                for pid, a, b, c in rows])
db.commit()

# ---------------------------------------------------------------- views
FIRST_TOKEN = lambda e: f"substr(trim({e}), 1, instr(trim({e}) || ' ', ' ') - 1)"
YEAR = lambda e: f"CAST(strftime('%Y', {e}) AS INTEGER)"

views = r"""
CREATE VIEW v_city_exemptions_by_year AS
SELECT
  x.parcel_id,
  x.tax_year,
  GROUP_CONCAT(DISTINCT x.exemption_code)                     AS city_codes,
  MAX(x.exemption_code = 'GH-1')                              AS has_gh1,
  MAX(COALESCE(x.is_senior, 0))                               AS has_city_senior,
  MAX(COALESCE(x.is_senior, 0) AND COALESCE(x.is_school, 0))  AS has_city_school_senior,
  SUM(COALESCE(x.exempt_amount, 0))                           AS city_exempt_dollars
FROM (
  SELECT b.parcel_id, b.tax_year, l.exemption_code, l.exempt_amount, r.is_senior, r.is_school
  FROM city_bills b
  JOIN city_bill_lines l ON l.id_hash = b.id_hash AND l.exemption_code IS NOT NULL
  LEFT JOIN exemption_code_ref r ON r.jurisdiction = 'city' AND r.code = l.exemption_code
  WHERE b.record_type = 'Real Property'
  ORDER BY b.parcel_id, b.tax_year, l.exemption_code
) x
GROUP BY x.parcel_id, x.tax_year;

CREATE VIEW v_city_current AS
SELECT
  b.parcel_id,
  b.tax_year,
  MAX(b.owner1)          AS city_owner1,
  MAX(b.owner2)          AS city_owner2,
  MAX(b.situs_line1)     AS city_situs,
  MAX(b.mail_line1)      AS city_mail_line1,
  MAX(b.mail_city)       AS city_mail_city,
  MAX(b.mail_zip)        AS city_mail_zip,
  MAX(b.mortgage_name)   AS mortgage_name,
  MAX(b.assessed_value)  AS city_assessed,
  MAX(b.appraised_value) AS city_appraised,
  SUM(b.base_tax)        AS city_base_tax,
  MAX(b.payment_status)  AS city_payment_status
FROM city_bills b
JOIN (
  SELECT parcel_id, MAX(tax_year) AS tax_year
  FROM city_bills WHERE record_type = 'Real Property'
  GROUP BY parcel_id
) m ON m.parcel_id = b.parcel_id AND m.tax_year = b.tax_year
WHERE b.record_type = 'Real Property'
GROUP BY b.parcel_id, b.tax_year;

CREATE VIEW v_county_current AS
SELECT
  x.parcel_id,
  x.tax_year,
  GROUP_CONCAT(DISTINCT x.code)            AS county_codes,
  MAX(x.code LIKE 'H1%')                   AS has_county_basic,
  MAX(COALESCE(x.is_senior, 0))            AS has_county_senior,
  MIN(x.year_applied)                      AS homestead_year_applied,
  MIN(x.base_year)                         AS county_base_year,
  SUM(COALESCE(x.total_exempt_amt, 0))     AS county_exempt_dollars
FROM (
  SELECT e.*, r.is_senior
  FROM county_exemptions e
  JOIN (SELECT parcel_id, MAX(tax_year) AS tax_year FROM county_exemptions GROUP BY parcel_id) m
    ON m.parcel_id = e.parcel_id AND m.tax_year = e.tax_year
  LEFT JOIN exemption_code_ref r
    ON r.jurisdiction = 'county'
   AND r.code = CASE WHEN e.code LIKE '%F' THEN substr(e.code, 1, length(e.code) - 1) ELSE e.code END
  ORDER BY e.parcel_id, e.tax_year, e.code
) x
GROUP BY x.parcel_id, x.tax_year;

CREATE VIEW v_county_last_sale AS
SELECT
  s.parcel_id,
  MAX(s.sale_date) AS last_sale_date,
  MIN(s.sale_date) AS first_sale_date,
  MAX(CASE WHEN s.price >= 10000 AND COALESCE(s.tran_code,'') NOT LIKE 'Z%' THEN s.sale_date END)
                   AS last_arms_length_sale_date,
  (SELECT s2.price FROM county_sales s2 WHERE s2.parcel_id = s.parcel_id AND s2.price IS NOT NULL
    ORDER BY s2.sale_date DESC, s2.id DESC LIMIT 1) AS last_sale_price  -- GROUP_CONCAT skipped NULL prices
FROM county_sales s
GROUP BY s.parcel_id;

CREATE VIEW v_parcel_master AS
SELECT
  p.parcel_id,
  p.owner1, p.owner2,
  p.site_address, p.address_number, p.street_name,
  p.mail_address, p.mail_city, p.mail_state, p.mail_zip5,
  p.class_code, p.zoning,
  CASE
    WHEN cc.city_mail_line1 IS NOT NULL AND cc.city_situs IS NOT NULL
      THEN (UPPER(TRIM(cc.city_mail_line1)) = UPPER(TRIM(cc.city_situs)))
    WHEN prof.owner_address IS NOT NULL AND p.address_number IS NOT NULL
      THEN ({FT_PROF} = CAST(p.address_number AS TEXT) AND sk.county_mail_key = sk.site_key)
    WHEN p.mail_address IS NOT NULL AND p.address_number IS NOT NULL
      THEN ({FT_MAIL} = CAST(p.address_number AS TEXT) AND sk.gis_mail_key = sk.site_key)
    ELSE NULL
  END AS owner_occupied_guess,
  cp.appraised_value AS county_appraised,
  cp.assessed_value  AS county_assessed,
  cp.land_value, cp.bldg_value, cp.landuse_code, cp.property_class AS county_class,
  cc.tax_year        AS city_bill_year,
  cc.city_owner1, cc.city_owner2, cc.city_situs, cc.city_mail_line1, cc.city_mail_city,
  cc.city_assessed, cc.city_appraised, cc.city_base_tax, cc.mortgage_name,
  cx.city_codes,
  COALESCE(cx.has_gh1, 0)                 AS has_city_basic,
  COALESCE(cx.has_city_senior, 0)         AS has_city_senior,
  COALESCE(cx.has_city_school_senior, 0)  AS has_city_school_senior,
  COALESCE(cx.city_exempt_dollars, 0)     AS city_exempt_dollars,
  kc.tax_year        AS county_exempt_year,
  kc.county_codes,
  COALESCE(kc.has_county_basic, 0)        AS has_county_basic,
  COALESCE(kc.has_county_senior, 0)       AS has_county_senior,
  kc.homestead_year_applied,
  kc.county_base_year,
  COALESCE(kc.county_exempt_dollars, 0)   AS county_exempt_dollars,
  fl.status                               AS county_exempt_fetch_status,
  prof.exemption_codes                    AS county_profile_codes,
  prof.owner                              AS county_owner,
  prof.co_owner                           AS county_co_owner,
  prof.owner_address                      AS county_mail_address,
  res.year_built, res.living_area, res.bedrooms, res.built_as,
  ls.last_sale_date, ls.last_arms_length_sale_date, ls.first_sale_date, ls.last_sale_price,
  NULLIF(MIN(
    COALESCE(kc.homestead_year_applied, 9999),
    COALESCE({Y_ARMS}, {Y_FIRST}, 9999)
  ), 9999)                                                    AS tenure_start_year,
  CAST(strftime('%Y','now') AS INTEGER) - NULLIF(MIN(
    COALESCE(kc.homestead_year_applied, 9999),
    COALESCE({Y_ARMS}, {Y_FIRST}, 9999)
  ), 9999)                                                    AS tenure_years,
  NTILE(3) OVER (ORDER BY COALESCE(cp.appraised_value, p.appraised_value)) AS value_tercile,
  CASE WHEN cc.city_owner1 IS NOT NULL AND prof.owner IS NOT NULL
        AND UPPER({FT_CO}) <> UPPER({FT_PO})
       THEN 1 ELSE 0 END AS owner_mismatch_flag
FROM city_parcels p
LEFT JOIN county_parcels    cp   ON cp.parcel_id = p.parcel_id
LEFT JOIN v_city_current    cc   ON cc.parcel_id = p.parcel_id
LEFT JOIN v_city_exemptions_by_year cx ON cx.parcel_id = cc.parcel_id AND cx.tax_year = cc.tax_year
LEFT JOIN v_county_current  kc   ON kc.parcel_id = p.parcel_id
LEFT JOIN county_fetch_log  fl   ON fl.parcel_id = p.parcel_id AND fl.mode = 'dek_exemptions'
LEFT JOIN county_profile    prof ON prof.parcel_id = p.parcel_id
LEFT JOIN county_residential res ON res.parcel_id = p.parcel_id
LEFT JOIN v_county_last_sale ls  ON ls.parcel_id = p.parcel_id
LEFT JOIN derived_street_key sk  ON sk.parcel_id = p.parcel_id
WHERE p.class_code LIKE 'R%';

CREATE VIEW v_goal1_county_senior_not_city AS
SELECT * FROM v_parcel_master
WHERE has_county_senior = 1 AND city_bill_year IS NOT NULL AND has_city_senior = 0;

CREATE VIEW v_goal1_reverse_city_senior_not_county AS
SELECT * FROM v_parcel_master
WHERE has_city_senior = 1 AND county_exempt_fetch_status IN ('ok','nodata') AND has_county_senior = 0;

CREATE VIEW v_goal2_candidates AS
SELECT
  m.*,
  (m.tenure_years >= 20)                         AS flag_tenure_20plus,
  (m.value_tercile = 1)                          AS flag_lower_third_value,
  (m.tenure_years >= 20 AND m.value_tercile = 1) AS flag_both
FROM v_parcel_master m
WHERE m.city_bill_year IS NOT NULL
  AND m.county_exempt_fetch_status IN ('ok','nodata')
  AND m.owner_occupied_guess = 1
  AND m.has_city_senior = 0
  AND m.has_county_senior = 0
  AND (m.has_city_basic = 1 OR m.has_county_basic = 1)
  AND (m.tenure_years >= 20 OR m.value_tercile = 1);

CREATE VIEW v_summary AS
SELECT 'residential city parcels' AS metric, COUNT(*) AS n FROM v_parcel_master
UNION ALL SELECT 'with a city bill pulled',                 COUNT(*) FROM v_parcel_master WHERE city_bill_year IS NOT NULL
UNION ALL SELECT 'with county exemptions checked',         COUNT(*) FROM v_parcel_master WHERE county_exempt_fetch_status IN ('ok','nodata')
UNION ALL SELECT 'owner-occupied (mailing = situs)',       COUNT(*) FROM v_parcel_master WHERE owner_occupied_guess = 1
UNION ALL SELECT 'city basic homestead (GH-1)',            COUNT(*) FROM v_parcel_master WHERE has_city_basic = 1
UNION ALL SELECT 'city senior exemption (any)',            COUNT(*) FROM v_parcel_master WHERE has_city_senior = 1
UNION ALL SELECT 'county basic homestead (H1/H1F)',        COUNT(*) FROM v_parcel_master WHERE has_county_basic = 1
UNION ALL SELECT 'county senior exemption (any)',          COUNT(*) FROM v_parcel_master WHERE has_county_senior = 1
UNION ALL SELECT 'GOAL1 county senior, no city senior',    COUNT(*) FROM v_goal1_county_senior_not_city
UNION ALL SELECT 'GOAL1 reverse: city senior, no county senior', COUNT(*) FROM v_goal1_reverse_city_senior_not_county
UNION ALL SELECT 'GOAL2 candidates (tenure 20+ or low value)', COUNT(*) FROM v_goal2_candidates
UNION ALL SELECT 'GOAL2 candidates, both flags',           COUNT(*) FROM v_goal2_candidates WHERE flag_both = 1
UNION ALL SELECT 'owner name mismatch city vs county',     COUNT(*) FROM v_parcel_master WHERE owner_mismatch_flag = 1;
"""
views = (views.replace('{FT_PROF}', FIRST_TOKEN('prof.owner_address'))
              .replace('{FT_MAIL}', FIRST_TOKEN('p.mail_address'))
              .replace('{FT_CO}', FIRST_TOKEN('cc.city_owner1'))
              .replace('{FT_PO}', FIRST_TOKEN('prof.owner'))
              .replace('{Y_ARMS}', YEAR('ls.last_arms_length_sale_date'))
              .replace('{Y_FIRST}', YEAR('ls.first_sale_date')))
db.executescript(views)
db.execute('ANALYZE')
db.commit()
db.execute('VACUUM')
db.close()
for k in sorted(counts): print(f'{k:24s} {counts[k]:>8,}')
print(f'done in {time.time()-t0:.0f}s -> {dst}')
