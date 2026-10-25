#!/usr/bin/env python3
"""Pull DeKalb County Tax Commissioner pages (Tyler iasWorld "datalets") into Supabase.

One HTML GET per parcel per page type:
  dek_exemptions -> raw.county_exemptions    dek_profile -> raw.county_profile
  mailing        -> raw.county_owner_history dek_sales   -> raw.county_sales
  residential    -> raw.county_residential

What is different from v1
  * Block detection: HTTP 403/429, "access denied"/"too many requests" pages, and
    pages with no datalet content are treated as blocks, never as 'nodata'.
    The item is logged 'blocked', the run pauses 15-30 minutes, and it stops
    after the second block.
  * Incremental: by default only fetches what is missing, failed, blocked, or
    from an older tax year. --refresh-days and --changed-gis add more.
  * Parcel list includes residential parcels from the county GIS layer as well
    as the 2024 city snapshot, so newly split parcels are picked up.
  * Exemption rows for a parcel/year are replaced, so removed exemptions disappear.
  * A daily request budget (config.DAILY_BUDGET['county']) across all runs.

  python pull_county.py --plan                         # what would be fetched; no requests
  python pull_county.py --limit 20                     # smoke test
  python pull_county.py                                # primary modes (exemptions, profile)
  python pull_county.py --modes all --max-minutes 240
  python pull_county.py --changed-gis                  # parcels whose GIS values changed since last snapshot
  python pull_county.py --reparse --modes dek_sales    # re-parse saved pages, no requests
"""
import argparse
import hashlib
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

from bs4 import BeautifulSoup

import config
from common import DB, Blocked, PoliteSession, StopRun, now, read_raw, save_raw, setup_logging

log = logging.getLogger("decatur")


# ---------------------------------------------------------------- HTML helpers (as v1)
def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def num(s):
    if s is None:
        return None
    s = re.sub(r"[,$\s]", "", str(s))
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def intnum(s):
    v = num(s)
    return int(v) if v is not None else None


def date(s):
    s = clean(s)
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def sections(html):
    soup = BeautifulSoup(html, "lxml")
    out = {}
    for div in soup.select("div[id^=datalet_div_]"):
        rows = []
        for tr in div.find_all("tr"):
            if tr.find("table"):
                continue
            cells = [clean(c.get_text(" ", strip=True)) for c in tr.find_all(["td", "th"])]
            if any(cells):
                rows.append(cells)
        if not rows:
            continue
        title = rows[0][0] if len(rows[0]) == 1 or not any(rows[0][1:]) else div.get("id")
        body = rows[1:] if title != div.get("id") else rows
        out[title] = body
        out.setdefault(div.get("id"), body)
    return out


def kv(rows):
    d = {}
    for r in rows:
        r = [c for c in r if c != ""] or r
        if len(r) >= 2:
            d[r[0]] = r[1]
        elif len(r) == 1:
            d.setdefault(r[0], "")
    return d


BLOCK_RE = re.compile(r"too many requests|request rejected|access denied|temporarily blocked|"
                      r"unusual traffic|captcha|requested url was rejected|rate limit", re.I)


def page_status(html, http_status=200):
    """ok | nodata | error, or raise Blocked."""
    if http_status in (403, 429):
        raise Blocked(f"HTTP {http_status}")
    flat = re.sub(r"\s+", " ", html or "")
    if BLOCK_RE.search(flat[:5000]):
        raise Blocked("block message in page")
    if "An Error has Occurred" in flat or "<title>Object moved" in flat:
        return "error"
    if "datalet" not in flat.lower():
        raise Blocked(f"page has no datalet content ({len(flat)} bytes)")
    if "-- No Data --" in flat or "No Data" in flat:
        return "nodata"
    return "ok"


# --------------------------------------------------------------------- parsers
# Each parser returns a list of (table, row) pairs; writing happens in store().
def parse_dek_exemptions(html, pid, taxyr):
    sec = sections(html)
    htrg = None
    for r in sec.get("HTRG Credit") or []:
        for c in r:
            if c.startswith("$"):
                htrg = num(c)
    out = []
    for r in sec.get("Exemption Summary") or []:
        if not r or r[0] == "Homestead Code" or r[0].startswith("Total") or not re.match(r"^[A-Z]\d+[A-Z]?$", r[0]):
            continue
        r = (r + [""] * 9)[:9]
        out.append(("county_exemptions", dict(
            parcel_id=pid, tax_year=taxyr, code=r[0], description=r[1] or None,
            year_applied=intnum(r[2]), base_year=intnum(r[3]),
            frozen_base_value=num(r[4]), const_exempt_amt=num(r[5]),
            host_exempt_amt=num(r[6]), freeze_exempt_amt=num(r[7]),
            total_exempt_amt=num(r[8]), htrg_credit=htrg)))
    return out


