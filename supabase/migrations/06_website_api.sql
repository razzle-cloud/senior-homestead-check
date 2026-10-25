-- Website API: address lookup (public, rate-limited) and outreach list (signed-in, allowlisted).
-- Functions live in public so the edge functions can call them with the service role,
-- but anon/authenticated cannot execute them. All data stays in private schemas.

create schema if not exists app;
revoke all on schema app from public, anon, authenticated;

create table app.outreach_users (
  email      text primary key,
  name       text,
  org        text,
  active     boolean not null default true,
  added_at   timestamptz not null default now()
);
create table app.access_log (
  id      bigint generated always as identity primary key,
  at      timestamptz not null default now(),
  email   text,
  action  text not null,
  detail  jsonb
);
create table app.lookup_log (
  at       timestamptz not null default now(),
  ip_hash  text not null
);
create index on app.lookup_log (ip_hash, at);
create index on app.lookup_log (at);
alter table app.outreach_users enable row level security;
alter table app.access_log enable row level security;
alter table app.lookup_log enable row level security;

-- ---------------------------------------------------------------- address normalisation
create or replace function app.norm_addr(s text) returns text
language plpgsql immutable as $$
declare
  t text;
  pairs text[] := array[
    'STREET','ST','AVENUE','AVE','ROAD','RD','DRIVE','DR','LANE','LN','COURT','CT','PLACE','PL',
    'CIRCLE','CIR','BOULEVARD','BLVD','TERRACE','TER','PARKWAY','PKWY','TRAIL','TRL','HIGHWAY','HWY',
    'SQUARE','SQ','POINT','PT','ALLEY','ALY','WAY','WAY',
    'EAST','E','WEST','W','NORTH','N','SOUTH','S',
    'APT','UNIT','APARTMENT','UNIT','STE','UNIT','SUITE','UNIT'];
  i int;
begin
  t := upper(coalesce(s, ''));
  t := regexp_replace(t, '#', ' UNIT ', 'g');
  t := regexp_replace(t, '[^A-Z0-9 ]', ' ', 'g');
  t := ' ' || regexp_replace(t, '\s+', ' ', 'g') || ' ';
  -- drop trailing city / state / zip
  t := regexp_replace(t, '( DECATUR)?( GA)?( 3003[0-9]( [0-9]{4})?)? $', ' ');
  for i in 1 .. array_length(pairs, 1) by 2 loop
    t := replace(t, ' ' || pairs[i] || ' ', ' ' || pairs[i+1] || ' ');
    t := replace(t, ' ' || pairs[i] || ' ', ' ' || pairs[i+1] || ' ');   -- second pass for adjacent repeats
  end loop;
  t := regexp_replace(t, ' UNIT UNIT ', ' UNIT ', 'g');
  return trim(regexp_replace(t, '\s+', ' ', 'g'));
end $$;

-- one row per residential parcel that can be looked up
create table app.lookup_index (
  parcel_id text primary key,
  address   text not null,     -- display form
  norm      text not null,
  tokens    text[] not null,
  house_no  text
);
create index on app.lookup_index (house_no);
alter table app.lookup_index enable row level security;

create or replace function app.refresh_lookup_index() returns integer
language plpgsql as $$
declare n integer;
begin
  truncate app.lookup_index;
  insert into app.lookup_index (parcel_id, address, norm, tokens, house_no)
  select c.parcel_id,
         regexp_replace(c.site_address, '\s+Decatur,?\s+GA\s+\d{5}.*$', '', 'i'),
         app.norm_addr(c.site_address),
         string_to_array(app.norm_addr(c.site_address), ' '),
         split_part(app.norm_addr(c.site_address), ' ', 1)
  from raw.city_parcels c
  where c.site_address is not null
    and (c.class_code like 'R%'
         or exists (select 1 from raw.county_parcels g where g.parcel_id = c.parcel_id and g.property_class like 'R%'));
  get diagnostics n = row_count;
  return n;
end $$;
select app.refresh_lookup_index();

-- ---------------------------------------------------------------- public lookup
create or replace function public.site_lookup(q text, ip_hash text)
returns jsonb
language plpgsql security definer
set search_path = pg_catalog, public
as $$
declare
  nq text := app.norm_addr(q);
  toks text[];
  hn text;
  recent integer;
  total integer;
  matches text[];
  result jsonb;
