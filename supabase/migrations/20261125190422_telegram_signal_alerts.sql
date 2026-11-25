-- Only the backend and the delivery worker can access Telegram chat IDs and jobs.
create table public.telegram_subscriptions (
  user_id uuid primary key references public.profiles(id) on delete cascade,
  chat_id bigint unique check (chat_id > 0),
  link_digest text unique,
  link_expires_at timestamptz,
  linked_at timestamptz
);

create table public.telegram_signal_events (
  symbol text not null check (symbol in ('NIFTY50', 'BANKNIFTY')),
  candle_at timestamptz not null,
  primary key (symbol, candle_at)
);

create table public.telegram_signal_deliveries (
  symbol text not null,
  candle_at timestamptz not null,
  user_id uuid not null references public.telegram_subscriptions(user_id) on delete cascade,
  chat_id bigint not null,
  provider text not null check (provider in ('groww', 'upstox')),
  expires_at timestamptz not null,
  available_at timestamptz not null default now(),
  claimed boolean not null default false,
  primary key (symbol, candle_at, user_id),
  foreign key (symbol, candle_at) references public.telegram_signal_events on delete cascade
);

create index telegram_signal_deliveries_pending
  on public.telegram_signal_deliveries(available_at) where not claimed;
create index telegram_signal_deliveries_user on public.telegram_signal_deliveries(user_id);
create index telegram_signal_events_candle on public.telegram_signal_events(candle_at);

alter table public.telegram_subscriptions enable row level security;
alter table public.telegram_signal_events enable row level security;
alter table public.telegram_signal_deliveries enable row level security;

revoke all on public.telegram_subscriptions, public.telegram_signal_events,
  public.telegram_signal_deliveries from public, anon, authenticated;
grant select, insert, update, delete on public.telegram_subscriptions,
  public.telegram_signal_events, public.telegram_signal_deliveries to service_role;

create function public.telegram_create_link(p_user uuid, p_digest text)
returns boolean language sql set search_path = '' as $$
  with pending as (
    insert into public.telegram_subscriptions(user_id, link_digest, link_expires_at)
    values (p_user, p_digest, now() + interval '10 minutes')
    on conflict (user_id) do update
      set link_digest = excluded.link_digest, link_expires_at = excluded.link_expires_at
      where telegram_subscriptions.chat_id is null
    returning 1
  ) select exists (select 1 from pending);
$$;

create function public.telegram_redeem_link(p_digest text, p_chat bigint)
returns boolean language plpgsql set search_path = '' as $$
begin
  update public.telegram_subscriptions as s set
    chat_id = p_chat, linked_at = now(), link_digest = null, link_expires_at = null
  where s.link_digest = p_digest and s.link_expires_at > now() and s.chat_id is null
    and exists (select 1 from public.profiles as p where p.id = s.user_id and p.status = 'active');
  return found;
exception when unique_violation then
  return false;
end;
$$;

create function public.telegram_enqueue_signal(
  p_symbol text, p_candle_at timestamptz, p_provider text, p_expires_at timestamptz
) returns void language sql set search_path = '' as $$
  delete from public.telegram_signal_events where candle_at < now() - interval '7 days';
  with new_event as (
    insert into public.telegram_signal_events(symbol, candle_at)
    select p_symbol, p_candle_at where p_expires_at > now()
    on conflict do nothing
    returning symbol, candle_at
  )
  insert into public.telegram_signal_deliveries(symbol, candle_at, user_id, chat_id, provider, expires_at)
  select e.symbol, e.candle_at, s.user_id, s.chat_id, p_provider, p_expires_at
  from new_event e cross join public.telegram_subscriptions s
  join public.profiles p on p.id = s.user_id and p.status = 'active'
  where s.chat_id is not null and s.linked_at <= e.candle_at + interval '15 minutes';
$$;

create function public.telegram_claim_delivery()
returns table(symbol text, candle_at timestamptz, user_id uuid, chat_id bigint,
              provider text, expires_at timestamptz)
language sql set search_path = '' as $$
  with next_delivery as (
    select d.symbol, d.candle_at, d.user_id
    from public.telegram_signal_deliveries d
    join public.telegram_subscriptions s on s.user_id = d.user_id and s.chat_id = d.chat_id
    join public.profiles p on p.id = d.user_id and p.status = 'active'
    where not d.claimed and d.available_at <= now() and d.expires_at > now()
    order by d.available_at, d.symbol, d.candle_at, d.user_id
    limit 1 for update of d skip locked
  )
  update public.telegram_signal_deliveries d set claimed = true
  from next_delivery n
  where (d.symbol, d.candle_at, d.user_id) = (n.symbol, n.candle_at, n.user_id)
  returning d.symbol, d.candle_at, d.user_id, d.chat_id, d.provider, d.expires_at;
$$;

revoke execute on function public.telegram_create_link(uuid, text),
  public.telegram_redeem_link(text, bigint),
  public.telegram_enqueue_signal(text, timestamptz, text, timestamptz),
  public.telegram_claim_delivery() from public, anon, authenticated;
grant execute on function public.telegram_create_link(uuid, text),
  public.telegram_redeem_link(text, bigint),
  public.telegram_enqueue_signal(text, timestamptz, text, timestamptz),
  public.telegram_claim_delivery() to service_role;
