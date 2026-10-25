#!/usr/bin/env python3
"""
Research enhancements, sections 1-3, for decatur_tax.sqlite.

Adds NEW objects only (prefixes ref_ and r_). The original 12 tables, the
derived_street_key helper and the 9 original views are never modified.
Re-runnable: every object this script owns is dropped and rebuilt.

  Section 1  data quality  -> r_parcel_clean, r_data_quality
  Section 2  rules/dollars -> ref_exemption_rules, ref_tax_rates, r_city_levy_2026
  Section 3  gap views     -> r_gap_candidates, r_gap_parcels, r_gap_summary,
                              r_gap_by_decile, r_goal2_clean
Plus r_dictionary (column notes) and r_settings.

Usage: python3 enhance_sections_1_3.py decatur_tax.sqlite
"""
import sqlite3, sys, re

DB = sys.argv[1] if len(sys.argv) > 1 else 'decatur_tax.sqlite'
ANALYSIS_YEAR = 2026          # tax year of the latest city bills
db = sqlite3.connect(DB)
db.execute('PRAGMA journal_mode=MEMORY')   # the folder does not allow deleting journal files
db.row_factory = sqlite3.Row

OWNED = ['r_filing_rates', 'r_senior_takeup', 'r_gap_parcels', 'r_goal2_clean', 'r_gap_by_decile', 'r_gap_summary', 'r_data_quality',
         'r_gap_candidates', 'r_parcel_clean', 'r_city_levy_2026', 'ref_tax_rates',
         'ref_exemption_rules', 'r_dictionary', 'r_settings']
for name in OWNED:
    t = db.execute("SELECT type FROM sqlite_master WHERE name=?", (name,)).fetchone()
    if t:
        db.execute(f'DROP {t[0].upper()} "{name}"')

db.execute('CREATE TABLE r_settings (key TEXT PRIMARY KEY, value TEXT)')
db.executemany('INSERT INTO r_settings VALUES (?,?)', [
    ('analysis_year', str(ANALYSIS_YEAR)),
    ('built_by', 'enhance_sections_1_3.py'),
    ('built_at_utc', db.execute("SELECT datetime('now')").fetchone()[0]),
])

# =====================================================================
# SECTION 2a: official exemption rules (used by sections 1 and 3)
# =====================================================================
CITY_SRC = 'https://www.decaturga.com/adminservices/page/homestead-exemption-information'
CNTY_SRC = 'https://dekalbtaxga.gov/wp-content/uploads/homestead-exemption-information.pdf'
db.execute('''CREATE TABLE ref_exemption_rules (
  jurisdiction TEXT, code TEXT, name TEXT,
  min_age INTEGER, max_age INTEGER,
  income_limit INTEGER, income_basis TEXT,
  levies TEXT,                    -- city levy keys the exemption reduces
  amount_official TEXT,           -- as published
  amount_on_bills INTEGER,        -- exempt value seen on 2026 city bills (NULL = full / varies)
  proves_min_age INTEGER,         -- holding this code proves the owner is at least this age
  proves_income_under INTEGER,    -- holding it proves household income under this (its own basis)
  is_basic INTEGER, is_senior INTEGER, is_school INTEGER,
  confidence TEXT, notes TEXT, source TEXT,
  PRIMARY KEY (jurisdiction, code))''')
