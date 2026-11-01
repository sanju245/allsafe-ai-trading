#!/usr/bin/env bash
# Tests supabase/migrations/20261102000000_single_admin_guard.sql on a LOCAL scratch Postgres.
#
#   PGHOST=/path/to/socket-or-localhost PGPORT=5432 PGUSER=<superuser> \
#     bash supabase/tests/test_single_admin_guard.sh
#
# NEVER point this at a Supabase project. It creates throw-away databases named
# allsafe_sag_*, stubs the Supabase `auth` schema inside them, and drops them afterwards.
# It refuses to run unless PGHOST is a unix socket path, localhost or 127.0.0.1.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIG="$HERE/../migrations"
CHECK="$HERE/../preflight/check_single_admin.sql"
HOST="${PGHOST:-}"
case "$HOST" in
  /*|localhost|127.0.0.1|::1) ;;
  *) echo "refusing to run: PGHOST must be a local unix socket directory or localhost (got '${HOST:-unset}')"; exit 2 ;;
esac

PASS=0; FAIL=0
ok()   { echo "ok - $1"; PASS=$((PASS+1)); }
fail() { echo "FAIL - $1"; FAIL=$((FAIL+1)); }
check_nonzero() { if [ "$2" -ne 0 ]; then ok "$1"; else fail "$1 (expected a non-zero exit status, got 0)"; fi; }
check() { if [ "$2" = "$3" ]; then ok "$1"; else fail "$1 (expected '$3', got '$2')"; fi; }

q() { psql -X -q -v ON_ERROR_STOP=1 -At -d "$1" -c "$2" 2>&1; }          # query, stop on error
qf() { psql -X -q -v ON_ERROR_STOP=1 -At -d "$1" -f "$2" 2>&1; }          # file, stop on error

new_db() {  # $1 = name, $2 = "with_profiles" | "bare"
  psql -X -q -d postgres -c "drop database if exists $1" >/dev/null 2>&1
  psql -X -q -d postgres -c "create database $1" >/dev/null || { echo "cannot create $1"; exit 2; }
  local guard
  guard=$(q "$1" "select to_regnamespace('auth') is not null")
  [ "$guard" = "f" ] || { echo "refusing: database $1 already has an auth schema"; exit 2; }
  q "$1" "
    do \$\$ begin
      if not exists (select 1 from pg_roles where rolname='anon') then create role anon nologin; end if;
      if not exists (select 1 from pg_roles where rolname='authenticated') then create role authenticated nologin; end if;
      if not exists (select 1 from pg_roles where rolname='service_role') then create role service_role nologin bypassrls; end if;
    end \$\$;
    create schema auth;
    create table auth.users (id uuid primary key default gen_random_uuid(), email text);
    create function auth.uid() returns uuid language sql stable
      as 'select nullif(current_setting(''request.jwt.claim.sub'', true), '''')::uuid';
    grant usage on schema auth to authenticated;" >/dev/null || { echo "stub setup failed"; exit 2; }
  if [ "$2" = "with_profiles" ]; then
    qf "$1" "$MIG/20261020000000_profiles_and_admin.sql" >/dev/null || { echo "migration 1 failed"; exit 2; }
    qf "$1" "$MIG/20261101000000_account_status_and_ip_allowlist.sql" >/dev/null || { echo "migration 2 failed"; exit 2; }
  fi
}
add_user() { q "$1" "insert into auth.users (email) values ('$2')" >/dev/null; }   # trigger creates the profile
snapshot() { q "$1" "select md5(string_agg(p::text, '|' order by id)) from public.profiles p"; }
idx_exists() { q "$1" "select to_regclass('public.profiles_single_admin_idx') is not null"; }

# ---------- S1: zero admins ----------
D=allsafe_sag_s1; new_db $D with_profiles
add_user $D a@example.com; add_user $D b@example.com
S1=$(snapshot $D)
OUT=$(qf $D "$MIG/20261102000000_single_admin_guard.sql"); RC=$?
check "S1 zero admins: migration succeeds" "$RC" "0"
check "S1 zero admins: index created" "$(idx_exists $D)" "t"
check "S1 zero admins: no row changed" "$(snapshot $D)" "$S1"
OUT=$(qf $D "$MIG/20261102000000_single_admin_guard.sql"); RC=$?
check "S1 rerun is idempotent" "$RC" "0"
check "S1 index is partial on role = admin" \
  "$(q $D "select indexdef like '%UNIQUE%' and indexdef like '%WHERE (role = ''admin''::text)%' from pg_indexes where indexname='profiles_single_admin_idx'")" "t"

# ---------- S2: exactly one admin ----------
D=allsafe_sag_s2; new_db $D with_profiles
add_user $D admin@example.com; add_user $D u1@example.com; add_user $D u2@example.com
q $D "update public.profiles set role='admin', status='active', allowed_ip='203.0.113.9' where email='admin@example.com'" >/dev/null
S2=$(snapshot $D)
OUT=$(qf $D "$MIG/20261102000000_single_admin_guard.sql"); RC=$?
check "S2 one admin: migration succeeds" "$RC" "0"
check "S2 one admin: no row changed (admin, status and IP intact)" "$(snapshot $D)" "$S2"
OUT=$(q $D "update public.profiles set role='admin' where email='u1@example.com'"); RC=$?
check "S2 promoting a second admin is rejected" "$RC" "1"
case "$OUT" in *profiles_single_admin_idx*) ok "S2 rejection names the guard index" ;; *) fail "S2 rejection names the guard index ($OUT)" ;; esac
check "S2 second admin was not created" "$(q $D "select count(*) from public.profiles where role='admin'")" "1"
add_user $D u3@example.com
check "S2 new users can still be created (trigger unaffected)" "$(q $D "select count(*) from public.profiles where email='u3@example.com' and role='user'")" "1"
q $D "update public.profiles set status='paused' where email='admin@example.com'" >/dev/null
check "S2 pausing the admin is still allowed" "$(q $D "select status from public.profiles where email='admin@example.com'")" "paused"
q $D "update public.profiles set role='user' where email='admin@example.com'" >/dev/null
q $D "update public.profiles set role='admin', status='active' where email='u1@example.com'" >/dev/null
check "S2 changing admin = demote first, then promote" "$(q $D "select email from public.profiles where role='admin'")" "u1@example.com"

# ---------- S3: duplicate admins (one paused) ----------
D=allsafe_sag_s3; new_db $D with_profiles
add_user $D a1@example.com; add_user $D a2@example.com; add_user $D u@example.com
q $D "update public.profiles set role='admin', status='active', allowed_ip='203.0.113.1' where email='a1@example.com'" >/dev/null
q $D "update public.profiles set role='admin', status='paused', allowed_ip='203.0.113.2' where email='a2@example.com'" >/dev/null
S3=$(snapshot $D)
OUT=$(qf $D "$MIG/20261102000000_single_admin_guard.sql"); RC=$?
check_nonzero "S3 duplicates: migration stops with an error" "$RC"
case "$OUT" in *"single-admin guard NOT applied: 2 profiles"*"No rows were changed"*) ok "S3 error explains the duplicate count and that nothing changed" ;; *) fail "S3 error message ($OUT)" ;; esac
check "S3 duplicates: index NOT created" "$(idx_exists $D)" "f"
check "S3 duplicates: no row changed (both admins, status and IPs intact)" "$(snapshot $D)" "$S3"
# Worst case: a client that does not stop on error. The index statement must fail too.
psql -X -q -d $D -f "$MIG/20261102000000_single_admin_guard.sql" >/dev/null 2>&1
check "S3 even without ON_ERROR_STOP the index cannot be created" "$(idx_exists $D)" "f"
check "S3 even without ON_ERROR_STOP no row changed" "$(snapshot $D)" "$S3"
OUT=$(qf $D "$CHECK")
case "$OUT" in *"2"*"a1@example.com"*"a2@example.com"*) ok "S3 read-only preflight lists both admins" ;; *) fail "S3 preflight output ($OUT)" ;; esac
check "S3 preflight changed nothing" "$(snapshot $D)" "$S3"
# After the operator demotes one admin by hand, the migration succeeds.
q $D "update public.profiles set role='user' where email='a2@example.com'" >/dev/null
OUT=$(qf $D "$MIG/20261102000000_single_admin_guard.sql"); RC=$?
check "S3 after manual demotion the migration succeeds" "$RC" "0"
check "S3 after manual demotion index exists" "$(idx_exists $D)" "t"

# ---------- S4: schema assumption missing ----------
D=allsafe_sag_s4; new_db $D bare
OUT=$(qf $D "$MIG/20261102000000_single_admin_guard.sql"); RC=$?
check_nonzero "S4 missing public.profiles: migration stops" "$RC"
case "$OUT" in *"table public.profiles does not exist"*) ok "S4 clear message for missing table" ;; *) fail "S4 message ($OUT)" ;; esac

# ---------- S5: missing role column ----------
D=allsafe_sag_s5; new_db $D bare
q $D "create table public.profiles (id uuid primary key, email text)" >/dev/null
OUT=$(qf $D "$MIG/20261102000000_single_admin_guard.sql"); RC=$?
check_nonzero "S5 missing role column: migration stops" "$RC"
case "$OUT" in *'no "role" column'*) ok "S5 clear message for missing column" ;; *) fail "S5 message ($OUT)" ;; esac

for n in s1 s2 s3 s4 s5; do psql -X -q -d postgres -c "drop database if exists allsafe_sag_$n" >/dev/null 2>&1; done
echo "passed=$PASS failed=$FAIL"
[ "$FAIL" -eq 0 ]
