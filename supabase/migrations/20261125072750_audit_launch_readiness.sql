-- Store durable approval and mail claims. Existing requests can be resumed as-is.
alter table public.account_requests
  add column if not exists approval_attempt uuid,
  add column if not exists processing_started_at timestamptz,
  add column if not exists notification_started_at timestamptz,
  add column if not exists receipt_started_at timestamptz;

create index if not exists account_requests_auth_user_idx on public.account_requests(auth_user_id);
create index if not exists account_requests_decided_by_idx on public.account_requests(decided_by);
create index if not exists account_requests_review_idx on public.account_requests(created_at desc, id desc)
  where status in ('pending', 'processing') or notification_status in ('pending', 'failed');

-- The existing, confirmed customer deletion also deletes the linked application.
-- This foreign-key replacement does not modify any current account or request.
alter table public.account_requests
  drop constraint if exists account_requests_auth_user_id_fkey,
  add constraint account_requests_auth_user_id_fkey
    foreign key (auth_user_id) references auth.users(id) on delete cascade;