G = 'ZGEN,CAP,DDA'
rules = [
    # city ------------------------------------------------------------------
    ('city', 'GH-1', 'General homestead', None, None, None, None, G, '$40,000', 40000, None, None, 1, 0, 0,
     'official', 'Must be filed with the City separately from DeKalb.', CITY_SRC),
    ('city', 'GH-2', 'General homestead-A (65+)', 65, None, None, None, G, '$15,000', 15000, 65, None, 0, 1, 0,
     'official', 'No income test.', CITY_SRC),
    ('city', 'GH-3', 'General homestead-3 (62+, income)', 62, None, 60000, 'Georgia taxable income', G, '$25,000',
     25000, 62, 60000, 0, 1, 0, 'official', '', CITY_SRC),
    ('city', 'GS-1', 'General & school (62+, income)', 62, None, 25000, 'Household income', G + ',SCH', '$50,000',
     50000, 62, 25000, 0, 1, 1, 'official', '', CITY_SRC),
    ('city', 'S-1', 'School (62+, income)', 62, None, 10000, 'Income excl. retirement', 'SCH', '$10,000', 10000,
     62, 10000, 0, 1, 1, 'official', '', CITY_SRC),
    ('city', 'S-2', 'School (80+, income)', 80, None, 40000, 'Federal AGI', 'SCH', 'All school tax', None, 80,
     40000, 0, 1, 1, 'official', 'Bills show the full school assessment exempt.', CITY_SRC),
    ('city', 'S-3', 'School (70+)', 70, None, None, None, 'SCH', '$50,000', 250000, 70, None, 0, 1, 1,
     'official + bills',
     'Bills show $250,000 = S-3 $50,000 + S-6 $200,000 combined under one code (753 of 755 S-3-only bills).',
     CITY_SRC),
    ('city', 'S-5', 'School (65-69, income)', 65, 69, 62000, 'Federal AGI', 'SCH', '$200,000', 200000, 65, 62000,
     0, 1, 1, 'official', '', CITY_SRC),
    ('city', 'S-6', 'School (70+)', 70, None, None, None, 'SCH', '$200,000', None, 70, None, 0, 1, 1, 'official',
     'Never appears as its own code on bills; folded into S-3.', CITY_SRC),
    ('city', 'LT-1', 'Land Trust', None, None, None, None, G, '$40,000', 40000, None, None, 1, 0, 0, 'official',
     '', CITY_SRC),
    ('city', 'DV', 'Disabled veteran', None, None, None, None, 'ZGEN,CAP,DDA,SCH,GEN', '$121,812 (all funds)', None,
     None, None, 0, 0, 1, 'official', 'Bills show $126,526 on school/bond lines.', CITY_SRC),
    ('city', 'YEARSUP', 'Unidentified (full exemption)', None, None, None, None, 'ZGEN,CAP,DDA,SCH,GEN', None, None,
     None, None, 0, 0, 1, 'unverified', '2 parcels.', 'bills'),
    ('city', 'PE20', 'Unidentified', None, None, None, None, 'ZGEN,CAP,DDA,SCH', None, None, None, None, 0, 0, 0,
     'unverified', '1 parcel.', 'bills'),
    # county (codes stored without the trailing F = assessment freeze) ------
    ('county', 'H1', 'Basic homestead', None, None, None, None, None, '$10,000 county levies', None, None, None, 1,
     0, 0, 'official', 'For Decatur residents only county levies matter (Decatur has its own schools).', CNTY_SRC),
    ('county', 'H1S', 'Basic + state senior', 62, None, None, None, None, 'Basic + state senior', None, 62, None, 1,
     1, 0, 'county label',
     'County label "Basic Exemption + State Sr". Age tier not published; 62 used as the safe minimum.',
     'county pages'),
    ('county', 'H3', 'Senior (62+, income)', 62, None, 10000, 'Georgia net income', None,
     '$10,000 county; all school', None, 62, 10000, 0, 1, 1, 'official', '', CNTY_SRC),
    ('county', 'H4', 'Senior (65+, income)', 65, None, 10000, 'Georgia net income', None,
     '$14,000 county; all school', None, 65, 10000, 0, 1, 1, 'official', '', CNTY_SRC),
    ('county', 'H5', 'Disabled veteran', None, None, None, None, None, '$126,526 county', None, None, None, 0, 0, 0,
     'official', '', CNTY_SRC),
    ('county', 'H6', 'Senior (62/65+, income)', 62, None, 37500, 'Georgia net income', None,
     '$14,000 county; $16,500 school', None, 62, 37500, 0, 1, 1, 'official',
     'County label says "Sr 65"; 2026 sheet lists age 62 and 65 with same terms. 62 used as the safe minimum.',
     CNTY_SRC),
    ('county', 'H6I', 'Senior (62/65+, income)', 62, None, 37500, 'Georgia net income', None, 'as H6', None, 62,
     37500, 0, 1, 1, 'county label', 'Label "Sr 65-Part School (I)".', 'county pages'),
    ('county', 'H6D', 'Disability (<62, income)', None, None, 37500, 'Georgia net income', None, 'as H6', None,
     None, 37500, 0, 0, 0, 'official', 'Disability, not age.', CNTY_SRC),
    ('county', 'H7', 'Senior (62+, income)', 62, None, 40000, 'Gross income', None,
     '$10,000 county; $22,500 school', None, 62, 40000, 0, 1, 1, 'official', '', CNTY_SRC),
    ('county', 'H8', 'Senior (65+, income)', 65, None, 40000, 'Gross income', None,
     '$14,000 county; $22,500 school', None, 65, 40000, 0, 1, 1, 'official', '', CNTY_SRC),
    ('county', 'H9', 'Senior (70+, income)', 70, None, 113664, 'Federal AGI', None, '$10,000 county; all school',
     None, 70, None, 0, 1, 1, 'official',
     'Income limit too high to prove eligibility for city income tiers.', CNTY_SRC),
    ('county', 'H10', 'Senior disabled veteran (65+)', 65, None, 10000, 'Georgia net income', None,
     '$126,526 county', None, 65, 10000, 0, 1, 1, 'official', '', CNTY_SRC),
    ('county', 'H5S', 'Disabled veteran + senior', 62, None, None, None, None, 'as H5 + senior', None, 62, None,
     1, 1, 0, 'county label', 'County label "Disabled Vet + Senior Frz"; senior tier not published, 62 used.',
     'county pages'),
    ('county', 'H5WS', 'Unidentified (disabled-vet family code)', None, None, None, None, None, None, None, None,
     None, 1, 0, 0, 'unverified', '2 parcels; homestead code, meaning not published.', 'county pages'),
    ('county', 'LD', 'Unidentified homestead code', None, None, None, None, None, None, None, None, None, 1, 0, 0,
     'unverified', '13 parcels (shown as LDF = with freeze).', 'county pages'),
    ('county', 'W1', 'Unidentified homestead code', None, None, None, None, None, None, None, None, None, 1, 0, 0,
     'unverified', 'Seen in county history (W1F).', 'county pages'),
]
db.executemany('INSERT INTO ref_exemption_rules VALUES (' + ','.join('?' * 18) + ')', rules)
RULE = {(r[0], r[1]): r for r in rules}
PROVES_AGE = {k: r[10] for k, r in RULE.items()}
PROVES_INC = {k: r[11] for k, r in RULE.items()}

# =====================================================================
# SECTION 2b: tax rates from the 2026 bills
# =====================================================================
LEVY_OF = {'ZGENERAL-REAL': 'ZGEN', 'CAPITAL-REAL': 'CAP', 'DDA-REAL': 'DDA',
           'SCHOOL-REAL': 'SCH', 'GEN BOND-REAL': 'GEN_BOND', 'BOND SCHOOL REAL': 'SCH_BOND'}
db.execute('''CREATE TABLE ref_tax_rates (tax_year INTEGER, levy TEXT, bill_description TEXT,
  mills REAL, homestead_exemptions_apply INTEGER, PRIMARY KEY (tax_year, levy))''')
for (desc, mills) in db.execute('''SELECT l.description, MAX(l.millage_rate) FROM city_bill_lines l
      JOIN city_bills b USING(id_hash) WHERE b.tax_year=? AND l.is_charge=1 AND l.millage_rate>0
      GROUP BY l.description''', (ANALYSIS_YEAR,)).fetchall():
    key = re.sub(r'^\d{4} ', '', desc)
    if key in LEVY_OF:
        lv = LEVY_OF[key]
        db.execute('INSERT INTO ref_tax_rates VALUES (?,?,?,?,?)',
                   (ANALYSIS_YEAR, lv, desc, mills, 0 if lv in ('GEN_BOND', 'SCH_BOND') else 1))
MILLS = {r['levy']: r['mills'] for r in db.execute('SELECT levy, mills FROM ref_tax_rates')}
GEN_MILLS = MILLS['ZGEN'] + MILLS['CAP'] + MILLS['DDA']
SCH_MILLS = MILLS['SCH']

# =====================================================================
# SECTION 2c: per-parcel 2026 city bill by levy
# =====================================================================
db.execute('''CREATE TABLE r_city_levy_2026 AS
SELECT b.parcel_id,
  MAX(b.assessed_value)  AS assessed,
  MAX(b.appraised_value) AS appraised,
  MAX(b.original_due)    AS billed_first_installment,   -- city bills are semiannual; 2026 has the March bill only
  MAX(CASE WHEN l.description LIKE '%ZGENERAL-REAL' THEN l.exempt_value END) AS exempt_general,
  MAX(CASE WHEN l.description LIKE '%SCHOOL-REAL' AND l.description NOT LIKE '%BOND%'
           THEN l.exempt_value END) AS exempt_school,
  SUM(CASE WHEN l.is_exempt=1 THEN -l.amount ELSE 0 END) AS exemption_credit_first_installment
FROM city_bills b JOIN city_bill_lines l USING(id_hash)
WHERE b.tax_year=? AND b.record_type='Real Property'
GROUP BY b.parcel_id''', (ANALYSIS_YEAR,))
db.execute('CREATE UNIQUE INDEX ix_r_city_levy ON r_city_levy_2026(parcel_id)')


