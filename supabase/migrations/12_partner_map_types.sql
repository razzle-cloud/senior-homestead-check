-- 12_partner_map_types: colour the partner map by WHICH exemption is missing (which office to visit),
-- not by how certain the gap is. Replaces site_outreach_map; same checks and logging as before.
-- Classes: 1 county homestead missing, 2 city homestead missing, 3 senior exemption missing (age proven),
--          4 senior exemption likely, 5 owner since before 1990 with no senior exemption,
--          6 possible county senior gap, 0 none. Where a home has several, the lowest number wins.
create or replace function public.site_outreach_map(p_email text)
returns jsonb
language plpgsql security definer
set search_path = pg_catalog, public
as $$
declare
  ok boolean;
  res jsonb;
begin
  select exists (select 1 from app.outreach_users u where lower(u.email) = lower(p_email) and u.active) into ok;
  insert into app.access_log (email, action, detail)
  values (p_email, case when ok then 'map' else 'denied' end, null);
  if not ok then
    return jsonb_build_object('status', 'not_allowed');
  end if;

  with g as (
    select parcel_id,
           bool_or(gap_code = 'COUNTY_BASIC_MISSING') as c1,
           bool_or(gap_code = 'CITY_BASIC_MISSING') as c2,
           bool_or(status = 'proven' and gap_code in ('GH2_MISSING', 'GH3_MISSING', 'SCHOOL_70_MISSING')) as c3,
           bool_or(status = 'likely') as c4,
           bool_or(gap_code = 'COUNTY_SENIOR_MISSING') as c6
    from analysis.r_gap_candidates where tier in ('A', 'B', 'D')
    group by parcel_id
  ), lt as (
    select distinct parcel_id from census.census_priority_long_tenure where has_any_senior_code = 0
  ), c as (
    select parcel_id,
           case when g.c1 then 1 when g.c2 then 2 when g.c3 then 3 when g.c4 then 4
                when lt.parcel_id is not null then 5 when g.c6 then 6 else 0 end as cls
    from g full join lt using (parcel_id)
  )
  select jsonb_build_object(
           'status', 'ok',
           'data_as_of', '2026-09',
           'origin', (select v from app.map_meta where k = 'origin'),
           'city', (select v from app.map_meta where k = 'city'),
           'streets', (select jsonb_agg(jsonb_build_array(name, road_class, line) order by id) from app.map_streets),
           'parcels', (select jsonb_agg(jsonb_build_array(
                                case when coalesce(c.cls, 0) > 0 then m.parcel_id end,
                                coalesce(c.cls, 0), m.rings) order by m.id)
                       from app.map_parcels m left join c using (parcel_id))
         ) into res;
  return res;
end $$;

revoke all on function public.site_outreach_map(text) from public, anon, authenticated;
grant execute on function public.site_outreach_map(text) to service_role;
