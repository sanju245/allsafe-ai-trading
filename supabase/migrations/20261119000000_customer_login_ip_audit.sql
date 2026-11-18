-- Successful customer sign-ins are recorded from the API's trusted edge IP.
-- Browser roles cannot read or write this security audit data.
create table if not exists public.customer_login_ip_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  client_ip inet not null,
  logged_at timestamptz not null default now()
);

create index if not exists customer_login_ip_events_user_time_idx
  on public.customer_login_ip_events (user_id, logged_at desc);
create index if not exists customer_login_ip_events_time_idx
  on public.customer_login_ip_events (logged_at desc);

alter table public.customer_login_ip_events enable row level security;
revoke all on table public.customer_login_ip_events from public, anon, authenticated;
grant select, insert on table public.customer_login_ip_events to service_role;

create or replace view public.customer_login_ip_daily_summary
with (security_invoker = true) as
select
  user_id,
  (logged_at at time zone 'UTC')::date as login_date,
  count(*)::integer as login_count,
  count(distinct client_ip)::integer as distinct_ip_count,
  array_agg(distinct host(client_ip) order by host(client_ip)) as ip_addresses
from public.customer_login_ip_events
group by user_id, (logged_at at time zone 'UTC')::date;

revoke all on table public.customer_login_ip_daily_summary from public, anon, authenticated;
grant select on table public.customer_login_ip_daily_summary to service_role;

comment on table public.customer_login_ip_events is
  'Sensitive security audit log of successful customer sign-ins. IP addresses are visible only to the trusted API service role and are not used to restrict login.';
comment on column public.customer_login_ip_events.client_ip is
  'IP address observed by the API edge; never accepted from browser input.';
