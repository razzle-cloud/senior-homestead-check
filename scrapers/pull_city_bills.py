#!/usr/bin/env python3
"""Pull City of Decatur tax bills (Sturgis "Wildfire" JSON API) into Supabase.

Prefix search, 20 records per page, SearchToken header for later pages. Each
6-character parcel prefix ("15 234") found in raw.city_parcels is searched once
per tax year.

What is different from v1
  * A "Too many requests" reply comes back as a normal 200 response. v1 stored
    it as zero records and marked the prefix done. v2 recognises it, logs the
    prefix as 'blocked' (never 'done'), pauses 15-30 minutes, and stops the run
    after the second block.
  * Incremental by default: prefixes already 'done' for a year are skipped, so a
    run only fills gaps (partial / error / blocked / never tried).
  * A daily request budget (config.DAILY_BUDGET['city']) across all runs.
  * Writes go straight to Supabase; raw.city_bills is archived before the first write.

  python pull_city_bills.py --plan                # show what would be fetched, no requests
  python pull_city_bills.py                       # fill gaps for config.CITY_YEARS
  python pull_city_bills.py --years 2026 --prefix "15 234" --force
  python pull_city_bills.py --refresh-days 30     # also re-pull prefixes older than 30 days
"""
import argparse
import json
import logging
import re
from datetime import datetime, timedelta

import config
from common import DB, Blocked, PoliteSession, StopRun, now, save_raw, setup_logging

log = logging.getLogger("decatur")
EX_RE = re.compile(r"EX-([A-Z]+):\s*(\S+)", re.I)


# ------------------------------------------------------------- parsing (same as v1)
def parse_dt(s, date_only=False):
    if not s:
        return None
    s = s.rstrip("Z")
    try:
        dt = datetime.fromisoformat(s[:26])
    except ValueError:
        return None
    return dt.date() if date_only else dt


def bill_row(rec, prefix, ts):
    ids = rec.get("IDs") or {}

    def idv(k):
        v = ids.get(k)
        return v.get("Value") if isinstance(v, dict) else None
    situs = rec.get("SitusAddress") or {}
    mail = rec.get("OwnerAddress") or {}
    vals = rec.get("Values") or {}
    pay = rec.get("Payment") or {}
    return dict(
        id_hash=rec["IDHash"], parcel_id=config.norm_pin(rec.get("ParcelNumber")),
        billing_id=rec.get("BillingID"),
        tax_year=int(idv("ID1") or rec.get("Year") or 0) or None,
        installment=idv("ID3"), receipt=idv("ID2"),
        record_type=rec.get("RecordType"),
        owner1=rec.get("OwnerName1"), owner2=rec.get("OwnerName2"),
        description=rec.get("Description"),
        situs_line1=situs.get("Line1"), situs_line2=situs.get("Line2"),
        mail_line1=mail.get("Line1"), mail_line2=mail.get("Line2"),
        mail_city=mail.get("City"), mail_state=mail.get("State"), mail_zip=mail.get("Zip"),
        mortgage_name=rec.get("MortgageName") or None,
        district=rec.get("District"), zone_code=rec.get("ZoneCode"),
        zone_desc=rec.get("ZoneDescription"), acres=rec.get("Acres"),
        assessed_value=vals.get("Assessed"), appraised_value=vals.get("Appraised"),
        base_tax=vals.get("BaseTax"), original_due=vals.get("OriginalAmountDue"),
        amount_due=vals.get("AmountDue"),
        payment_status=pay.get("Status") or pay.get("PaymentStatus"),
        payment_date=parse_dt(pay.get("Date"), True),
        bill_date=parse_dt(rec.get("BillDate"), True),
        due_date=parse_dt(rec.get("DueDate"), True),
        last_updated=parse_dt(rec.get("LastUpdated")),
        version=rec.get("Version"), search_prefix=prefix, fetched_at=ts,
    )