def parse_dek_profile(html, pid, taxyr):
    sec = sections(html)
    info = kv(sec.get("Parcel Information") or [])
    own = kv(sec.get("Owner information") or [])
    if not info and not own:
        return []
    codes = clean(info.get("Exemption Codes", "")).strip(" /")
    return [("county_profile", dict(
        parcel_id=pid, owner=own.get("Owner") or None, co_owner=own.get("Co-Owner") or None,
        owner_address=own.get("Current Owner Address") or None,
        care_of=own.get("Care of Information") or None,
        tax_district=info.get("Tax District") or None, old_parcel_id=info.get("Old Parcel ID") or None,
        property_class=info.get("Property Class") or None, land_use_code=info.get("Land Use Code") or None,
        zoning=(info.get("Zoning") or "").strip("- ") or None, acres=num(info.get("Acres")),
        built_as=info.get("Built As") or None, dwelling_type=info.get("Dwelling Type") or None,
        new_construction=info.get("New Construction") or None,
        exemption_codes=codes or None, disabled=info.get("Disabled") or None,
        hs_app_mail_date=info.get("H/S Application Mail Date") or None))]


def parse_mailing(html, pid, taxyr):
    out = []
    for r in sections(html).get("Owner History") or []:
        if not r or not re.match(r"^(19|20)\d\d$", r[0]):
            continue
        r = (r + [""] * 4)[:4]
        out.append(("county_owner_history", dict(
            parcel_id=pid, tax_year=int(r[0]), owner_address_blob=r[1] or None,
            city_exmp_code=r[2] or None, county_exmp_code=r[3] or None)))
    return out


def parse_dek_sales(html, pid, taxyr):
    out = []
    for r in sections(html).get("Sales") or []:
        if not r or r[0] == "Sale Date" or not date(r[0]):
            continue
        r = (r + [""] * 7)[:7]
        out.append(("county_sales", dict(
            parcel_id=pid, sale_date=date(r[0]), price=num(r[1]), tran_code=r[2] or None,
            grantor=r[3] or None, grantee=r[4] or None, instrument=r[5] or None,
            book_page=r[6] or None)))
    return out


def parse_residential(html, pid, taxyr):
    d = kv(sections(html).get("Residential Structure") or [])
    if not d:
        return []
    return [("county_residential", dict(
        parcel_id=pid, building_no=d.get("Building #"), improvement_type=d.get("Improvement Type"),
        stories=d.get("Stories"), construction=d.get("Construction"), built_as=d.get("Built As"),
        living_area=intnum(d.get("Living Area")), quality_grade=d.get("Quaility Grade") or d.get("Quality Grade"),
        condition=d.get("Condition"), year_built=intnum(d.get("Year Built")),
        remodeled_year=intnum(d.get("Remodeled Year")), effective_year=intnum(d.get("Effective Year")),
        bedrooms=intnum(d.get("Bedrooms")), full_baths=intnum(d.get("Full Baths")),
        half_baths=intnum(d.get("Half Baths")), fireplaces=intnum(d.get("Fireplaces")),
        basement=d.get("Basement")))]


PARSERS = {
    "dek_exemptions": parse_dek_exemptions,
    "dek_profile": parse_dek_profile,
    "mailing": parse_mailing,
    "dek_sales": parse_dek_sales,
    "residential": parse_residential,
}


# ------------------------------------------------------------------- pipeline
def raw_path(raw_dir, mode, pid):
    return Path(raw_dir) / "county" / mode / (pid.replace(" ", "_") + ".html")


def fetch(session, mode, pid, taxyr):
    params = {"mode": mode, "UseSearch": "no", "pin": pid, "jur": "000", "taxyr": taxyr}
    r = session.get(config.IASWORLD_URL, params=params)
    return r.status_code, r.text


