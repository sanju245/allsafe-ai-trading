-- Read-only preflight and post-transfer verification. No credentials or password data.
select p.id, p.email, p.role, p.status, p.allowed_ip,
       lower(p.email) = lower(a.email) as profile_matches_auth_email
from public.profiles p
join auth.users a on a.id = p.id
where p.id in (
  '2997e4f7-1b53-4d75-b081-aaf3296e52f4'::uuid,
  'e557a06c-956f-4fff-85a1-a6c7b3d0dbf0'::uuid
)
order by p.id;

select count(*) filter (where role = 'admin') as admin_count,
       to_regclass('public.profiles_single_admin_idx') is not null as single_admin_index_exists
from public.profiles;