# =====================================================================
# SECTION 1: cleaned parcel table
# =====================================================================
def owner_type(n):
    n = (n or '').upper()
    if re.search(r'\b(ASSOCIATION|ASSN|HOA|OWNERS ASSOC|CONDOMINIUM ASSOC)\b', n):
        return 'association'
    if re.search(r'\b(CITY OF|HOUSING AUTH\w*|DEKALB COUNTY|BOARD OF|CHURCH|SCHOOL|STATE OF|UNITED STATES|'
                 r'DOWNTOWN DEVELOPMENT)\b', n):
        return 'government_institution'
    if re.search(r'\b(LLC|L L C|INC|CORP|CORPORATION|COMPANY|LP|LLP|LTD|PARTNERS|PARTNERSHIP|PROPERTIES|'
                 r'HOLDINGS|INVESTMENTS?|REALTY|HOMES|GROUP|VENTURES|FUND|BANK|MORTGAGE|DEVELOPMENT)\b', n):
        return 'llc_corp'
    if re.search(r'\b(ESTATE OF|EST OF|ESTATE)\b', n) or n.endswith(' EST'):
        return 'estate'
    if re.search(r'\b(TRUST|TRUSTEE|TRUSTEES|TRST|REVOCABLE|IRREVOCABLE|TR)\b', n):
        return 'trust'
    return 'individual'


def clean_year(y):
    try:
        y = int(y)
    except (TypeError, ValueError):
        return None
    return y if 1900 <= y <= ANALYSIS_YEAR + 1 else None


def year_of(d):
    return clean_year(d[:4]) if d else None


def strip_f(code):
    return code[:-1] if code.endswith('F') and len(code) > 2 else code


def codes(s):
    return [c.strip() for c in (s or '').split(',') if c.strip()]


landuse = {r[0]: r[1] for r in db.execute('SELECT parcel_id, land_use_code FROM county_profile')}

# County codes: the county PROFILE page is complete (it matches the county history on every parcel);
# the exemptions-page scrape used by v_parcel_master missed 77 parcels (H6IF, LDF, H6DF, H5WS).
cnty_fixed = {r[0]: ','.join(c.strip() for c in re.split(r'[,; ]+', r[1] or '') if c.strip())
              for r in db.execute('SELECT parcel_id, exemption_codes FROM county_profile')}

# Age floors from how long a senior code has been held (as of Jan 1 of the analysis year).
#  county: grant year = earliest of the exemptions-page "year applied" for that code and the first year of
#          an unbroken same-owner run of that code in county_owner_history (2019-2026).
#  city:   a senior code already on the prior-year bill adds one year.
year_applied = {}
for pid, code, ya in db.execute('SELECT parcel_id, code, year_applied FROM county_exemptions'):
    if ya and 1980 <= ya <= ANALYSIS_YEAR:
        year_applied[(pid, strip_f(code))] = ya
hist = {}
for pid, y, blob, code in db.execute('''SELECT parcel_id, tax_year, owner_address_blob, county_exmp_code
                                        FROM county_owner_history WHERE tax_year <= ?''', (ANALYSIS_YEAR,)):
    hist.setdefault(pid, {})[y] = ((blob or '')[:20], strip_f(code) if code else None)
city_prev = {}
for pid, cs in db.execute('SELECT parcel_id, city_codes FROM v_city_exemptions_by_year WHERE tax_year = ?',
                          (ANALYSIS_YEAR - 1,)):
    city_prev[pid] = codes(cs)


def age_floor(pid, county_codes_list, city_codes_list):
    best, basis = None, None
    h = hist.get(pid, {})
    for c in county_codes_list:
        min_age = PROVES_AGE.get(('county', c))
        if not min_age:
            continue
        run_start = None
        if ANALYSIS_YEAR in h and h[ANALYSIS_YEAR][1] == c:
            owner = h[ANALYSIS_YEAR][0]
            y = ANALYSIS_YEAR
            while y in h and h[y][1] == c and h[y][0] == owner:
                run_start = y
                y -= 1
        cands = [x for x in (year_applied.get((pid, c)), run_start) if x]
        if not cands:
            continue
        g = min(cands)
        f = min_age + (ANALYSIS_YEAR - g)
        if best is None or f > best:
            best, basis = f, f'county {c} held since {g} (min age {min_age})'
    for c in city_prev.get(pid, []):
        min_age = PROVES_AGE.get(('city', c))
        if min_age and c in city_codes_list:
            f = min_age + 1
            if best is None or f > best:
                best, basis = f, f'city {c} on {ANALYSIS_YEAR - 1} bill (min age {min_age})'
    return best, basis
levy = {r['parcel_id']: dict(r) for r in db.execute('SELECT * FROM r_city_levy_2026')}
master = [dict(r) for r in db.execute('SELECT * FROM v_parcel_master')]

