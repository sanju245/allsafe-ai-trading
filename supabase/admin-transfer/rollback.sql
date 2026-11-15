-- Guarded rollback of transfer.sql. Run only when reversal is explicitly intended.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '15s';
lock table public.profiles in share row exclusive mode;

do $$
declare
  target_id constant uuid := '2997e4f7-1b53-4d75-b081-aaf3296e52f4';
  previous_id constant uuid := 'e557a06c-956f-4fff-85a1-a6c7b3d0dbf0';
begin
  if not exists (
    select 1 from public.profiles p join auth.users a on a.id = p.id
    where p.id = target_id and p.role = 'admin' and p.status = 'active' and p.allowed_ip is null
      and lower(p.email) = 'sanjay200123@gmail.com'
      and lower(a.email) = 'sanjay200123@gmail.com'
  ) or not exists (
    select 1 from public.profiles p join auth.users a on a.id = p.id
    where p.id = previous_id and p.role = 'user' and p.status = 'active'
      and lower(p.email) = 'sanjay@gmail.com'
      and lower(a.email) = 'sanjay@gmail.com'
  ) or (select count(*) from public.profiles where role = 'admin') <> 1 then
    raise exception 'Administrator rollback aborted: current identities, roles, or status changed.';
  end if;

  update public.profiles
  set role = 'user', allowed_ip = '152.58.183.233'::inet
  where id = target_id and role = 'admin';
  update public.profiles set role = 'admin' where id = previous_id and role = 'user';

  if (select count(*) from public.profiles where role = 'admin') <> 1
     or not exists (select 1 from public.profiles where id = previous_id and role = 'admin') then
    raise exception 'Administrator rollback verification failed; transaction rolled back.';
  end if;
end
$$;
commit;
