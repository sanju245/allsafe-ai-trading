-- Admin-managed account lifecycle controls.
-- The browser keeps SELECT-only profile access; all changes use the API's
-- server-only Supabase Auth Admin credential.

alter table public.profiles
  add column if not exists status text not null default 'active',
  add column if not exists allowed_ip inet;

alter table public.profiles
  drop constraint if exists profiles_status_allowed_values;
alter table public.profiles
  add constraint profiles_status_allowed_values
  check (status in ('active', 'paused'));

alter table public.profiles
  drop constraint if exists profiles_allowed_ip_exact_host;
alter table public.profiles
  add constraint profiles_allowed_ip_exact_host
  check (
    allowed_ip is null
    or (family(allowed_ip) = 4 and masklen(allowed_ip) = 32)
    or (family(allowed_ip) = 6 and masklen(allowed_ip) = 128)
  );

comment on column public.profiles.status is
  'Account access state. API routes reject paused accounts even while old JWTs remain unexpired.';
comment on column public.profiles.allowed_ip is
  'One exact IPv4/IPv6 host address; NULL only until first-admin bootstrap is completed.';

-- Keep profile data read-only to browser roles. Supabase service_role bypasses RLS
-- and is used only by the server-side API.
revoke all on table public.profiles from anon, authenticated;
grant select on table public.profiles to authenticated;

-- Paused admins lose the existing RLS-based profile-directory read as well.
-- API admin endpoints additionally enforce the caller's exact allowed IP.
create or replace function private.is_admin()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.profiles
    where id = (select auth.uid())
      and role = 'admin'
      and status = 'active'
  );
$$;

revoke all on function private.is_admin() from public, anon, authenticated;
grant execute on function private.is_admin() to authenticated;