def line_rows(rec):
    out = []
    for j in rec.get("Jurisdictions") or []:
        desc = j.get("Description") or ""
        m = EX_RE.search(desc)
        ex_code = ex_levy = None
        if m and (j.get("isExempt") or desc.upper().find("EX-") >= 0):
            ex_levy, ex_code = m.group(1).upper(), m.group(2).upper()
        amt = j.get("Amount")
        exempt_amount = j.get("ExemptAmount") or 0
        if ex_code and not exempt_amount and amt is not None:
            exempt_amount = -amt          # credit lines carry a negative Amount
        out.append(dict(
            id_hash=rec["IDHash"], line_id=j.get("ID"), code=j.get("Code"),
            description=desc, amount=amt, quantity=j.get("Quantity"),
            exempt_value=j.get("ExemptValue"), exempt_amount=exempt_amount,
            millage_rate=j.get("MillageRate"), installment=j.get("Installment"),
            is_charge=int(bool(j.get("isCharge"))), is_exempt=int(bool(j.get("isExempt"))),
            exemption_code=ex_code, exemption_levy=ex_levy,
        ))
    return out


# ------------------------------------------------------------- block detection
def check_reply(r):
    """Return parsed JSON, or raise Blocked if this is a throttle/soft-block reply."""
    text = r.text or ""
    if re.search(r"too many requests|rate limit|throttl|access denied", text[:2000], re.I):
        raise Blocked("soft block message in response body")
    try:
        data = r.json()
    except ValueError:
        raise Blocked(f"non-JSON reply (HTTP {r.status_code}, {len(text)} bytes)")
    if not isinstance(data, dict) or ("Records" not in data and "TotalRecords" not in data):
        raise Blocked("reply has no Records/TotalRecords fields")
    return data


def search(session, prefix, year, skip, token):
    headers = {"Content-Type": "application/json", "Origin": config.WILDFIRE_ORIGIN,
               "Referer": config.WILDFIRE_ORIGIN + "/"}
    if token:
        headers["SearchToken"] = token
    body = {"value": prefix, "skip": skip,
            "facets": {"Years": {str(year): True}, "Type": {"Real Property": True}},
            "direct": False}
    r = session.post(config.WILDFIRE_URL, headers=headers, data=json.dumps(body))
    return r, check_reply(r)


def store_records(db, records, prefix, ts):
    for rec in records:
        db.upsert("city_bills", bill_row(rec, prefix, ts))
        db.delete("city_bill_lines", "id_hash = %s", (rec["IDHash"],))
        for lr in line_rows(rec):
            db.insert("city_bill_lines", lr)


def log_prefix(db, prefix, year, status, total, fetched, note=None):
    db.upsert("city_search_log", dict(
        search_prefix=prefix, tax_year=year, status=status, total_records=total,
        fetched_records=fetched, updated_at=now(), note=note, run_id=db.run_id))


def pull_prefix(session, db, prefix, year):
    """Fetch every page for one prefix/year. Rows are committed only if the
    whole prefix completes; a block mid-way rolls this prefix back."""
    ts = now()
    skip, token, total, fetched, seen = 0, None, None, 0, set()
    out_dir = config.RAW_DIR / "city" / str(year)
    while True:
        r, data = search(session, prefix, year, skip, token)
        save_raw(out_dir / f"{prefix.replace(' ', '_')}_{skip:05d}.json", r.text)
        token = data.get("SearchToken") or token
        total = data.get("TotalRecords") or 0
        recs = data.get("Records") or []
        if total and not recs and skip == 0:
            raise Blocked("TotalRecords > 0 but no records on the first page")
        new = [x for x in recs if x.get("IDHash") and x["IDHash"] not in seen]
        seen.update(x["IDHash"] for x in new)
        store_records(db, new, prefix, ts)
        fetched += len(new)
        log.info("  %s %s skip=%d got=%d new=%d total=%d", prefix, year, skip, len(recs), len(new), total)
        if not recs or fetched >= total or not new:
            break
        skip += len(recs)
    status = "done" if fetched >= total else "partial"
    log_prefix(db, prefix, year, status, total, fetched)
    db.commit()
    return fetched, total, status


