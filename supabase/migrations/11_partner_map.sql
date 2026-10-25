-- 11_partner_map: parcel-level map for signed-in partners only.
-- Shapes are precomputed once (Web Mercator metres, relative to an origin, simplified,
-- delta-encoded). Gap status is added at request time by site_outreach_map, which checks
-- the allowlist and logs every call, exactly like site_outreach.

create table if not exists app.map_meta (k text primary key, v jsonb not null);
create table if not exists app.map_parcels (id serial primary key, parcel_id text, rings jsonb not null);
create table if not exists app.map_streets (id serial primary key, name text, road_class int, line jsonb not null);
alter table app.map_meta enable row level security;
alter table app.map_parcels enable row level security;
alter table app.map_streets enable row level security;
revoke all on app.map_meta, app.map_parcels, app.map_streets from anon, authenticated;

create or replace function app.enc_line(g extensions.geometry, ox double precision, oy double precision)
returns jsonb language sql immutable
set search_path = pg_catalog, extensions, public
as $$
  with p as (
    select (d).path[array_upper((d).path, 1)] as i,
           round(st_x((d).geom) - ox)::int as x,
           round(st_y((d).geom) - oy)::int as y
    from st_dumppoints(g) d
  ), q as (
    select i, x - coalesce(lag(x) over w, 0) as dx, y - coalesce(lag(y) over w, 0) as dy,
           row_number() over w as rn
    from p window w as (order by i)
  )
  select coalesce(jsonb_agg(t.v order by q.i, t.k), '[]'::jsonb)
  from q cross join lateral (values (1, q.dx), (2, q.dy)) as t(k, v)
  where q.rn = 1 or q.dx <> 0 or q.dy <> 0
$$;


do $$
declare ox double precision; oy double precision;
begin
  select floor(st_xmin(e)) - 50, floor(st_ymin(e)) - 50 into ox, oy
  from (select extensions.st_transform(geom, 3857) as e from geo.city_limits limit 1) s;

  insert into app.map_meta values ('origin', jsonb_build_array(ox, oy));

  insert into app.map_meta
  select 'city', jsonb_agg(app.enc_line(extensions.st_exteriorring((dp).geom), ox, oy))
  from geo.city_limits c,
       lateral extensions.st_dump(extensions.st_simplifypreservetopology(extensions.st_transform(c.geom, 3857), 2)) dp;

  insert into app.map_parcels (parcel_id, rings)
  select ps.parcel_id, jsonb_agg(app.enc_line(extensions.st_exteriorring((dp).geom), ox, oy))
  from geo.parcel_status ps,
       lateral extensions.st_dump(extensions.st_simplifypreservetopology(extensions.st_transform(ps.geom, 3857), 0.6)) dp
  group by ps.gid, ps.parcel_id
  order by ps.gid;

  insert into app.map_streets (name, road_class, line)
  select s.name, s.road_class, app.enc_line((dp).geom, ox, oy)
  from geo.streets s,
       lateral extensions.st_dump(extensions.st_simplify(extensions.st_transform(s.geom, 3857), 2)) dp;
end $$;

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
           bool_or(status = 'proven') as pr,
           bool_or(status = 'likely') as li,
           bool_or(status = 'possible' and tier = 'D') as po
    from analysis.r_gap_candidates where tier in ('A', 'B', 'D')
    group by parcel_id
  ), lt as (
    select distinct parcel_id from census.census_priority_long_tenure where has_any_senior_code = 0
  ), c as (
    select parcel_id,
           case when g.pr then 1 when g.li then 2 when lt.parcel_id is not null then 3 when g.po then 4 else 0 end as cls
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
revoke all on function app.enc_line(extensions.geometry, double precision, double precision) from public, anon, authenticated;