def store(db, mode, pid, taxyr, html, http_status, path, prev_hash):
    """Parse one page and write it in the current transaction. Raises Blocked."""
    status = page_status(html, http_status)
    note, rows = None, []
    if status == "ok":
        try:
            rows = PARSERS[mode](html, pid, taxyr)
            if not rows:
                status = "nodata"
        except Exception as e:
            log.exception("parse failed %s %s", mode, pid)
            status, note = "parse_error", str(e)[:250]
    if mode == "dek_exemptions" and status in ("ok", "nodata"):
        db.delete("county_exemptions", "parcel_id = %s and tax_year = %s", (pid, taxyr))
    for table, row in rows:
        if table == "county_sales":
            db.upsert(table, row, conflict=("county_sales_natural_key",
                                            ["parcel_id", "sale_date", "book_page", "price"]))
        else:
            db.upsert(table, row)
    h = hashlib.md5(repr(rows).encode()).hexdigest() if status in ("ok", "nodata") else None
    db.upsert("county_fetch_log", dict(
        parcel_id=pid, mode=mode, tax_year=taxyr, status=status, http_status=http_status,
        raw_path=str(path), note=note, fetched_at=now(), run_id=db.run_id, content_hash=h))
    changed = bool(prev_hash) and h is not None and h != prev_hash
    return status, len(rows), changed


def parcel_universe(db, parcels_arg):
    if parcels_arg:
        return [config.norm_pin(p) for p in parcels_arg]
    q = """
      select parcel_id from raw.city_parcels where class_code like 'R%'
      union
      select parcel_id from raw.county_parcels where property_class like 'R%'
      order by 1"""
    return [r[0] for r in db.execute(q).fetchall() if r[0]]


def changed_gis_parcels(db):
    """Parcels whose county GIS values differ from the newest archived snapshot."""
    snap = db.execute("select tablename from pg_tables where schemaname='archive' "
                      "and tablename like 'county\\_parcels\\_\\_%' order by 1 desc limit 1").fetchone()
    if not snap:
        log.warning("--changed-gis: no archived county_parcels snapshot yet (run pull_gis.py first)")
        return set()
    q = f"""
      select c.parcel_id from raw.county_parcels c
      left join archive."{snap[0]}" a using (parcel_id)
      where a.parcel_id is null
         or (c.assessed_value, c.appraised_value, c.property_class, c.taxyr)
            is distinct from (a.assessed_value, a.appraised_value, a.property_class, a.taxyr)"""
    out = {r[0] for r in db.execute(q).fetchall()}
    log.info("--changed-gis: %d parcels new or changed vs archive.%s", len(out), snap[0])
    return out


