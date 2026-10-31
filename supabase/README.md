# Supabase account setup

The API owns user administration. The browser may sign in with the public anon
key, but it must never receive the service-role credential.

## Apply the migrations

Apply all SQL files under `supabase/migrations` in timestamp order using the
Supabase SQL Editor or the Supabase CLI. The account-controls migration adds an
`active`/`paused` state and one exact IP address to each profile. Browser roles
remain read-only on `public.profiles`.

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
2. From the intended administrator's permitted network, open
   `https://allsafe-ai-api.onrender.com/api/v1/auth/client-ip` and copy the
   returned `client_ip` value.
3. In Supabase SQL Editor, promote only that account and bind its exact IP:

   ```sql
   update public.profiles
   set role = 'admin',
       status = 'active',
       allowed_ip = '203.0.113.42'::inet
   where lower(email) = lower('admin@example.com');
   ```

   Replace the example address and email with the values from steps 1 and 2.
   Confirm exactly one row was updated. Do not use a CIDR range; the migration
   rejects anything other than one IPv4 or IPv6 host address.
4. Sign in at `https://allsafe-ai-trading.vercel.app/login` from that IP, then
   confirm `GET /api/v1/auth/me` returns the `admin` role. Admin actions are
   served by the API and checked against the current profile status and IP on
   every request.

The public `GET /api/v1/auth/client-ip` endpoint reports the API's trusted
client address and does not require a login. In production, the API accepts this
address only from Render's `CF-Connecting-IP` header; if it is absent or invalid,
the API fails closed.
