-- Enforce "at most one administrator" at the database level.
--
-- SAFETY CONTRACT
--   * This migration NEVER updates, deletes or inserts rows. It only reads public.profiles
--     and, if everything checks out, creates one index.
--   * If the existing data does not satisfy the rule (more than one profile with
--     role = 'admin'), the migration raises an error and stops BEFORE creating the index.
--     Nothing is changed; fix the data by hand (see supabase/README.md) and run it again.
--   * It is idempotent: running it again after success is a no-op.
--   * It does not touch auth.users, existing columns, policies, triggers or functions.
--
-- Run it in the Supabase SQL Editor as one script, or with the Supabase CLI. Both run the
-- statements in order and stop at the first error, so a failed check prevents the index.
-- Run supabase/preflight/check_single_admin.sql first to see the answer without risk.

do $$
declare
  admin_count bigint;
begin
  -- 1. Schema assumptions this migration relies on (created by the two earlier migrations).
  if to_regclass('public.profiles') is null then
    raise exception 'single-admin guard NOT applied: table public.profiles does not exist. '
      'Apply 20261020000000_profiles_and_admin.sql first. No rows were changed.';
  end if;

  if not exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'profiles' and column_name = 'role'
  ) then
    raise exception 'single-admin guard NOT applied: public.profiles has no "role" column. '
      'No rows were changed.';
  end if;

  -- 2. Detect duplicate administrators. Paused admins count too: pausing is not demotion.
  select count(*) into admin_count from public.profiles where role = 'admin';

  if admin_count > 1 then
    raise exception 'single-admin guard NOT applied: % profiles have role = ''admin'' (at most 1 is allowed). '
      'No rows were changed. Decide which account stays admin, demote the others by hand, '
      'then run this migration again. See supabase/README.md.', admin_count
      using errcode = 'P0001';
  end if;
end
$$;

-- 3. Partial unique index: every admin row maps to the same key (the constant 'admin'),
--    so a second admin row is rejected with a unique violation. Rows with any other role
--    are not in the index and are unaffected.
create unique index if not exists profiles_single_admin_idx
  on public.profiles ((role))
  where role = 'admin';

comment on index public.profiles_single_admin_idx is
  'At most one profile may have role = admin. To change the administrator, demote the current one first, then promote the new one (see supabase/README.md).';

-- Rollback (manual, if ever needed):
--   drop index if exists public.profiles_single_admin_idx;
