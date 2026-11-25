-- Keep the ten newest customer sign-ins after Supabase expires or revokes sessions.
create table public.customer_sign_ins (
  session_id uuid primary key,
  customer_id uuid not null references public.profiles (id) on delete cascade,
  signed_in_at timestamptz not null,
  ip_address inet
);

create index customer_sign_ins_recent_idx
  on public.customer_sign_ins (customer_id, signed_in_at desc, session_id desc);

alter table public.customer_sign_ins enable row level security;
revoke all on table public.customer_sign_ins from public, anon, authenticated, service_role;
grant select on table public.customer_sign_ins to service_role;

create function private.capture_customer_sign_in(p_user_id uuid, p_session_id uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  sign_in_time timestamptz;
  sign_in_ip inet;
begin
  -- Serialize the insert and retention policy per customer across concurrent sign-ins.
  perform pg_catalog.pg_advisory_xact_lock(1415665921, pg_catalog.hashtext(p_user_id::text));
  if exists (select 1 from public.customer_sign_ins where session_id = p_session_id) then
    return;
  end if;

  -- Refresh may replace a session's IP. Preserve the original value already
  -- recorded, or leave it unknown when first observed after a refresh.
  select created_at, case when refreshed_at is null then pg_catalog.host(ip)::inet end
    into sign_in_time, sign_in_ip
    from auth.sessions
    where id = p_session_id and user_id = p_user_id;
  if not found or sign_in_time is null then
    return;
  end if;

  insert into public.customer_sign_ins (session_id, customer_id, signed_in_at, ip_address)
  values (p_session_id, p_user_id, sign_in_time, sign_in_ip);

  delete from public.customer_sign_ins
  where session_id in (
    select session_id from public.customer_sign_ins
    where customer_id = p_user_id
    order by signed_in_at desc, session_id desc
    offset 10
  );

exception when others then
  -- Keep verification available if the audit write fails. Omit IPs and IDs from logs.
  raise log 'Customer sign-in history write failed (SQLSTATE %).', sqlstate;
end;
$$;

revoke all on function private.capture_customer_sign_in(uuid, uuid) from public, anon, authenticated, service_role;
grant usage on schema private to service_role;
grant execute on function private.capture_customer_sign_in(uuid, uuid) to service_role;

-- The API calls this only after verifying a password sign-in JWT. Combine
-- profile verification and capture so the portal uses one database request.
create function public.get_profile_for_sign_in(p_user_id uuid, p_session_id uuid)
returns table (id uuid, email text, role text, status text, created_at timestamptz)
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
    perform private.capture_customer_sign_in(p_user_id, p_session_id);
  end if;
  return query select profile.id, profile.email, profile.role, profile.status, profile.created_at;
end;
$$;

revoke all on function public.get_profile_for_sign_in(uuid, uuid) from public, anon, authenticated, service_role;
grant execute on function public.get_profile_for_sign_in(uuid, uuid) to service_role;
