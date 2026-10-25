#!/usr/bin/env python3
"""Offline tests for the v2 pull. No web requests: HTTP is replaced by a fake
server, and the database is a LOCAL Postgres copy (never Supabase).

  TEST_DATABASE_URL=postgresql:///v2test?host=/var/run/postgresql python3 tests/test_offline.py

The test database must have the raw schema plus migration 05 applied.
"""
import json
import os
import sys
import time
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
URL = os.environ.get("TEST_DATABASE_URL")
if not URL or "supabase" in URL:
    sys.exit("Set TEST_DATABASE_URL to a local test database (never Supabase).")
os.environ["DATABASE_URL"] = URL
os.environ["PULL_CONTACT"] = "test@example.invalid"

import tempfile                                                  # noqa: E402
import config                                                    # noqa: E402
config.CONTACT = "test@example.invalid"
config.DELAY = {k: 0 for k in config.DELAY}
config.RAW_DIR = Path(tempfile.mkdtemp(prefix="v2raw_"))
config.LOG_DIR = Path(tempfile.mkdtemp(prefix="v2log_"))
SLEEPS = []
time.sleep = lambda s: SLEEPS.append(s)                          # no real waiting

import common                                                    # noqa: E402
import pull_city_bills                                           # noqa: E402
import pull_county                                               # noqa: E402
import requests                                                  # noqa: E402

conn = common.connect(URL)
conn.autocommit = True
def q(s, p=None):
    cur = conn.execute(s, p)
    return cur.fetchall() if cur.description else None
PASS = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""))
    PASS.append(cond)


class Resp:
    def __init__(self, status=200, text="", headers=None):
        self.status_code, self.text, self.headers = status, text, headers or {}

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def run(mod, argv, handler):
    calls = []

    def fake(self, method, url, **kw):
        calls.append((method, url, kw))
        return handler(method, url, kw)
    with mock.patch.object(requests.Session, "request", fake), mock.patch.object(sys, "argv", ["x"] + argv):
        mod.main()
    return calls


def last_run():
    return q("select status, requests, blocks, rows_written from raw.pull_runs order by run_id desc limit 1")[0]


# ------------------------------------------------------------------ city bills
PFX = "99 901"          # a synthetic prefix that cannot collide with real data


def rec(i, year=2026):
    return {"IDHash": f"test{year}{i:024d}", "ParcelNumber": f"{PFX} 01 {i:03d}", "BillingID": str(i),
            "IDs": {"ID1": {"Value": str(year)}, "ID3": {"Value": "1"}}, "RecordType": "Real Property",
            "OwnerName1": "TEST OWNER", "Values": {"Assessed": 100000.0, "Appraised": 250000.4},
            "Acres": 0.25, "Jurisdictions": [
                {"ID": "1", "Code": "ZGEN", "Description": "2026 CITY GENERAL", "Amount": 500.0, "isCharge": True},
                {"ID": "2", "Code": "XGEN", "Description": "2026 EX-ZGEN: GH-1", "Amount": -120.0, "isExempt": True}]}


def city_ok(total):
    recs = [rec(i) for i in range(total)]

    def h(method, url, kw):
        body = json.loads(kw["data"])
        if body["skip"] and not kw["headers"].get("SearchToken"):
            return Resp(200, json.dumps({"Records": [], "TotalRecords": total}))
        page = recs[body["skip"]: body["skip"] + 20]
        return Resp(200, json.dumps({"Records": page, "TotalRecords": total, "SearchToken": "tok"}))
    return h


def city_soft_block(method, url, kw):
    return Resp(200, json.dumps({"Message": "Too many requests. Please try again later."}))


q("delete from raw.city_bill_lines where id_hash like 'test%'")
q("delete from raw.city_bills where id_hash like 'test%'")
q("delete from raw.city_search_log where search_prefix = %s", (PFX,))
lines_before = q("select count(*) from raw.city_bill_lines")[0][0]

calls = run(pull_city_bills, ["--prefix", PFX, "--years", "2026"], city_ok(45))
check("city: pages fetched for 45 records = 3", len(calls) == 3, len(calls))
check("city: 45 bills stored", q("select count(*) from raw.city_bills where id_hash like 'test%'")[0][0] == 45)
check("city: 90 bill lines stored with new identity ids",
      q("select count(*), min(id) > 307332 from raw.city_bill_lines where id_hash like 'test%'")[0] == (90, True))
check("city: exemption code parsed", q("select count(*) from raw.city_bill_lines where id_hash like 'test%' and exemption_code='GH-1' and exempt_amount=120")[0][0] == 45)
check("city: prefix logged done", q("select status, fetched_records from raw.city_search_log where search_prefix=%s and tax_year=2026", (PFX,)) == [("done", 45)])
check("city: run finished", last_run()[0] == "finished", last_run())
check("city: archive snapshot made", q("select count(*) from pg_tables where schemaname='archive' and tablename like 'city\\_bills\\_\\_%%'")[0][0] == 1)

calls = run(pull_city_bills, ["--prefix", PFX, "--years", "2026"], city_ok(45))
check("city: rerun skips a done prefix (0 requests)", len(calls) == 0, len(calls))