rows = []
for m in master:
    pid = m['parcel_id']
    lu = landuse.get(pid) or ''
    lu_code = (m['landuse_code'] or lu[:3] or '').strip()
    is_vacant = int(lu_code == '100')
    is_common = int(lu_code in ('111', '166', '188') or '**' in lu)
    is_condo = int(lu_code == '106')
    is_townhouse = int(lu_code == '107')
    own_name = m['city_owner1'] or m['county_owner'] or m['owner1']
    otype = owner_type(own_name)
    # tenure --------------------------------------------------------------
    hy = clean_year(m['homestead_year_applied'])
    arms = year_of(m['last_arms_length_sale_date'])
    first = year_of(m['first_sale_date'])
    sale_y = arms or first
    cands = [(y, b) for y, b in ((hy, 'homestead'), (sale_y, 'sale' if arms else 'deed_any')) if y]
    if cands:
        start, basis = min(cands)
        if basis == 'homestead' and start == 2007:
            basis = 'homestead_2007_floor'
    else:
        start, basis = None, 'none'
    tenure = ANALYSIS_YEAR - start if start else None
    invalid_src = ((m['homestead_year_applied'] is not None and hy is None) or
                   (bool(m['first_sale_date']) and first is None) or
                   (bool(m['last_arms_length_sale_date']) and arms is None))
    # sale timing ---------------------------------------------------------
    last_arms = m['last_arms_length_sale_date'] or ''
    sold_this_year = int(last_arms >= f'{ANALYSIS_YEAR}-01-01')
    sold_last_year = int(f'{ANALYSIS_YEAR - 1}-01-01' <= last_arms < f'{ANALYSIS_YEAR}-01-01')
    # exemption evidence --------------------------------------------------
    cc = codes(m['city_codes'])
    county_codes_fixed = cnty_fixed.get(pid) or None
    kc = [strip_f(c) for c in codes(county_codes_fixed)]
    has_county_homestead = int(bool(kc))
    has_county_senior_fixed = int(any((RULE.get(('county', c)) or [0] * 14)[13] == 1 for c in kc))
    floor, floor_basis = age_floor(pid, kc, cc)
    city_age = max([PROVES_AGE.get(('city', c)) or 0 for c in cc] or [0]) or None
    cnty_age = max([PROVES_AGE.get(('county', c)) or 0 for c in kc] or [0]) or None
    age_proven = max(city_age or 0, cnty_age or 0) or None
    age_proven_now = max(age_proven or 0, floor or 0) or None
    incs = [PROVES_INC.get(('city', c)) for c in cc] + [PROVES_INC.get(('county', c)) for c in kc]
    incs = [i for i in incs if i]
    income_proven_under = min(incs) if incs else None
    has_homestead_any = bool(cc or kc)
    mail = (m['city_mail_line1'] or m['mail_address'] or '').upper().strip()
    po_box = int(bool(re.match(r'^(P\.?\s*O\.?\s*BOX|POST OFFICE BOX|BOX\s)', mail)))
    if has_homestead_any:
        occ, occ_basis = 1, 'homestead on file'
    elif m['owner_occupied_guess'] == 1:
        occ, occ_basis = 1, 'mailing = property address'
    elif po_box:
        occ, occ_basis = None, 'PO box mailing, unknown'
    elif m['owner_occupied_guess'] == 0:
        occ, occ_basis = 0, 'mailing elsewhere, no homestead'
    else:
        occ, occ_basis = None, 'unknown'
    no_bill_reason = None
    if m['city_bill_year'] is None:
        no_bill_reason = ('common area / association' if (is_common or otype == 'association') else
                          'vacant lot' if is_vacant else
                          'company owner' if otype == 'llc_corp' else 'not found in city billing')
    lv = levy.get(pid, {})
    in_universe = int(not is_vacant and not is_common and otype in ('individual', 'trust', 'estate')
                      and m['city_bill_year'] == ANALYSIS_YEAR and not sold_this_year)
    rows.append((pid, m['site_address'], own_name, m['owner2'], otype, lu, is_vacant, is_common, is_condo,
                 is_townhouse, m['county_appraised'], lv.get('assessed'), m['homestead_year_applied'], hy,
                 m['last_arms_length_sale_date'], m['first_sale_date'], start, basis, tenure,
                 m['tenure_years'], int(invalid_src), sold_this_year, sold_last_year,
                 m['owner_occupied_guess'], occ, occ_basis, po_box, m['city_codes'], county_codes_fixed,
                 m['has_city_basic'], has_county_homestead, m['has_city_senior'], has_county_senior_fixed,
                 city_age, cnty_age, age_proven, income_proven_under, lv.get('exempt_general'),
                 lv.get('exempt_school'), lv.get('billed_first_installment'), no_bill_reason, in_universe,
                 m['year_built'], m['value_tercile'],
                 m['county_codes'], m['county_assessed'], floor, floor_basis, age_proven_now))

db.execute('''CREATE TABLE r_parcel_clean (
  parcel_id TEXT PRIMARY KEY, site_address TEXT, owner_name TEXT, owner2 TEXT, owner_type TEXT,
  land_use TEXT, is_vacant INTEGER, is_common_area INTEGER, is_condo INTEGER, is_townhouse INTEGER,
  county_appraised NUMERIC, city_assessed_2026 NUMERIC,
  homestead_year_raw INTEGER, homestead_year_clean INTEGER,
  last_arms_length_sale_date TEXT, first_sale_date TEXT,
  tenure_start_year INTEGER, tenure_basis TEXT, tenure_years INTEGER, tenure_years_original INTEGER,
  tenure_source_invalid INTEGER, sold_this_year INTEGER, sold_last_year INTEGER,
  owner_occupied_guess_original INTEGER, owner_occupied_best INTEGER, owner_occupied_basis TEXT,
  mail_is_po_box INTEGER, city_codes TEXT, county_codes TEXT,
  has_city_basic INTEGER, has_county_basic INTEGER, has_city_senior INTEGER, has_county_senior INTEGER,
  city_age_proven INTEGER, county_age_proven INTEGER, age_proven INTEGER, income_proven_under INTEGER,
  exempt_general_2026 NUMERIC, exempt_school_2026 NUMERIC, city_billed_2026_first_half NUMERIC,
  no_city_bill_reason TEXT, in_analysis_universe INTEGER,
  year_built INTEGER, value_tercile_original INTEGER,
  county_codes_exemptions_page TEXT, county_assessed NUMERIC,
  age_floor_now INTEGER, age_floor_basis TEXT, age_proven_now INTEGER,
  value_decile INTEGER, value_pct_rank REAL)''')
db.executemany('INSERT INTO r_parcel_clean VALUES (' + ','.join('?' * 49) + ',NULL,NULL)', rows)
# value deciles over improved residential homes (vacant lots and common areas excluded)
db.execute('''CREATE TEMP TABLE _dec AS
  SELECT parcel_id,
         NTILE(10) OVER (ORDER BY county_appraised) AS dec,
         ROUND(PERCENT_RANK() OVER (ORDER BY county_appraised), 4) AS pr
  FROM r_parcel_clean WHERE is_vacant=0 AND is_common_area=0 AND county_appraised > 0''')
db.execute('''UPDATE r_parcel_clean SET
  value_decile   = (SELECT dec FROM _dec d WHERE d.parcel_id = r_parcel_clean.parcel_id),
  value_pct_rank = (SELECT pr  FROM _dec d WHERE d.parcel_id = r_parcel_clean.parcel_id)''')
db.commit()

# =====================================================================
# SECTION 3: gap candidates
# =====================================================================
P = {r['parcel_id']: dict(r) for r in db.execute('SELECT * FROM r_parcel_clean')}
gaps = []

# County-side relief for a NEW county homestead, from what recent filers actually receive:
#   constitutional exemption credit (median) + HOST/EHOST credit as a share of county assessed value (median).
#   Freeze benefits (which grow over time) and the state HTRG grant are excluded, so this is conservative.
_recent = db.execute('''SELECT e.const_exempt_amt, e.host_exempt_amt, cp.assessed_value
    FROM county_exemptions e JOIN county_parcels cp USING(parcel_id)
    WHERE e.code IN ('H1','H1F') AND e.year_applied IN (?,?) AND cp.assessed_value > 50000''',
    (ANALYSIS_YEAR - 1, ANALYSIS_YEAR)).fetchall()
