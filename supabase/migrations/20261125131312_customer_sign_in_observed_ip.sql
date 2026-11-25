-- The browser signs in through Vercel. Its account verification request goes
-- straight to Render, where the API can read the real client IP from the edge.
drop function public.get_profile_for_sign_in(uuid, uuid);
drop function private.capture_customer_sign_in(uuid, uuid);

create function private.capture_customer_sign_in(p_user_id uuid, p_session_id uuid, p_client_ip inet)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  sign_in_time timestamptz;
begin
  perform pg_catalog.pg_advisory_xact_lock(1415665921, pg_catalog.hashtext(p_user_id::text));
  if exists (select 1 from public.customer_sign_ins where session_id = p_session_id) then
    return;
  end if;

  -- A refresh can happen on a different network. Only the initial account
  -- verification can pair this browser address with the session's creation time.
  select created_at into sign_in_time
  from auth.sessions
  where id = p_session_id and user_id = p_user_id
    and refreshed_at is null and created_at >= pg_catalog.now() - interval '5 minutes';
  if not found then
    return;
  end if;

  insert into public.customer_sign_ins (session_id, customer_id, signed_in_at, ip_address)
  values (p_session_id, p_user_id, sign_in_time, pg_catalog.host(p_client_ip)::inet);

  delete from public.customer_sign_ins
  where session_id in (
    select session_id from public.customer_sign_ins
    where customer_id = p_user_id
    order by signed_in_at desc, session_id desc
    offset 10
  );
exception when others then
  raise log 'Customer sign-in history write failed (SQLSTATE %).', sqlstate;
end;
$$;

revoke all on function private.capture_customer_sign_in(uuid, uuid, inet) from public, anon, authenticated, service_role;
grant execute on function private.capture_customer_sign_in(uuid, uuid, inet) to service_role;

create function public.get_profile_for_sign_in(p_user_id uuid, p_session_id uuid, p_client_ip inet)
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
    perform private.capture_customer_sign_in(p_user_id, p_session_id, p_client_ip);
  end if;
  return query select profile.id, profile.email, profile.role, profile.status, profile.created_at;
end;
$$;

revoke all on function public.get_profile_for_sign_in(uuid, uuid, inet) from public, anon, authenticated, service_role;
grant execute on function public.get_profile_for_sign_in(uuid, uuid, inet) to service_role;