def plan(db, years, prefix, force, refresh_days):
    if prefix:
        prefixes = [prefix]
    else:
        prefixes = [r[0] for r in db.execute(
            "select distinct left(parcel_id, 6) from raw.city_parcels where parcel_id is not null order by 1").fetchall()]
    logged = {(p, y): (s, u) for p, y, s, u in db.execute(
        "select search_prefix, tax_year, status, updated_at from raw.city_search_log").fetchall()}
    cutoff = datetime.now() - timedelta(days=refresh_days) if refresh_days else None
    todo = []
    for y in years:
        for p in prefixes:
            st, upd = logged.get((p, y), (None, None))
            if force or st != "done" or (cutoff and (upd is None or upd < cutoff)):
                todo.append((p, y, st))
    return prefixes, todo


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--years", nargs="*", type=int, default=config.CITY_YEARS)
    ap.add_argument("--prefix", help="only this 6-char prefix, e.g. '15 234'")
    ap.add_argument("--force", action="store_true", help="re-pull even if logged done")
    ap.add_argument("--refresh-days", type=int, help="also re-pull prefixes last pulled more than N days ago")
    ap.add_argument("--max-minutes", type=float, help="stop cleanly after this many minutes")
    ap.add_argument("--plan", action="store_true", help="list what would be fetched; no web requests")
    args = ap.parse_args()
    setup_logging("pull_city_bills")

    db = DB("city_bills", vars(args), snapshot=not args.plan)
    prefixes, todo = plan(db, args.years, args.prefix, args.force, args.refresh_days)
    used = db.requests_today("city_bills")
    budget = config.DAILY_BUDGET["city"] - used
    kinds = {}
    for _, _, st in todo:
        kinds[st or "never tried"] = kinds.get(st or "never tried", 0) + 1
    log.info("%d prefixes x %s -> %d to fetch (%s). Requests used today: %d, budget left: %d",
             len(prefixes), args.years, len(todo),
             ", ".join(f"{k}={v}" for k, v in sorted(kinds.items())) or "nothing to do", used, budget)
    if args.plan:
        for p, y, st in todo[:200]:
            print(f"  {y} {p}  (currently: {st or 'never tried'})")
        db.update_run(status="plan_only")
        return
    if budget <= 0:
        db.update_run(status="stopped_budget", note="no budget left today")
        log.warning("Daily city budget already used. Try again tomorrow.")
        return

    session = PoliteSession("city", budget, max_minutes=args.max_minutes)
    status, note = "finished", None
    try:
        for i, (prefix, year, _) in enumerate(todo, 1):
            try:
                fetched, total, st = pull_prefix(session, db, prefix, year)
                log.info("[%d/%d] %s %s: %s (%d/%d)", i, len(todo), prefix, year, st, fetched, total)
            except Blocked as e:
                db.rollback()
                log_prefix(db, prefix, year, "blocked", None, None, str(e)[:250])
                db.commit()
                db.update_run(session)
                session.handle_block(str(e))       # pauses, or raises StopRun
            except StopRun:
                raise
            except Exception as e:
                db.rollback()
                log.exception("prefix %s year %s failed", prefix, year)
                try:
                    log_prefix(db, prefix, year, "error", None, None, str(e)[:250])
                    db.commit()
                except Exception:
                    db.reconnect()
            if i % 10 == 0:
                db.update_run(session)
    except StopRun as e:
        db.rollback()
        status, note = e.status, str(e)
        log.warning("%s", e)
    except KeyboardInterrupt:
        db.rollback()
        status, note = "stopped_by_user", "Ctrl-C"
    db.update_run(session, status=status, note=note)
    for y, n, p in db.execute("select tax_year, count(*), count(distinct parcel_id) from raw.city_bills "
                              "group by 1 order by 1").fetchall():
        log.info("city_bills %s: %d records, %d parcels", y, n, p)
    log.info("run %d %s. HTTP requests: %d, rows written: %d, blocks: %d",
             db.run_id, status, session.calls, db.rows, session.blocks)


if __name__ == "__main__":
    main()