def _median(xs):
    xs = sorted(xs); n = len(xs)
    return (xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2) if n else None
CNTY_CONST = _median([r[0] or 0 for r in _recent])
CNTY_HOST_RATE = _median([(r[1] or 0) / r[2] for r in _recent])
CNTY_MILLS_BASIC = CNTY_CONST / 10000 * 1000     # implied mills on the levies the $10,000 basic applies to
db.executemany('INSERT INTO r_settings VALUES (?,?)', [
    ('county_relief_sample_n', str(len(_recent))),
    ('county_const_credit_median', f'{CNTY_CONST:.2f}'),
    ('county_host_credit_rate_median', f'{CNTY_HOST_RATE:.6f}'),
    ('county_implied_mills_basic', f'{CNTY_MILLS_BASIC:.3f}'),
])


def add(pid, tier, gap_code, label, status, evidence, missing, levies, exempt_value, savings,
        income_dependent, note='', strength=None, county_savings=None):
    if strength is None:
        strength = {'proven': 'high', 'likely': 'medium'}.get(status, 'low')
    if county_savings is None and savings is not None and savings <= 0:
        return          # nothing left to exempt (e.g. already fully exempt) - not a real gap
    gaps.append((pid, tier, gap_code, label, status, strength, evidence, missing, levies,
                 round(exempt_value) if exempt_value is not None else None,
                 round(savings, 2) if savings is not None else None,
                 round(county_savings, 2) if county_savings is not None else None,
                 int(income_dependent), note))


for pid, p in P.items():
    if not p['in_analysis_universe']:
        continue
    cc = codes(p['city_codes'])
    kc = [strip_f(c) for c in codes(p['county_codes'])]
    a = p['city_assessed_2026'] or 0
    eg = p['exempt_general_2026'] or 0
    es = p['exempt_school_2026'] or 0
    room_g = max(a - eg, 0)        # taxable value left on the general levies
    room_s = max(a - es, 0)        # taxable value left on the school levy
    age = p['age_proven_now'] or 0
    age_by_floor = (p['age_floor_now'] or 0) > (p['age_proven'] or 0)
    floor_note = f" Age from {p['age_floor_basis']}." if age_by_floor else ''
    inc = p['income_proven_under']
    ca = p['county_assessed'] or 0
    has = lambda c: c in cc
    school_senior = any(has(c) for c in ('S-1', 'S-2', 'S-3', 'S-5', 'GS-1'))
    has_city_basic = has('GH-1') or has('LT-1') or has('DV')
    ev = f"city: {p['city_codes'] or 'none'}; county: {p['county_codes'] or 'none'}"

    # ---- Tier B: basic homestead filed with one office only --------------
    gh1_value = 0
    if kc and not has_city_basic:
        gh1_value = min(40000, room_g)
        add(pid, 'B', 'CITY_BASIC_MISSING', 'County homestead on file, no city GH-1', 'proven', ev, 'GH-1',
            'ZGEN,CAP,DDA', gh1_value, gh1_value * GEN_MILLS / 1000, 0,
            'The county accepted a homestead, so residency is established.')
    if cc and has_city_basic and not kc:
        add(pid, 'B', 'COUNTY_BASIC_MISSING', 'City homestead on file, no county homestead', 'proven', ev, 'H1',
            'county levies', 10000, None, 0,
            'County relief = basic exemption credit + HOST/EHOST homestead credit, estimated from what recent '
            'filers receive (excludes freeze and the state HTRG grant).'
            + (' Bought last year: new owners must refile with the county.' if p['sold_last_year'] else ''),
            county_savings=CNTY_CONST + CNTY_HOST_RATE * ca)
    room_g_after = max(room_g - gh1_value, 0)

    # ---- Tier A: age proven, a city benefit is missing -------------------
    if age >= 65 and not has('GH-2'):
        v = min(15000, room_g_after)
        add(pid, 'A', 'GH2_MISSING', 'Age 65+ proven, no city GH-2', 'proven', ev, 'GH-2', 'ZGEN,CAP,DDA',
            v, v * GEN_MILLS / 1000, 0, 'GH-2 has no income test.' + floor_note)
    elif age >= 62 and not has('GH-2') and any(c in ('H6', 'H6I', 'H1S') for c in kc):
        v = min(15000, room_g_after)
        add(pid, 'A', 'GH2_MISSING', 'County senior code labelled 65+, no city GH-2', 'likely', ev, 'GH-2',
            'ZGEN,CAP,DDA', v, v * GEN_MILLS / 1000, 0,
            'County labels this code "Sr 65"; its 2026 sheet also lists age 62.')
    if age >= 62 and not has('GH-3') and inc is not None and inc <= 60000:
        v = min(25000, room_g_after)
        add(pid, 'A', 'GH3_MISSING', 'Age 62+ and low income proven by other codes, no city GH-3', 'proven', ev,
            'GH-3', 'ZGEN,CAP,DDA', v, v * GEN_MILLS / 1000, 0,
            f'Holds a code capped at ${inc:,} income; GH-3 cap is $60,000 Georgia taxable income. '
            'Bills show GH-3 stacked with GS-1/S-1 on 100+ parcels, so tiers combine.')
    if age >= 70 and not (has('S-3') or has('S-2')):
        v = max(min(250000, a) - min(es, a), 0)
        add(pid, 'A', 'SCHOOL_70_MISSING', 'Age 70+ proven, no city 70+ school exemption', 'proven', ev,
            'S-3 + S-6', 'SCH', v, v * SCH_MILLS / 1000, 0,
            'S-3 and S-6 have no income test; bills combine them to $250,000.' + floor_note)
    elif age >= 65 and not school_senior:
        v = min(200000, room_s)
        add(pid, 'A', 'SCHOOL_65_MISSING', 'Age 65+ proven, no city school senior exemption', 'likely', ev,
            'S-5 (65-69) or S-3/S-6 (70+)', 'SCH', v, v * SCH_MILLS / 1000, 1,
            'If 70+: S-3/S-6 ($250,000, no income test). If 65-69: S-5 ($200,000) needs federal AGI under '
            '$62,000. Estimate uses $200,000.')

    # ---- Tier D: county senior tier missing (low value for Decatur) -------
    if (p['city_age_proven'] or 0) >= 62 and not p['has_county_senior']:
        add(pid, 'D', 'COUNTY_SENIOR_MISSING', 'City senior on file, county has basic or none', 'possible', ev,
            'H4/H6/H8 (income-limited)', 'county levies', 4000, None, 1,
            'For Decatur residents county senior tiers add at most $4,000 on county levies; all carry income limits. '
            'Estimate = $4,000 x implied county rate.', county_savings=4000 * CNTY_MILLS_BASIC / 1000)

    # ---- Tier C: likely senior, filed nowhere ----------------------------
    if (p['owner_occupied_best'] == 1 and not p['has_city_senior'] and not p['has_county_senior']
            and (p['has_city_basic'] or p['has_county_basic'])):
        t = p['tenure_years'] or 0
        d = p['value_decile'] or 99
        if t >= 20 or d <= 3:
            v = min(15000, room_g_after)
            if t >= 30 or (t >= 20 and d <= 3):
                strength = 'high' if (t >= 20 and d <= 3) else 'medium'
            elif t >= 20:
                strength = 'medium'
            else:
                strength = 'low'       # low value only, owned under 20 years
            flags = []
            if t >= 30:
                flags.append('owned 30+ yrs')
            elif t >= 20:
                flags.append('owned 20+ yrs')
            if d <= 3:
                flags.append(f'value decile {d}')
            if p['tenure_basis'] == 'homestead_2007_floor':
                flags.append('tenure is a floor (2007 freeze year)')
            add(pid, 'C', 'LIKELY_SENIOR_UNFILED', 'Long tenure or low value, no senior exemption anywhere',
                'possible', '; '.join(flags) + ' | ' + ev, 'GH-2 (+ school tier if 65+/70+)', 'ZGEN,CAP,DDA',
                v, v * GEN_MILLS / 1000, 0,
                'Homeowner savings shown = GH-2 only (what any 65+ owner gets). A 70+ owner would also get up to '
                '$250,000 off school tax.', strength)