calls = run(pull_city_bills, ["--prefix", PFX, "--years", "2026", "--force"], city_ok(45))
check("city: forced re-pull does not duplicate lines",
      q("select count(*) from raw.city_bill_lines where id_hash like 'test%'")[0][0] == 90)

# soft block: two prefixes, both soft-blocked -> pause once, then stop
q("delete from raw.city_search_log where search_prefix = %s", (PFX,))
SLEEPS.clear()
calls = run(pull_city_bills, ["--prefix", PFX, "--years", "2026", "2025"], city_soft_block)
st = q("select tax_year, status from raw.city_search_log where search_prefix=%s order by 1", (PFX,))
check("city: soft block logged 'blocked', never 'done'", st == [(2025, "blocked"), (2026, "blocked")], st)
check("city: paused 15-30 min after first block", any(900 <= s <= 1800 for s in SLEEPS), [round(s) for s in SLEEPS if s > 60])
check("city: run stopped after 2 blocks", last_run()[:3] == ("stopped_blocked", 2, 2), last_run())
check("city: earlier bills untouched by blocked run", q("select count(*) from raw.city_bills where id_hash like 'test%'")[0][0] == 45)

# block mid-prefix: page 1 ok, page 2 blocked -> nothing from this prefix committed
q("delete from raw.city_bill_lines where id_hash like 'test%'")
q("delete from raw.city_bills where id_hash like 'test%'")
q("delete from raw.city_search_log where search_prefix = %s", (PFX,))
ok = city_ok(45)
n = {"i": 0}


def midblock(m, u, kw):
    n["i"] += 1
    return ok(m, u, kw) if n["i"] == 1 else Resp(429, "slow down", {"Retry-After": "600"})


run(pull_city_bills, ["--prefix", PFX, "--years", "2026"], midblock)
check("city: block mid-prefix rolls back partial pages",
      q("select count(*) from raw.city_bills where id_hash like 'test%'")[0][0] == 0)
check("city: HTTP 429 treated as block", q("select status from raw.city_search_log where search_prefix=%s", (PFX,)) == [("blocked",)])

# budget
config.DAILY_BUDGET["city"] = q("select coalesce(sum(requests),0) from raw.pull_runs where source='city_bills' and started_at >= date_trunc('day', now())")[0][0] + 2
q("delete from raw.city_search_log where search_prefix = %s", (PFX,))
calls = run(pull_city_bills, ["--prefix", PFX, "--years", "2026"], city_ok(100))
check("city: daily budget stops the run", len(calls) == 2 and last_run()[0] == "stopped_budget", (len(calls), last_run()))
config.DAILY_BUDGET["city"] = 400

# ------------------------------------------------------------------ county
PID = "99 901 01 001"


def page(*divs):
    body = ""
    for i, (title, rows) in enumerate(divs):
        trs = f"<tr><td>{title}</td></tr>" + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
        body += f'<div id="datalet_div_{i}"><table>{trs}</table></div>'
    return f"<html><head><title>datalet</title></head><body>{body}</body></html>"


EX_HDR = ["Homestead Code", "Exemption", "Year Applied", "Base Year", "Frozen Base Value",
          "Const. Exempt", "HOST/DME Exempt", "Freeze Exempt", "Total Exempt"]
EX_PAGE = page(("Exemption Summary", [EX_HDR, ["H1F", "Basic", "1999", "2001", "$100,000", "$10,000", "", "", "$10,000"],
                                      ["H4", "Senior 65", "2015", "", "", "$4,000", "", "", "$4,000"]]))
EX_PAGE2 = page(("Exemption Summary", [EX_HDR, ["H1F", "Basic", "1999", "2001", "$100,000", "$10,000", "", "", "$10,000"]]))
NODATA = page(("Exemption Summary", [["-- No Data --"]]))
SALES = page(("Sales", [["Sale Date", "Price", "Tran Code", "Grantor", "Grantee", "Instrument", "Book/Page"],
                        ["01/02/1985", "$50,000", "Q", "A", "B", "WD", ""],
                        ["03/04/2020", "$0", "X", "B", "B TRUST", "QC", "123-45"]]))
pages = {"dek_exemptions": EX_PAGE, "dek_sales": SALES}


def county_h(method, url, kw):
    return Resp(200, pages[kw["params"]["mode"]])


for t in ("county_exemptions", "county_sales", "county_fetch_log"):
    q(f"delete from raw.{t} where parcel_id = %s", (PID,))

run(pull_county, ["--parcel", PID, "--modes", "dek_exemptions", "dek_sales"], county_h)
check("county: 2 exemptions stored", q("select code from raw.county_exemptions where parcel_id=%s order by 1", (PID,)) == [("H1F",), ("H4",)])
check("county: 2 sales stored (one with NULL book/page)", q("select count(*) from raw.county_sales where parcel_id=%s", (PID,))[0][0] == 2)
check("county: fetch log ok with hash", q("select count(*) from raw.county_fetch_log where parcel_id=%s and status='ok' and content_hash is not null", (PID,))[0][0] == 2)

