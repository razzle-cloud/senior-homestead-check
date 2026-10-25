#!/usr/bin/env python3
"""Refresh the parcel lists from the two public ArcGIS layers into Supabase.

  raw.city_parcels   <- City of Decatur parcels layer (owner + mailing address)
  raw.county_parcels <- DeKalb Tax_Parcels_YYYY, TAX_DISTRICT='92' (values)

The county publishes a new Tax_Parcels_YYYY layer each year. With
COUNTY_GIS_LAYER = "auto" the newest one is used. Both tables are archived
before the first write. Parcels that disappear from a layer are left in place
(they are reported, not deleted).

  python pull_gis.py --list-layers         # show the county's Tax_Parcels layers
  python pull_gis.py                       # refresh both
  python pull_gis.py --only county --layer Tax_Parcels_2026
"""
import argparse
import logging
import re

import config
from common import DB, Blocked, PoliteSession, StopRun, now, save_raw, setup_logging

log = logging.getLogger("decatur")


def county_layers(session):
    r = session.get(config.COUNTY_GIS_ROOT, params={"f": "json"})
    r.raise_for_status()
    names = [s["name"] for s in r.json().get("services", []) if s.get("type") == "FeatureServer"]
    return sorted((n for n in names if re.fullmatch(r"Tax_Parcels_\d{4}", n)), reverse=True)


def county_url(session, layer):
    if layer == "auto":
        layers = county_layers(session)
        if not layers:
            raise SystemExit("No Tax_Parcels_YYYY layer found; set COUNTY_GIS_LAYER in config.py")
        layer = layers[0]
        log.info("county GIS layer: %s (newest of %s)", layer, ", ".join(layers[:4]))
    return layer, f"{config.COUNTY_GIS_ROOT}/{layer}/FeatureServer/0/query"


def page_query(session, url, where, tag):
    offset = page = 0
    while True:
        params = {"where": where, "outFields": "*", "returnGeometry": "false",
                  "resultOffset": offset, "resultRecordCount": 2000,
                  "orderByFields": "OBJECTID", "f": "json"}
        r = session.get(url, params=params)
        r.raise_for_status()
        save_raw(config.RAW_DIR / "gis" / tag / f"page_{page:03d}.json", r.text)
        data = r.json()
        if "error" in data:
            raise RuntimeError(data["error"])
        feats = data.get("features", [])
        for f in feats:
            yield f["attributes"]
        log.info("  %s offset=%d got %d", tag, offset, len(feats))
        if not feats or not data.get("exceededTransferLimit"):
            break
        offset += len(feats)
        page += 1


def pull_city(session, db):
    ts, n, skipped, seen = now(), 0, 0, set()
    for a in page_query(session, config.CITY_GIS, "1=1", "city"):
        pid = config.norm_pin(a.get("PARCELID"))
        if not pid:
            skipped += 1
            continue
        seen.add(pid)
        db.upsert("city_parcels", dict(
            parcel_id=pid, objectid=a.get("OBJECTID"), prclkey=a.get("PRCLKEY"),
            owner1=a.get("OWNERNME1"), owner2=a.get("OWNERNME2"),
            site_address=a.get("SITEADDRESS"), address_number=a.get("ADDRESS_NUMBER"),
            street_name=a.get("FULL_STREET_NAME"), unit_no=a.get("UNIT_NO"),
            mail_address=a.get("PSTLADDRESS"), mail_city=a.get("PSTLCITY"),
            mail_state=a.get("PSTLSTATE"), mail_zip5=a.get("PSTLZIP5"),
            class_code=a.get("CLASSDSCRP") or a.get("CLASSCD"), landuse=a.get("LANDUSE"),
            zoning=a.get("ZONING"), assessed_value=a.get("CNTASSDVAL"),
            appraised_value=a.get("TOTAPR1"), acreage=a.get("ACREAGE"),
            status=a.get("STATUS"), fetched_at=ts))
        n += 1
    db.commit()
    report_missing(db, "city_parcels", seen)
    log.info("city_parcels: %d upserted, %d skipped (no parcel id)", n, skipped)


def pull_county(session, db, layer):
    layer, url = county_url(session, layer)
    ts, n, skipped, seen = now(), 0, 0, set()
    for a in page_query(session, url, config.COUNTY_GIS_WHERE, "county_" + layer):
        pid = config.norm_pin(a.get("ParcelID") or a.get("PARCELID"))
        if not pid:
            skipped += 1
            continue
        seen.add(pid)
        db.upsert("county_parcels", dict(
            parcel_id=pid, objectid=a.get("OBJECTID"), tax_district=a.get("TAX_DISTRICT"),
            taxyr=a.get("TAXYR"), property_class=a.get("PROPERTY_CLASS"),
            landuse_code=a.get("LANDUSECODE"), zoning=a.get("ZONING"),
            assessed_value=a.get("ASSESSED_VALUE"), computed_assessed=a.get("COMPUTED_ASSESSED"),
            appraised_value=a.get("APPRAISED_VALUE"), computed_appraised=a.get("COMPUTED_APPRAISED"),
            land_value=a.get("LAND_VALUE"), bldg_value=a.get("BLDG_VALUE"),
            stated_area=a.get("StatedArea"), status=a.get("STATUS"), fetched_at=ts))
        n += 1
    if n == 0:
        db.rollback()
        raise SystemExit(f"{layer} returned no parcels for {config.COUNTY_GIS_WHERE}; nothing written")
    db.commit()
    report_missing(db, "county_parcels", seen)
    log.info("county_parcels from %s: %d upserted, %d skipped (no parcel id)", layer, n, skipped)


def report_missing(db, table, seen):
    have = {r[0] for r in db.execute(f"select parcel_id from raw.{table}").fetchall()}
    gone = sorted(have - seen)
    if gone:
        log.info("%s: %d parcels in the database were not in this pull (kept; e.g. %s)",
                 table, len(gone), ", ".join(gone[:5]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=["city", "county"])
    ap.add_argument("--layer", default=config.COUNTY_GIS_LAYER)
    ap.add_argument("--list-layers", action="store_true")
    args = ap.parse_args()
    setup_logging("pull_gis")
    if args.list_layers:
        s = PoliteSession("gis", 10)
        print("\n".join(county_layers(s)) or "none found")
        return
    db = DB("gis", vars(args))
    budget = config.DAILY_BUDGET["gis"] - db.requests_today("gis")
    session = PoliteSession("gis", budget)
    status, note = "finished", None
    try:
        if args.only != "county":
            pull_city(session, db)
        if args.only != "city":
            pull_county(session, db, args.layer)
    except (Blocked, StopRun) as e:
        db.rollback()
        status, note = getattr(e, "status", "stopped_blocked"), str(e)
        log.warning("%s", e)
    for t in ("city_parcels", "county_parcels"):
        log.info("%s now has %d rows", t, db.execute(f"select count(*) from raw.{t}").fetchone()[0])
    db.update_run(session, status=status, note=note)


if __name__ == "__main__":
    main()