db.execute('''CREATE TABLE r_gap_candidates (
  parcel_id TEXT, tier TEXT, gap_code TEXT, gap_label TEXT, status TEXT, strength TEXT, evidence TEXT,
  missing_exemption TEXT, levies TEXT, est_exempt_value NUMERIC, est_annual_homeowner_savings_city_tax NUMERIC,
  est_annual_homeowner_savings_county_tax NUMERIC,
  income_dependent INTEGER, note TEXT, PRIMARY KEY (parcel_id, gap_code))''')
db.executemany('INSERT INTO r_gap_candidates VALUES (' + ','.join('?' * 14) + ')', gaps)

# =====================================================================
# Views
# =====================================================================
db.executescript('''
CREATE VIEW r_gap_parcels AS
SELECT g.*, p.site_address, p.owner_name, p.owner_type, p.value_decile, p.county_appraised,
       p.city_assessed_2026, p.tenure_years, p.tenure_basis, p.age_proven, p.age_proven_now,
       p.age_floor_basis, p.is_condo
FROM r_gap_candidates g JOIN r_parcel_clean p USING(parcel_id);

CREATE VIEW r_gap_summary AS
SELECT tier, gap_code, gap_label, status, strength,
       COUNT(*) AS parcels,
       SUM(income_dependent) AS income_dependent_parcels,
       ROUND(SUM(est_annual_homeowner_savings_city_tax)) AS total_unclaimed_relief_city_tax,
       ROUND(AVG(est_annual_homeowner_savings_city_tax)) AS avg_unclaimed_relief_city_tax,
       ROUND(SUM(est_annual_homeowner_savings_county_tax)) AS total_unclaimed_relief_county_tax,
       ROUND(AVG(est_annual_homeowner_savings_county_tax)) AS avg_unclaimed_relief_county_tax
FROM r_gap_candidates GROUP BY tier, gap_code, gap_label, status, strength
ORDER BY tier, gap_code, CASE strength WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END;

CREATE VIEW r_gap_by_decile AS
SELECT p.value_decile,
  COUNT(DISTINCT CASE WHEN g.tier='A' THEN g.parcel_id END) AS tier_a_parcels,
  COUNT(DISTINCT CASE WHEN g.tier='B' THEN g.parcel_id END) AS tier_b_parcels,
  COUNT(DISTINCT CASE WHEN g.tier='C' AND g.strength IN ('high','medium') THEN g.parcel_id END) AS tier_c_parcels_med_high,
  COUNT(DISTINCT CASE WHEN g.tier='C' AND g.strength='low' THEN g.parcel_id END) AS tier_c_parcels_low,
  ROUND(SUM(CASE WHEN g.tier IN ('A','B') THEN g.est_annual_homeowner_savings_city_tax END)) AS tier_ab_unclaimed_relief_city_tax,
  (SELECT COUNT(*) FROM r_parcel_clean p2 WHERE p2.value_decile=p.value_decile AND p2.in_analysis_universe=1) AS universe_parcels
FROM r_parcel_clean p LEFT JOIN r_gap_candidates g USING(parcel_id)
WHERE p.value_decile IS NOT NULL
GROUP BY p.value_decile ORDER BY p.value_decile;

CREATE VIEW r_goal2_clean AS
SELECT p.*,
  (p.tenure_years >= 20) AS flag_tenure_20plus,
  (p.tenure_years >= 30) AS flag_tenure_30plus,
  (p.value_decile = 1)   AS flag_bottom_10pct,
  (p.value_decile <= 2)  AS flag_bottom_20pct,
  (p.value_decile <= 3)  AS flag_bottom_30pct,
  g.strength
FROM r_parcel_clean p JOIN r_gap_candidates g ON g.parcel_id = p.parcel_id AND g.gap_code = 'LIKELY_SENIOR_UNFILED';

CREATE VIEW r_data_quality AS
SELECT 'residential parcels (all)' AS check_name, COUNT(*) AS parcels FROM r_parcel_clean
UNION ALL SELECT 'vacant lots (excluded)', SUM(is_vacant) FROM r_parcel_clean
UNION ALL SELECT 'HOA / common areas (excluded)', SUM(is_common_area) FROM r_parcel_clean
UNION ALL SELECT 'company owners (excluded)', SUM(owner_type='llc_corp') FROM r_parcel_clean
UNION ALL SELECT 'association / government owners (excluded)',
                 SUM(owner_type IN ('association','government_institution')) FROM r_parcel_clean
UNION ALL SELECT 'trust owners (kept)', SUM(owner_type='trust') FROM r_parcel_clean
UNION ALL SELECT 'estate owners (kept)', SUM(owner_type='estate') FROM r_parcel_clean
UNION ALL SELECT 'no 2026 city bill (excluded)', SUM(no_city_bill_reason IS NOT NULL) FROM r_parcel_clean
UNION ALL SELECT 'sold since Jan 1 of analysis year (excluded)', SUM(sold_this_year) FROM r_parcel_clean
UNION ALL SELECT 'sold in prior year (kept, flagged)', SUM(sold_last_year) FROM r_parcel_clean
UNION ALL SELECT 'invalid year in tenure source (cleaned)', SUM(tenure_source_invalid) FROM r_parcel_clean
UNION ALL SELECT 'original tenure > 100 years', SUM(tenure_years_original > 100) FROM r_parcel_clean
UNION ALL SELECT 'clean tenure > 100 years', SUM(tenure_years > 100) FROM r_parcel_clean
UNION ALL SELECT 'tenure is a 2007 freeze-year floor', SUM(tenure_basis='homestead_2007_floor') FROM r_parcel_clean
UNION ALL SELECT 'owner-occupied: original guess', SUM(owner_occupied_guess_original=1) FROM r_parcel_clean
UNION ALL SELECT 'owner-occupied: best (homestead or address match)', SUM(owner_occupied_best=1) FROM r_parcel_clean
UNION ALL SELECT 'PO box mailing address', SUM(mail_is_po_box) FROM r_parcel_clean
UNION ALL SELECT 'county codes recovered from profile page (missed by original scrape)',
                 SUM(county_codes IS NOT NULL AND county_codes_exemptions_page IS NULL) FROM r_parcel_clean
UNION ALL SELECT 'age raised by years-held evidence', SUM(COALESCE(age_floor_now,0) > COALESCE(age_proven,0)) FROM r_parcel_clean
UNION ALL SELECT 'age now proven 70+ only via years-held evidence',
                 SUM(age_proven_now >= 70 AND COALESCE(age_proven,0) < 70) FROM r_parcel_clean
UNION ALL SELECT 'in analysis universe', SUM(in_analysis_universe) FROM r_parcel_clean;
''')