begin
  -- rate limits: 40 per visitor per hour, 4,000 per day overall
  delete from app.lookup_log where at < now() - interval '2 days';
  select count(*) into recent from app.lookup_log l where l.ip_hash = site_lookup.ip_hash and l.at > now() - interval '1 hour';
  if recent >= 40 then
    return jsonb_build_object('status', 'rate_limited');
  end if;
  select count(*) into total from app.lookup_log where at > now() - interval '1 day';
  if total >= 4000 then
    return jsonb_build_object('status', 'busy');
  end if;
  insert into app.lookup_log (ip_hash) values (site_lookup.ip_hash);

  toks := array_remove(string_to_array(nq, ' '), '');
  hn := toks[1];
  if hn is null or hn !~ '^[0-9]+[A-Z]?$' or array_length(toks, 1) < 2 or length(array_to_string(toks[2:], '')) < 3 then
    return jsonb_build_object('status', 'need_number_and_street');
  end if;

  select array_agg(parcel_id order by norm) into matches
  from app.lookup_index i
  where i.house_no = hn and i.tokens @> toks;

  if matches is null then
    return jsonb_build_object('status', 'not_found');
  end if;
  if array_length(matches, 1) > 6 then
    return jsonb_build_object('status', 'add_unit', 'count', array_length(matches, 1));
  end if;

  select jsonb_agg(p order by p->>'address') into result
  from (
    select jsonb_build_object(
      'address', i.address,
      'city', coalesce((
        select jsonb_agg(distinct jsonb_build_object('code', l.exemption_code, 'name', coalesce(r.name, l.exemption_code)))
        from raw.city_bills b join raw.city_bill_lines l using (id_hash)
        left join analysis.ref_exemption_rules r on r.jurisdiction = 'city' and r.code = l.exemption_code
        where b.parcel_id = i.parcel_id and b.tax_year = 2026 and l.exemption_code is not null), '[]'::jsonb),
      'county', coalesce((
        select jsonb_agg(jsonb_build_object('code', e.code,
                 'name', coalesce(r.name, e.description, e.code),
                 'year_applied', e.year_applied) order by e.code)
        from raw.county_exemptions e
        left join analysis.ref_exemption_rules r on r.jurisdiction = 'county' and r.code = regexp_replace(e.code, 'F$', '')
        where e.parcel_id = i.parcel_id and e.tax_year = 2026), '[]'::jsonb),
      'has_city_bill', exists (select 1 from raw.city_bills b where b.parcel_id = i.parcel_id and b.tax_year = 2026),
      'county_checked', exists (select 1 from raw.county_fetch_log f where f.parcel_id = i.parcel_id and f.mode = 'dek_exemptions' and f.status in ('ok','nodata')),
      'gaps', coalesce((
        select jsonb_agg(jsonb_build_object(
                 'code', g.gap_code, 'status', g.status, 'missing', g.missing_exemption,
                 'label', g.gap_label,
                 'city_savings', round(g.est_annual_homeowner_savings_city_tax),
                 'county_savings', round(g.est_annual_homeowner_savings_county_tax),
                 'income_dependent', g.income_dependent = 1)
               order by g.tier, g.gap_code)
        from analysis.r_gap_candidates g
        where g.parcel_id = i.parcel_id and g.tier in ('A','B','D')), '[]'::jsonb)
    ) as p
    from app.lookup_index i where i.parcel_id = any(matches)
  ) s;

  return jsonb_build_object('status', 'ok', 'results', result, 'data_as_of', '2026-09');
end $$;

-- ---------------------------------------------------------------- outreach list (allowlisted users)
create or replace function public.site_outreach(p_email text, p_action text default 'view')
returns jsonb
language plpgsql security definer
set search_path = pg_catalog, public
as $$
declare
  ok boolean;
  rows jsonb;
begin
  select exists (select 1 from app.outreach_users u where lower(u.email) = lower(p_email) and u.active) into ok;
  insert into app.access_log (email, action, detail)
  values (p_email, case when ok then p_action else 'denied' end, null);
  if not ok then
    return jsonb_build_object('status', 'not_allowed');
  end if;
  if p_action = 'check' then
    return jsonb_build_object('status', 'ok');
  end if;

  with g as (
    select parcel_id,
           array_agg(distinct gap_label) filter (where status = 'proven') as proven,
           array_agg(distinct gap_label) filter (where status = 'likely') as likely,
           array_agg(distinct gap_label) filter (where status = 'possible' and tier = 'D') as possible,
           sum(coalesce(est_annual_homeowner_savings_city_tax,0)) filter (where status in ('proven','likely')) as city_savings,
           sum(coalesce(est_annual_homeowner_savings_county_tax,0)) filter (where status = 'proven') as county_savings
    from analysis.r_gap_candidates where tier in ('A','B','D')
    group by parcel_id
  ), lt as (
    select parcel_id, tenure_start_year from census.census_priority_long_tenure where has_any_senior_code = 0
  ), u as (
    select parcel_id from g union select parcel_id from lt
  )
  select jsonb_agg(jsonb_build_object(
           'parcel_id', u.parcel_id,
           'address', coalesce(i.address, p.site_address),
           'owner', coalesce(cp.owner, p.owner_name),
           'co_owner', coalesce(cp.co_owner, p.owner2),
           'mail', coalesce(cp.owner_address, nullif(trim(concat_ws(' ', c.mail_address, c.mail_city, c.mail_state, c.mail_zip5)), '')),
           'proven', coalesce(to_jsonb(g.proven), '[]'),
           'likely', coalesce(to_jsonb(g.likely), '[]'),
           'possible', coalesce(to_jsonb(g.possible), '[]'),
           'long_tenure', lt.parcel_id is not null,
           'owner_since', coalesce(lt.tenure_start_year, p.tenure_start_year),
           'city_savings', round(coalesce(g.city_savings, 0)),
           'county_savings', round(coalesce(g.county_savings, 0)),
           'value_decile', p.value_decile,
           'owner_type', p.owner_type
         ) order by coalesce(i.address, p.site_address)) into rows
  from u
  left join g using (parcel_id)
  left join lt using (parcel_id)
  left join analysis.r_parcel_clean p using (parcel_id)
  left join raw.county_profile cp using (parcel_id)
  left join raw.city_parcels c using (parcel_id)
  left join app.lookup_index i using (parcel_id);

  return jsonb_build_object('status', 'ok', 'data_as_of', '2026-09', 'rows', rows);
end $$;

revoke all on function public.site_lookup(text, text) from public, anon, authenticated;
revoke all on function public.site_outreach(text, text) from public, anon, authenticated;
grant execute on function public.site_lookup(text, text) to service_role;
grant execute on function public.site_outreach(text, text) to service_role;

revoke all on all tables in schema app from anon, authenticated;
revoke all on all functions in schema app from public, anon, authenticated;
