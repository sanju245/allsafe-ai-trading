-- Operational script for the owner-requested administrator transfer, 2026-11-15.
-- Run preflight.sql first. This script does not change Auth identities or passwords.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '15s';
lock table public.profiles in share row exclusive mode;

do $$
declare
  target_id constant uuid := '2997e4f7-1b53-4d75-b081-aaf3296e52f4';
  previous_id constant uuid := 'e557a06c-956f-4fff-85a1-a6c7b3d0dbf0';
  admin_count bigint;
begin
  if not exists (
    select 1 from public.profiles p join auth.users a on a.id = p.id
    where p.id = target_id
      and lower(p.email) = 'sanjay200123@gmail.com'
      and lower(a.email) = 'sanjay200123@gmail.com'
      and p.status = 'active'
  ) or not exists (
    select 1 from public.profiles p join auth.users a on a.id = p.id
    where p.id = previous_id
      and lower(p.email) = 'sanjay@gmail.com'
      and lower(a.email) = 'sanjay@gmail.com'
      and p.status = 'active'
  ) then
    raise exception 'Administrator transfer aborted: profile/Auth identity or status changed.';
  end if;

  select count(*) into admin_count from public.profiles where role = 'admin';
  if admin_count <> 1 then
    raise exception 'Administrator transfer aborted: expected exactly one current admin.';
  end if;

  if exists (select 1 from public.profiles where id = target_id and role = 'admin' and allowed_ip is null)
     and exists (select 1 from public.profiles where id = previous_id and role = 'user') then
    raise notice 'Requested administrator transfer already complete; no changes.';
    return;
  end if;

  if not exists (
    select 1 from public.profiles
    where id = target_id and role = 'user' and allowed_ip = '152.58.183.233'::inet
  )
     or not exists (select 1 from public.profiles where id = previous_id and role = 'admin') then
    raise exception 'Administrator transfer aborted: unexpected current roles.';
  end if;

  update public.profiles set role = 'user' where id = previous_id and role = 'admin';
  update public.profiles set role = 'admin', allowed_ip = null where id = target_id and role = 'user';

  if (select count(*) from public.profiles where role = 'admin') <> 1
     or not exists (select 1 from public.profiles where id = target_id and role = 'admin' and allowed_ip is null) then
    raise exception 'Administrator transfer verification failed; transaction rolled back.';
  end if;
end
$$;
commit;