# =====================================================================
# SECTION 3b: filing rates by segment (who files, where)
# =====================================================================
def prop_type(p):
    lu = (p['land_use'] or '')[:3]
    return {'101': 'single-family house', '106': 'condo', '107': 'townhouse',
            '102': 'multi-family (2-3 units)', '103': 'multi-family (2-3 units)'}.get(lu, 'other / unknown')

def cohort(p):
    d = p['last_arms_length_sale_date'] or ''
    y = int(d[:4]) if d[:4].isdigit() and int(d[:4]) >= 1900 else None
    if y is None: return 'no arms-length sale on record'
    for lo, hi, lab in [(1900, 1989, 'bought before 1990'), (1990, 1999, 'bought 1990-99'),
                        (2000, 2009, 'bought 2000-09'), (2010, 2014, 'bought 2010-14'),
                        (2015, 2019, 'bought 2015-19'), (2020, 2022, 'bought 2020-22'),
                        (2023, 2024, 'bought 2023-24'), (2025, 2025, 'bought 2025')]:
        if lo <= y <= hi: return lab
    return 'bought 2026'

def tenure_band(p):
    t = p['tenure_years']
    if t is None: return 'unknown'
    return '<10 yrs' if t < 10 else '10-19 yrs' if t < 20 else '20-29 yrs' if t < 30 else '30+ yrs'

base = [p for p in P.values() if p['in_analysis_universe'] and p['owner_occupied_best'] == 1]
segs = {
    'all': lambda p: 'all likely owner-occupied homes',
    'value_decile': lambda p: f"decile {p['value_decile']:02d}" if p['value_decile'] else 'unknown',
    'property_type': prop_type,
    'owner_type': lambda p: p['owner_type'],
    'purchase_cohort': cohort,
    'tenure_band': tenure_band,
}
fr = []
for st, fn in segs.items():
    groups = {}
    for p in base:
        groups.setdefault(fn(p), []).append(p)
    for seg, ps in sorted(groups.items()):
        n = len(ps)
        cb = [bool(codes(p['city_codes'])) and any(c in ('GH-1', 'LT-1', 'DV') for c in codes(p['city_codes'])) for p in ps]
        kb = [bool(p['has_county_basic']) for p in ps]
        both = sum(1 for a, b in zip(cb, kb) if a and b)
        c_only = sum(1 for a, b in zip(cb, kb) if a and not b)
        k_only = sum(1 for a, b in zip(cb, kb) if b and not a)
        neither = n - both - c_only - k_only
        fr.append((st, seg, n, both, c_only, k_only, neither,
                   round(100 * both / n, 1), round(100 * c_only / n, 1), round(100 * k_only / n, 1),
                   round(100 * neither / n, 1)))
db.execute('''CREATE TABLE r_filing_rates (segment_type TEXT, segment TEXT, households INTEGER,
  filed_both INTEGER, city_only INTEGER, county_only INTEGER, neither INTEGER,
  pct_both REAL, pct_city_only REAL, pct_county_only REAL, pct_neither REAL)''')
db.executemany('INSERT INTO r_filing_rates VALUES (' + ','.join('?' * 11) + ')', fr)

# Senior take-up: among households whose age is proven by COUNTY records only (so the measure is not circular:
# city codes would prove age AND count as claiming), what share claim each city benefit?
def band3(p):
    d = p['value_decile']
    return 'all values' if d is None else ('bottom 30%' if d <= 3 else 'middle 40%' if d <= 7 else 'top 30%')
tk = []
def county_age(p):
    f = p['age_floor_now'] if (p['age_floor_basis'] or '').startswith('county') else 0
    return max(p['county_age_proven'] or 0, f or 0)

def county_income(p):
    ks = [strip_f(c) for c in codes(p['county_codes'])]
    xs = [PROVES_INC.get(('county', c)) for c in ks]
    xs = [x for x in xs if x]
    return min(xs) if xs else None

tests = [
    ('County record proves 62+', lambda p: county_age(p) >= 62, 'any city senior exemption',
     lambda cc: any(c in cc for c in ('GH-2', 'GH-3', 'GS-1', 'S-1', 'S-2', 'S-3', 'S-5'))),
    ('County record proves 65+', lambda p: county_age(p) >= 65, 'GH-2 (65+, no income test)',
     lambda cc: 'GH-2' in cc),
    ('County record proves 70+', lambda p: county_age(p) >= 70, '70+ school exemption (S-3/S-6 or S-2)',
     lambda cc: 'S-3' in cc or 'S-2' in cc),
    ('County record proves 62+ and income under $60k', lambda p: county_age(p) >= 62 and county_income(p)
     is not None and county_income(p) <= 60000, 'GH-3 (62+, income)', lambda cc: 'GH-3' in cc),
]
univ = [p for p in P.values() if p['in_analysis_universe']]
for label, elig, benefit, has_it in tests:
    for grp in ('all values', 'bottom 30%', 'middle 40%', 'top 30%'):
        ps = [p for p in univ if elig(p) and (grp == 'all values' or band3(p) == grp)]
        if not ps: continue
        k = sum(1 for p in ps if has_it(codes(p['city_codes'])))
        tk.append((label, benefit, grp, len(ps), k, round(100 * k / len(ps), 1)))
