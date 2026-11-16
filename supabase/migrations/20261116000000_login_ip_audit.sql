-- Record verified successful logins for the admin-only account-sharing review.
-- Customer and administrator access is not restricted by IP. Existing
-- profiles.allowed_ip values remain untouched and are ignored by the API.

create table if not exists public.login_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  email text not null,
  client_ip inet,
  user_agent text,
  occurred_at timestamptz not null default now()
);

alter table public.login_events enable row level security;

-- Only the API's server-side service-role credential can write or read this
-- table. The API separately requires an active admin before returning events.
revoke all on table public.login_events from public, anon, authenticated;
grant select, insert on table public.login_events to service_role;

create index if not exists login_events_occurred_at_id_idx
  on public.login_events (occurred_at desc, id desc);

create index if not exists login_events_user_occurred_at_idx
  on public.login_events (user_id, occurred_at desc);

comment on table public.login_events is
  'Successful verified sign-ins, including source IP when the trusted edge header is available. Read through the admin-only API; records are not removed when a profile is deleted.';
comment on column public.profiles.allowed_ip is
  'Legacy value retained for compatibility; customer and admin access is not gated by this column.';
