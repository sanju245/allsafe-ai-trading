-- Public applications are stored without creating auth.users. Only the API's
-- service role can read or change applicant personal details.
create table if not exists public.account_requests (
  id uuid primary key default gen_random_uuid(),
  full_name text not null check (char_length(full_name) between 2 and 120),
  date_of_birth date not null,
  email text not null,
  phone_number text not null,
  whatsapp_number text not null,
  request_ip inet not null,
  status text not null default 'pending'
    check (status in ('pending', 'processing', 'approved', 'declined')),
  notification_status text not null default 'pending'
    check (notification_status in ('pending', 'sent', 'failed')),
  auth_user_id uuid references auth.users (id) on delete set null,
  decided_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  receipt_sent_at timestamptz,
  decided_at timestamptz,
  notification_sent_at timestamptz
);

create unique index if not exists account_requests_one_open_email
  on public.account_requests (lower(email))
  where status in ('pending', 'processing');
create index if not exists account_requests_recent
  on public.account_requests (created_at desc);

alter table public.account_requests enable row level security;
revoke all on table public.account_requests from public, anon, authenticated;
grant select, insert, update, delete on table public.account_requests to service_role;

comment on table public.account_requests is
  'Private customer applications. An auth account exists only after an admin approves.';