db.execute('''CREATE TABLE r_senior_takeup (eligible_group TEXT, benefit TEXT, value_band TEXT,
  households INTEGER, claiming INTEGER, pct_claiming REAL)''')
db.executemany('INSERT INTO r_senior_takeup VALUES (?,?,?,?,?,?)', tk)
db.commit()

# =====================================================================
# Dictionary
# =====================================================================
db.execute('CREATE TABLE r_dictionary (object TEXT, column_name TEXT, meaning TEXT)')
D = [
    ('r_parcel_clean', '*', 'One row per residential city parcel with cleaned fields. Built from v_parcel_master; '
                            'originals untouched.'),
    ('r_parcel_clean', 'owner_type', 'individual / trust / estate / llc_corp / association / government_institution, '
                                     'from owner-name keywords.'),
    ('r_parcel_clean', 'tenure_basis', 'sale = last arms-length sale; homestead = county year applied; '
                                       'homestead_2007_floor = 2007 freeze conversion, so owned AT LEAST since 2007; '
                                       'deed_any = earliest deed; none.'),
    ('r_parcel_clean', 'tenure_years', f'{ANALYSIS_YEAR} minus tenure_start_year, after dropping years before 1900 '
                                       '(the original had year 0/1 values).'),
    ('r_parcel_clean', 'owner_occupied_best', '1 if any homestead exemption is on file (legally requires residence) or '
                                              'mailing = property address; NULL if unknown (e.g. PO box).'),
    ('r_parcel_clean', 'age_proven', 'Highest minimum age proven by any exemption code held (city or county). '
                                     'NULL = no age evidence.'),
    ('r_parcel_clean', 'income_proven_under', 'Lowest income ceiling of any income-tested code held (bases differ: '
                                              'GA net, gross, federal AGI).'),
    ('r_parcel_clean', 'value_decile', '1 = lowest 10% of county appraised value among improved residential parcels '
                                       '(vacant lots and common areas excluded).'),
    ('r_parcel_clean', 'in_analysis_universe', f'Improved residential, individual/trust/estate owner, has a '
                                               f'{ANALYSIS_YEAR} city bill, not sold since Jan 1 {ANALYSIS_YEAR}. '
                                               'All gap lists use this universe.'),
    ('r_gap_candidates', 'tier', 'A = age proven, a city benefit missing; B = basic homestead filed with one office '
                                 'only; C = likely senior, filed nowhere (population estimate); D = county senior '
                                 'tier missing (low dollar value).'),
    ('r_gap_candidates', 'status', 'proven = every condition shown by existing filings; likely = strong evidence, '
                                   'one condition unconfirmed; possible = inference only.'),
    ('r_parcel_clean', 'county_codes', 'County exemption codes from the county PROFILE page (complete). The '
                                       'exemptions-page codes used by v_parcel_master missed 77 parcels; kept '
                                       'as county_codes_exemptions_page.'),
    ('r_parcel_clean', 'has_county_basic', 'Any county homestead code on file (from the profile page).'),
    ('r_parcel_clean', 'age_floor_now', 'Minimum age as of Jan 1 of the analysis year implied by how long a senior '
                                        'code has been held: min age of the code + years since granted.'),
    ('r_parcel_clean', 'age_proven_now', 'max(age_proven, age_floor_now). Used by the gap rules.'),
    ('r_gap_candidates', 'est_annual_homeowner_savings_county_tax', 'Unclaimed relief on the DeKalb County bill. '
                                        'For a missing county homestead: basic exemption credit + HOST/EHOST '
                                        'credit, from what recent filers receive (see r_settings). Excludes '
                                        'freeze growth and the state HTRG grant, so conservative.'),
    ('r_filing_rates', '*', 'Among likely owner-occupied homes in the analysis universe: share with a basic '
                            'homestead at both offices, city only, county only, or neither, by segment.'),
    ('r_senior_takeup', '*', 'Among households whose age (and income, where relevant) is proven by COUNTY records '
                             'only: share claiming each city senior benefit, by value band. County-only evidence '
                             'avoids circularity (a city code would both prove age and count as claiming).'),
    ('r_gap_candidates', 'est_annual_homeowner_savings_county_tax (accuracy)', 'Model checked on 1,117 county '
                             'homesteads granted 2023-2026: median error 7%; totals run ~7% high.'),
    ('r_gap_candidates', 'strength', 'high / medium / low. Tier C: high = owned 20+ yrs AND bottom 30% value; '
                                     'medium = owned 30+ yrs, or 20-29 yrs; low = bottom 30% value only (owned under 20 yrs).'),
    ('r_parcel_clean', 'tenure_basis=deed_any', 'Earliest deed of any kind; can predate the current owner '
                                                '(one parcel shows a 1917 deed).'),
    ('r_gap_candidates', 'est_annual_homeowner_savings_city_tax', 'Unclaimed relief: what the HOMEOWNER would save per year on their City of Decatur tax bill by filing the missing exemption (not county tax). Exempt value x 2026 city tax rate, capped at the taxable value left '
                                               'on that levy. NULL where county rates would be needed.'),
    ('r_gap_candidates', 'income_dependent', '1 = the benefit also depends on an income test not proven by existing '
                                             'filings.'),
    ('ref_exemption_rules', '*', 'Official city and county exemption terms, plus the amount actually seen on 2026 '
                                 'bills.'),
    ('ref_tax_rates', '*', 'City tax rates in mills (dollars per $1,000 of assessed value), read from the 2026 bills.'),
    ('r_city_levy_2026', '*', 'Per-parcel 2026 city bill: assessed value, exempt value on the general and school '
                              'levies. City bills are semiannual and the database holds only the first (March) '
                              '2026 bill, so billed and credit amounts are half-year figures.'),
    ('r_gap_candidates', 'est_annual_homeowner_savings_city_tax (check)', 'Validated: 2 x the first-half credit equals amount x rate on '
                                                        '5,860/5,872 GH-1, 1,554/1,558 GH-2, 468/469 GH-3 and '
                                                        '751/752 S-3 bills.'),
]
db.executemany('INSERT INTO r_dictionary VALUES (?,?,?)', D)
db.commit()
db.execute('ANALYZE')
db.commit()
print('gap rows:', len(gaps))
for r in db.execute('SELECT * FROM r_gap_summary'):
    print(tuple(r))
print()
for r in db.execute('SELECT * FROM r_data_quality'):
    print(tuple(r))
db.close()
