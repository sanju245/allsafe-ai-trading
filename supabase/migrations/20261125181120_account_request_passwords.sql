alter table public.account_requests
  add column uses_chosen_password boolean not null default false;

create table private.account_request_passwords (
  request_id uuid primary key references public.account_requests(id) on delete cascade,
  password_hash text not null check (password_hash ~ '^[$]2b[$]12[$][./A-Za-z0-9]{53}$')
);

alter table private.account_request_passwords enable row level security;
revoke all on table private.account_request_passwords from public, anon, authenticated, service_role;
grant select, insert, delete on table private.account_request_passwords to service_role;

create function public.insert_account_request_with_password(p_application jsonb, p_password_hash text)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  saved public.account_requests;
begin
  insert into public.account_requests (
    full_name, date_of_birth, email, phone_number, whatsapp_number, request_ip, uses_chosen_password
  ) values (
    p_application ->> 'full_name',
    (p_application ->> 'date_of_birth')::date,
    p_application ->> 'email',
    p_application ->> 'phone_number',
    p_application ->> 'whatsapp_number',
    (p_application ->> 'request_ip')::inet,
    true
  )
  returning * into saved;

  insert into private.account_request_passwords (request_id, password_hash)
  values (saved.id, p_password_hash);
  return to_jsonb(saved);
end;
$$;

create function public.get_account_request_password_hash(p_request_id uuid, p_approval_attempt uuid)
returns text
language sql
stable
security invoker
set search_path = ''
as $$
  select credentials.password_hash
  from private.account_request_passwords credentials
  join public.account_requests application on application.id = credentials.request_id
  where application.id = p_request_id
    and application.status = 'processing'
    and application.approval_attempt = p_approval_attempt
    and application.processing_started_at is not null;
$$;

revoke all on function public.insert_account_request_with_password(jsonb, text) from public, anon, authenticated;
revoke all on function public.get_account_request_password_hash(uuid, uuid) from public, anon, authenticated;
grant execute on function public.insert_account_request_with_password(jsonb, text) to service_role;
grant execute on function public.get_account_request_password_hash(uuid, uuid) to service_role;

create function private.clear_account_request_password()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  delete from private.account_request_passwords where request_id = new.id;
  return new;
end;
$$;

revoke all on function private.clear_account_request_password() from public, anon, authenticated;
grant execute on function private.clear_account_request_password() to service_role;
create trigger clear_decided_account_request_password
  after update of status on public.account_requests
  for each row
  when (new.uses_chosen_password and old.status is distinct from new.status and new.status in ('approved', 'declined'))
  execute function private.clear_account_request_password();
