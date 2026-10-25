#!/usr/bin/env python3
"""How complete is the data in Supabase? Read-only; makes no web requests.

  python coverage.py
"""
import config
from common import connect, database_url


def show(conn, title, q, params=None):
    cur = conn.execute(q, params)
    rows = cur.fetchall()
    cols = [d.name for d in cur.description]
    print(f"\n== {title}")
    widths = [max([len(str(c))] + [len(str(r[i] if r[i] is not None else "")) for r in rows]) for i, c in enumerate(cols)]
    print("  " + "  ".join(str(c).ljust(w) for c, w in zip(cols, widths)))
    for r in rows:
        print("  " + "  ".join(str(v if v is not None else "").ljust(w) for v, w in zip(r, widths)))


def main():
    conn = connect(database_url())
    show(conn, "Parcel universe", """
      select 'city GIS residential' as what, count(*) as parcels, max(fetched_at)::date as last_pulled
        from raw.city_parcels where class_code like 'R%'
      union all select 'county GIS residential', count(*), max(fetched_at)::date
        from raw.county_parcels where property_class like 'R%'
      union all select 'either (pull universe)', count(*), null from (
        select parcel_id from raw.city_parcels where class_code like 'R%'
        union select parcel_id from raw.county_parcels where property_class like 'R%') u""")
    show(conn, "City bills: prefixes by year and status", """
      select tax_year, status, count(*) as prefixes, sum(fetched_records) as records,
             max(updated_at)::date as last_update
      from raw.city_search_log group by 1, 2 order by 1 desc, 2""")
    show(conn, "City bills: parcels with a bill", """
      select b.tax_year, count(distinct b.parcel_id) as parcels_billed,
             count(distinct b.parcel_id) filter (where p.class_code like 'R%') as residential_billed,
             (select count(*) from raw.city_parcels where class_code like 'R%') as residential_total
      from raw.city_bills b left join raw.city_parcels p using (parcel_id)
      group by 1 order by 1 desc""")
    show(conn, "County pages: status by page type and tax year", """
      select mode, tax_year, status, count(*) as pages, max(fetched_at)::date as last_fetch
      from raw.county_fetch_log group by 1, 2, 3 order by 1, 2 desc, 3""")
    show(conn, "County pages still needed for the current tax year (primary page types)", """
      with u as (select parcel_id from raw.city_parcels where class_code like 'R%%'
                 union select parcel_id from raw.county_parcels where property_class like 'R%%'),
           m(mode) as (values ('dek_exemptions'), ('dek_profile'))
      select m.mode,
             count(*) filter (where l.parcel_id is null) as never_fetched,
             count(*) filter (where l.status in ('error','parse_error','blocked')) as failed_or_blocked,
             count(*) filter (where l.status in ('ok','nodata') and l.tax_year < %s) as older_tax_year,
             count(*) filter (where l.status in ('ok','nodata') and l.tax_year >= %s) as current
      from u cross join m left join raw.county_fetch_log l on l.parcel_id = u.parcel_id and l.mode = m.mode
      group by 1 order by 1""", (config.COUNTY_TAX_YEAR, config.COUNTY_TAX_YEAR))
    show(conn, "Last 10 pull runs", """
      select run_id, source, started_at::timestamp(0) as started, finished_at::timestamp(0) as finished,
             status, requests, rows_written, blocks, left(coalesce(note,''), 60) as note
      from raw.pull_runs order by run_id desc limit 10""")
    show(conn, "Requests today by source (daily budgets: %s)" % config.DAILY_BUDGET, """
      select source, sum(requests) as requests_today from raw.pull_runs
      where started_at >= date_trunc('day', now()) group by 1 order by 1""")
    show(conn, "Archive snapshots", """
      select tablename from pg_tables where schemaname = 'archive' order by 1""")


if __name__ == "__main__":
    main()
