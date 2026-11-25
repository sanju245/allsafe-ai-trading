alter table public.profiles add column pause_reason text;
alter table public.profiles add constraint profiles_pause_reason_valid check (
  pause_reason is null or (
    status = 'paused' and char_length(pause_reason) between 1 and 1000 and btrim(pause_reason) <> ''
  )
);

-- The existing sign-in procedure verifies the profile and records its login IP.
-- Include the pause reason in the same server-only account lookup.
drop function public.get_profile_for_sign_in(uuid, uuid, inet);
create function public.get_profile_for_sign_in(p_user_id uuid, p_session_id uuid, p_client_ip inet)
returns table (id uuid, email text, role text, status text, created_at timestamptz, pause_reason text)
language plpgsql
security invoker
set search_path = ''
as $$
declare
  profile public.profiles%rowtype;
begin
  select p.* into profile from public.profiles p where p.id = p_user_id;
  if not found then
    return;
  end if;
  if profile.role = 'user' and profile.status = 'active' and pg_catalog.btrim(profile.email) <> '' then
    perform private.capture_customer_sign_in(p_user_id, p_session_id, p_client_ip);
  end if;
  return query select profile.id, profile.email, profile.role, profile.status, profile.created_at, profile.pause_reason;
end;
$$;
revoke all on function public.get_profile_for_sign_in(uuid, uuid, inet) from public, anon, authenticated, service_role;
grant execute on function public.get_profile_for_sign_in(uuid, uuid, inet) to service_role;

create table public.customer_warnings (
  id uuid primary key,
  target_id uuid references public.profiles (id) on delete cascade,
  message text not null check (char_length(message) between 1 and 1000 and btrim(message) <> ''),
  sent_at timestamptz not null default now()
);
create index customer_warnings_target_idx on public.customer_warnings (target_id) where target_id is not null;

create table public.customer_warning_recipients (
  customer_id uuid not null references public.profiles (id) on delete cascade,
  warning_id uuid not null references public.customer_warnings (id) on delete cascade,
  primary key (customer_id, warning_id)
);
create index customer_warning_recipients_warning_idx on public.customer_warning_recipients (warning_id);

alter table public.customer_warnings enable row level security;
alter table public.customer_warning_recipients enable row level security;
revoke all on table public.customer_warnings, public.customer_warning_recipients from public, anon, authenticated, service_role;
grant select, insert on table public.customer_warnings, public.customer_warning_recipients to service_role;

-- Store the notice and its audience atomically. Retrying the same send uses the
-- original audience, including when additional customers have since joined.
create function public.send_customer_warning(p_id uuid, p_target_id uuid, p_message text)
returns integer
language plpgsql
security invoker
set search_path = ''
as $$
declare
  existing public.customer_warnings%rowtype;
  delivered integer;
begin
  insert into public.customer_warnings (id, target_id, message)
  select p_id, p_target_id, p_message
  where exists (select 1 from public.profiles p where p.role = 'user' and (p_target_id is null or p.id = p_target_id))
  on conflict (id) do nothing;

  if found then
    insert into public.customer_warning_recipients (customer_id, warning_id)
    select p.id, p_id from public.profiles p
    where p.role = 'user' and (p_target_id is null or p.id = p_target_id);
    get diagnostics delivered = row_count;
    return delivered;
  end if;

  select * into existing from public.customer_warnings w where w.id = p_id;
  if not found then
    return 0;
  end if;
  if existing.target_id is distinct from p_target_id or existing.message is distinct from p_message then
    return -1;
  end if;
  return (select count(*)::integer from public.customer_warning_recipients r where r.warning_id = p_id);
end;
$$;

create function public.get_customer_warnings(p_customer_id uuid, p_before uuid)
returns table (id uuid, message text, sent_at timestamptz)
language sql
stable
security invoker
set search_path = ''
as $$
  select w.id, w.message, w.sent_at
  from public.customer_warning_recipients r
  join public.customer_warnings w on w.id = r.warning_id
  where r.customer_id = p_customer_id
    and (p_before is null or (w.sent_at, w.id) < (
      select previous.sent_at, previous.id
      from public.customer_warning_recipients target
      join public.customer_warnings previous on previous.id = target.warning_id
      where target.customer_id = p_customer_id and target.warning_id = p_before
    ))
  order by w.sent_at desc, w.id desc
  limit 21;
$$;

revoke all on function public.send_customer_warning(uuid, uuid, text), public.get_customer_warnings(uuid, uuid)
  from public, anon, authenticated, service_role;
grant execute on function public.send_customer_warning(uuid, uuid, text), public.get_customer_warnings(uuid, uuid)
  to service_role;
