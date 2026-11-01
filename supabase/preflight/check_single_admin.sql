-- READ-ONLY pre-check for migration 20261102000000_single_admin_guard.sql.
-- Safe to run in the Supabase SQL Editor: it contains only SELECT statements.
-- It lists administrators by id, email, status and creation time (no secrets are involved).
--
-- Expected result before migrating: admin_count is 0 or 1.
-- If admin_count is greater than 1, decide which account stays admin and demote the others
-- by hand BEFORE applying the migration (see supabase/README.md). The migration will refuse
-- to run while more than one admin exists, and it will not change any account itself.

select count(*) as admin_count
from public.profiles
where role = 'admin';

select id, email, role, status, allowed_ip, created_at
from public.profiles
where role = 'admin'
order by created_at;

-- Is the guard already installed?
select to_regclass('public.profiles_single_admin_idx') is not null as guard_index_exists;