pages["dek_exemptions"] = EX_PAGE2
run(pull_county, ["--parcel", PID, "--modes", "dek_exemptions", "dek_sales", "--force"], county_h)
check("county: removed exemption disappears on re-pull", q("select code from raw.county_exemptions where parcel_id=%s", (PID,)) == [("H1F",)])
check("county: re-pulled sales are not duplicated (NULLs equal)", q("select count(*) from raw.county_sales where parcel_id=%s", (PID,))[0][0] == 2)

pages["dek_exemptions"] = NODATA
run(pull_county, ["--parcel", PID, "--modes", "dek_exemptions", "--force"], county_h)
check("county: 'No Data' page -> nodata and exemptions cleared",
      q("select status from raw.county_fetch_log where parcel_id=%s and mode='dek_exemptions'", (PID,)) == [("nodata",)]
      and q("select count(*) from raw.county_exemptions where parcel_id=%s", (PID,))[0][0] == 0)

calls = run(pull_county, ["--parcel", PID, "--modes", "dek_exemptions", "dek_sales"], county_h)
check("county: incremental rerun fetches nothing", len(calls) == 0, len(calls))

for label, resp in [("403", Resp(403, "Forbidden")),
                    ("access-denied page", Resp(200, "<html><body><h1>Access Denied</h1></body></html>")),
                    ("page without datalet content", Resp(200, "<html><body>Please wait...</body></html>"))]:
    pages["dek_exemptions"] = EX_PAGE
    q("delete from raw.county_exemptions where parcel_id=%s", (PID,))
    q("insert into raw.county_exemptions (parcel_id, tax_year, code) values (%s, 2026, 'H1F')", (PID,))
    SLEEPS.clear()
    run(pull_county, ["--parcel", PID, "--parcel", "99 901 01 002", "--modes", "dek_exemptions", "--force"],
        lambda m, u, kw, r=resp: r)
    st = q("select status from raw.county_fetch_log where parcel_id=%s and mode='dek_exemptions'", (PID,))
    check(f"county: {label} -> 'blocked', data kept, run stopped",
          st == [("blocked",)] and last_run()[0] == "stopped_blocked"
          and q("select count(*) from raw.county_exemptions where parcel_id=%s", (PID,))[0][0] == 1,
          (st, last_run()))

calls = run(pull_county, ["--parcel", PID, "--modes", "dek_exemptions"], county_h)
check("county: blocked item is retried next run", len(calls) == 1 and
      q("select status from raw.county_fetch_log where parcel_id=%s and mode='dek_exemptions'", (PID,)) == [("ok",)])

calls = run(pull_county, ["--parcel", PID, "--modes", "dek_exemptions", "--reparse"], county_h)
check("county: --reparse reads saved pages, no requests", len(calls) == 0 and last_run()[0] == "finished")

# plan mode on the real parcel universe: no requests, sensible size
calls = run(pull_county, ["--plan"], county_h)
check("county: --plan makes no requests", len(calls) == 0)

# ------------------------------------------------------------------ GIS
import pull_gis                                                  # noqa: E402


def gis_h(method, url, kw):
    if url.endswith("/services"):
        return Resp(200, json.dumps({"services": [{"name": n, "type": "FeatureServer"} for n in
                                                  ("Tax_Parcels_2024", "Tax_Parcels_2026", "Tax_Parcels_2025", "Other")]}))
    if "Tax_Parcels_2026" in url:
        return Resp(200, json.dumps({"features": [{"attributes": {"ParcelID": "99 901 01 001", "TAX_DISTRICT": "92",
                     "TAXYR": "2026", "PROPERTY_CLASS": "R3", "ASSESSED_VALUE": 123456.6, "OBJECTID": 1}}]}))
    return Resp(404, "unexpected url " + url)


calls = run(pull_gis, ["--only", "county"], gis_h)
check("gis: auto picks newest Tax_Parcels layer (2026)", any("Tax_Parcels_2026" in c[1] for c in calls))
check("gis: county parcel upserted, decimal value rounded into bigint column",
      q("select taxyr, assessed_value from raw.county_parcels where parcel_id='99 901 01 001'") == [("2026", 123457)])
calls = run(pull_county, ["--plan", "--parcel", "99 901 01 001", "--changed-gis"], county_h)
check("county: --changed-gis finds the new GIS parcel", len(calls) == 0)
q("delete from raw.county_parcels where parcel_id like '99 901%%'")

# ------------------------------------------------------------------ cleanup
for t in ("county_exemptions", "county_sales", "county_fetch_log"):
    q(f"delete from raw.{t} where parcel_id like '99 901%%'")
q("delete from raw.city_bill_lines where id_hash like 'test%'")
q("delete from raw.city_bills where id_hash like 'test%'")
q("delete from raw.city_search_log where search_prefix = %s", (PFX,))
check("cleanup: bill lines back to original count", q("select count(*) from raw.city_bill_lines")[0][0] == lines_before)

print(f"\n{sum(PASS)}/{len(PASS)} checks passed")
sys.exit(0 if all(PASS) else 1)