def build_todo(db, parcels, modes, taxyr, args):
    logged = {(p, m): (s, y, f, h) for p, m, s, y, f, h in db.execute(
        "select parcel_id, mode, status, tax_year, fetched_at, content_hash from raw.county_fetch_log").fetchall()}
    cutoff = datetime.now() - timedelta(days=args.refresh_days) if args.refresh_days else None
    changed = changed_gis_parcels(db) if args.changed_gis else set()
    buckets = {"never": [], "retry": [], "new tax year": [], "gis changed": [], "stale": [], "forced": []}
    for p in parcels:
        for m in modes:
            st, yr, fa, h = logged.get((p, m), (None, None, None, None))
            item = (p, m, h)
            if args.force or args.reparse:
                buckets["forced"].append(item)
            elif st is None:
                buckets["never"].append(item)
            elif st in ("error", "parse_error", "blocked"):
                buckets["retry"].append(item)
            elif yr is not None and yr < taxyr and m in ("dek_exemptions", "dek_profile", "mailing"):
                buckets["new tax year"].append(item)
            elif p in changed:
                buckets["gis changed"].append(item)
            elif cutoff and (fa is None or fa < cutoff):
                buckets["stale"].append(item)
    todo = [x for b in buckets.values() for x in b]
    return todo, {k: len(v) for k, v in buckets.items() if v}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modes", nargs="*", default=config.COUNTY_MODES_PRIMARY, help="page types, or 'all'")
    ap.add_argument("--limit", type=int, help="stop after N fetches (smoke test)")
    ap.add_argument("--parcel", action="append", help="specific parcel id(s)")
    ap.add_argument("--taxyr", type=int, default=config.COUNTY_TAX_YEAR)
    ap.add_argument("--force", action="store_true", help="re-fetch everything selected")
    ap.add_argument("--refresh-days", type=int, help="also re-fetch pages older than N days")
    ap.add_argument("--changed-gis", action="store_true", help="also re-fetch parcels whose GIS values changed")
    ap.add_argument("--max-minutes", type=float, help="stop cleanly after this many minutes")
    ap.add_argument("--plan", action="store_true", help="show what would be fetched; no web requests")
    ap.add_argument("--reparse", action="store_true", help="re-parse saved pages only; no web requests")
    ap.add_argument("--raw-dir", default=str(config.RAW_DIR), help="where raw pages are saved/read")
    args = ap.parse_args()
    modes = config.COUNTY_MODES_ALL if args.modes == ["all"] else args.modes
    setup_logging("pull_county")

    db = DB("county", vars(args), snapshot=not args.plan)
    parcels = parcel_universe(db, args.parcel)
    todo, buckets = build_todo(db, parcels, modes, args.taxyr, args)
    if args.limit:
        todo = todo[: args.limit]
    used = db.requests_today("county")
    budget = config.DAILY_BUDGET["county"] - used
    log.info("%d parcels x %s -> %d to do %s. Requests used today: %d, budget left: %d",
             len(parcels), modes, len(todo), buckets, used, budget)
    if args.plan:
        days = len(todo) / max(1, config.DAILY_BUDGET["county"])
        print(f"About {len(todo)} requests; at the daily budget that is about {days:.1f} day(s) of runs.")
        db.update_run(status="plan_only")
        return
    if not args.reparse and budget <= 0:
        db.update_run(status="stopped_budget", note="no budget left today")
        log.warning("Daily county budget already used. Try again tomorrow.")
        return

    session = None if args.reparse else PoliteSession("county", budget, max_minutes=args.max_minutes)
    counts, changed_n, status, note = {}, 0, "finished", None
    try:
        for i, (pid, mode, prev_hash) in enumerate(todo, 1):
            path = raw_path(args.raw_dir, mode, pid)
            try:
                if args.reparse:
                    html = read_raw(path)
                    if html is None:
                        continue
                    http = 200
                else:
                    http, html = fetch(session, mode, pid, args.taxyr)
                    save_raw(path, html)
                st, n, changed = store(db, mode, pid, args.taxyr, html, http, path, prev_hash)
                db.commit()
                changed_n += changed
            except Blocked as e:
                db.rollback()
                db.upsert("county_fetch_log", dict(
                    parcel_id=pid, mode=mode, tax_year=args.taxyr, status="blocked", http_status=None,
                    raw_path=None, note=str(e)[:250], fetched_at=now(), run_id=db.run_id))
                db.commit()
                st = "blocked"
                if session is None:
                    log.warning("saved page for %s %s looks like a block page: %s", mode, pid, e)
                else:
                    db.update_run(session)
                    session.handle_block(str(e))
            except StopRun:
                raise
            except Exception as e:
                db.rollback()
                log.exception("failed %s %s", mode, pid)
                st = "error"
                try:
                    db.upsert("county_fetch_log", dict(
                        parcel_id=pid, mode=mode, tax_year=args.taxyr, status="error", http_status=None,
                        raw_path=None, note=str(e)[:250], fetched_at=now(), run_id=db.run_id))
                    db.commit()
                except Exception:
                    db.reconnect()
            counts[(mode, st)] = counts.get((mode, st), 0) + 1
            if i % 50 == 0 or i == len(todo):
                log.info("%d/%d  %s  changed=%d", i, len(todo),
                         "  ".join(f"{m}:{s}={c}" for (m, s), c in sorted(counts.items())), changed_n)
                db.update_run(session)
    except StopRun as e:
        db.rollback()
        status, note = e.status, str(e)
        log.warning("%s", e)
    except KeyboardInterrupt:
        db.rollback()
        status, note = "stopped_by_user", "Ctrl-C"
    db.update_run(session, status=status, note=note)
    log.info("run %d %s. requests=%d rows=%d pages whose content changed=%d  %s",
             db.run_id, status, session.calls if session else 0, db.rows, changed_n, counts)


if __name__ == "__main__":
    main()
