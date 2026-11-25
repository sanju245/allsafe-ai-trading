# Supabase account setup

The API owns user administration. The web session route uses the public anon key. The service-role credential stays on the API.

## Apply the migrations

Apply versioned migrations under `supabase/migrations` with the Supabase CLI.
When adopting a database with manually applied changes, verify its schema and
repair the migration history before pushing a new migration. The account-controls migration adds an
`active`/`paused` state and a legacy exact-IP field to each profile. Current sign-in
authorization uses token, role, and account status; it does not restrict customers by IP.
Browser roles remain read-only on `public.profiles`.

### Single-administrator guard (`20261102000000_single_admin_guard.sql`)

This migration makes the database refuse a second `role = 'admin'` profile (a
partial unique index, `profiles_single_admin_idx`). It never modifies accounts.

1. In the SQL Editor, run `supabase/preflight/check_single_admin.sql` (read-only).
   `admin_count` must be 0 or 1.
2. If it is greater than 1, decide which account stays admin and demote the others
   by hand, for example
   `update public.profiles set role = 'user' where lower(email) = lower('old-admin@example.com');`
   Paused admins count as admins until demoted.
3. Run the migration. If duplicates remain it stops with an error before creating
   the index and changes nothing, so it is safe to fix the data and run it again.
4. After it succeeds, change the administrator in one transaction: demote the current
   admin, then promote the new one before committing. Promoting a second admin while
   one exists fails with a unique-violation error naming `profiles_single_admin_idx`.
   Keep account-specific transfer and rollback records in the private operational
   handover. Verify both Auth identities, active status, expected roles, and the
   single-admin constraint before running a guarded transaction.

Rollback: `drop index if exists public.profiles_single_admin_idx;`

Local test (scratch Postgres only, never a Supabase project):
`PGHOST=<socket dir or localhost> PGUSER=<superuser> bash supabase/tests/test_single_admin_guard.sh`

## Disable public sign-up

In the Supabase Dashboard, open **Authentication → Settings → User Signups**
and turn off **Allow new users to sign up** before exposing the login page.
The web app has no self-registration form, but this project setting also blocks
direct sign-up requests to Supabase Auth. Customer accounts are created only by
the API's administrator-only endpoint.

## Configure the API service

Add these server-side values to the Render API service's environment:

- `SUPABASE_URL`: the Supabase project URL.
- `SUPABASE_JWT_SECRET`: needed only for legacy HS256 access tokens. ES256 and
  RS256 tokens are verified against Supabase's public JWKS endpoint.
- `SUPABASE_SERVICE_ROLE_KEY`: the legacy service-role key used only by the
  server-side Auth Admin and profile REST calls.
- `APP_ENV=production`: makes the API require Render's `CF-Connecting-IP`
  header. If running on Render, its service identifier also enables that
  fail-closed behavior.
- `CORS_ORIGINS=https://allsafe-ai-trading.vercel.app,http://localhost:3000`:
  allowed browser origins. Keep localhost only if it is needed for development.

Never put `SUPABASE_SERVICE_ROLE_KEY` in a `NEXT_PUBLIC_*` variable, a web
environment file, a response, or a browser request.

## Bootstrap the first administrator

1. In the Supabase Dashboard, open **Authentication → Users** and add the
   intended administrator with a confirmed email and a temporary password.
   Public self-signup is disabled. The auth trigger creates the matching
   `public.profiles` row with role `user`.
2. In Supabase SQL Editor, promote only that account:

   ```sql
   update public.profiles
   set role = 'admin',
       status = 'active'
   where lower(email) = lower('admin@example.com');
   ```

   Replace the example email with the intended administrator's verified Auth email.
   Confirm exactly one row was updated and only one administrator exists.
3. Sign in at `https://allsafe-ai-trading.vercel.app/admin/login`, then
   confirm `GET /api/v1/auth/me` returns the `admin` role. Admin actions are
   served by the API and checked against the current profile role and active status
   on every request. Authentication checks token, role, and active account status;
   legacy `allowed_ip` values are not used for authorization.

New account applications no longer ask customers for an IP. The API records the
source address from Render's `CF-Connecting-IP` header for abuse limiting and audit
metadata in the legacy `request_ip` column. Existing `profiles.allowed_ip` and
`account_requests.request_ip` values are retained but do not affect login or access.
The launch-readiness migration adds request processing timestamps, approved
application cleanup on customer deletion, and indexes for the paginated
admin queue. It leaves RLS and the application's service-role-only table access
in place.
