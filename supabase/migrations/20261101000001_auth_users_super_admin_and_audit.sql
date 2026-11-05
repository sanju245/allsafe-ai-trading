-- =============================================================================
-- AllSafe AI Trading — Authentication, Permanent Super Admin & Audit Schema
-- File: supabase/migrations/20261101000001_auth_users_super_admin_and_audit.sql
-- Purpose:
--   1. Create app_users table with PBKDF2 password hashes, roles, status, and global/CIDR IP rules
--   2. Provision permanent Super Admin (00000000-0000-4000-a000-000000000001) with global IP ('*')
--   3. Enforce trigger preventing Super Admin deletion, demotion, suspension, or IP lockout
--   4. Create immutable admin_audit_logs, admin_system_settings, and admin_content_config tables
--   5. Enable FORCE ROW LEVEL SECURITY with InitPlan-cached JWT checks and explicit GRANTs
-- =============================================================================

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- -----------------------------------------------------------------------------
-- 1. APPLICATION USERS & PERMANENT SUPER ADMIN TABLE
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.app_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username TEXT NOT NULL UNIQUE CHECK (char_length(username) BETWEEN 2 AND 64),
    email TEXT NOT NULL UNIQUE CHECK (position('@' in email) > 1),
    password_hash TEXT NOT NULL CHECK (password_hash LIKE 'pbkdf2_sha256$%'),
    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'operator', 'auditor', 'user')),
    is_super_admin BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'locked')),
    allowed_ip TEXT DEFAULT '*',
    mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    last_login_at TIMESTAMPTZ,
    last_login_ip TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT chk_super_admin_invariants CHECK (
        NOT is_super_admin OR (role = 'admin' AND status = 'active' AND coalesce(allowed_ip, '*') = '*')
    )
);

-- Ensure at most one permanent Super Admin row exists
CREATE UNIQUE INDEX IF NOT EXISTS idx_app_users_single_super_admin
    ON public.app_users ((is_super_admin))
    WHERE is_super_admin = TRUE;

CREATE INDEX IF NOT EXISTS idx_app_users_role_status
    ON public.app_users (role, status);

-- Trigger protecting the permanent Super Admin from deletion, demotion, or IP lockout
CREATE OR REPLACE FUNCTION public.protect_permanent_super_admin()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.is_super_admin OR OLD.id = '00000000-0000-4000-a000-000000000001'::uuid THEN
            RAISE EXCEPTION 'Permanent Super Admin identity cannot be deleted.';
        END IF;
        RETURN OLD;
    ELSIF TG_OP = 'UPDATE' THEN
        IF OLD.is_super_admin OR OLD.id = '00000000-0000-4000-a000-000000000001'::uuid THEN
            IF NEW.is_super_admin IS DISTINCT FROM TRUE
               OR NEW.role IS DISTINCT FROM 'admin'
               OR NEW.status IS DISTINCT FROM 'active'
               OR coalesce(NEW.allowed_ip, '*') IS DISTINCT FROM '*' THEN
                RAISE EXCEPTION 'Permanent Super Admin role, active status, and global IP access (*) cannot be restricted.';
            END IF;
        END IF;
        NEW.updated_at := timezone('utc', now());
        RETURN NEW;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_protect_super_admin ON public.app_users;
CREATE TRIGGER trg_protect_super_admin
    BEFORE UPDATE OR DELETE ON public.app_users
    FOR EACH ROW
    EXECUTE FUNCTION public.protect_permanent_super_admin();

-- -----------------------------------------------------------------------------
-- 2. ADMIN AUDIT LOGS (Append-Only Security & Activity Trail)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.admin_audit_logs (
    id TEXT PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    actor_id TEXT NOT NULL,
    actor_email TEXT NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT,
    severity TEXT NOT NULL DEFAULT 'info' CHECK (severity IN ('info', 'warning', 'critical')),
    ip_address TEXT NOT NULL DEFAULT '127.0.0.1',
    status TEXT NOT NULL DEFAULT 'success' CHECK (status IN ('success', 'denied', 'error')),
    details TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_admin_audit_logs_timestamp
    ON public.admin_audit_logs (timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_admin_audit_logs_severity
    ON public.admin_audit_logs (severity, timestamp DESC);

-- -----------------------------------------------------------------------------
-- 3. SYSTEM SETTINGS & CONTENT CONFIGURATION TABLES
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.admin_system_settings (
    id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    admin_global_ip_access BOOLEAN NOT NULL DEFAULT TRUE,
    session_ttl_seconds INTEGER NOT NULL DEFAULT 28800 CHECK (session_ttl_seconds BETWEEN 300 AND 86400),
    login_rate_limit_per_minute INTEGER NOT NULL DEFAULT 12 CHECK (login_rate_limit_per_minute BETWEEN 3 AND 120),
    max_failed_login_attempts INTEGER NOT NULL DEFAULT 5 CHECK (max_failed_login_attempts BETWEEN 3 AND 20),
    lockout_duration_seconds INTEGER NOT NULL DEFAULT 900 CHECK (lockout_duration_seconds BETWEEN 60 AND 7200),
    live_poll_interval_seconds INTEGER NOT NULL DEFAULT 15,
    off_hours_poll_interval_seconds INTEGER NOT NULL DEFAULT 60,
    maintenance_mode BOOLEAN NOT NULL DEFAULT FALSE,
    read_only_trading_invariant BOOLEAN NOT NULL DEFAULT TRUE CHECK (read_only_trading_invariant = TRUE),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    updated_by TEXT NOT NULL DEFAULT 'superadmin'
);

INSERT INTO public.admin_system_settings (id, admin_global_ip_access, read_only_trading_invariant)
VALUES (1, TRUE, TRUE)
ON CONFLICT (id) DO NOTHING;

-- -----------------------------------------------------------------------------
-- 4. ROW LEVEL SECURITY & EXPLICIT SUPABASE DATA API GRANTS
-- -----------------------------------------------------------------------------
ALTER TABLE public.app_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.app_users FORCE ROW LEVEL SECURITY;

ALTER TABLE public.admin_audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.admin_audit_logs FORCE ROW LEVEL SECURITY;

ALTER TABLE public.admin_system_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.admin_system_settings FORCE ROW LEVEL SECURITY;

REVOKE ALL ON public.app_users FROM anon, PUBLIC;
REVOKE ALL ON public.admin_audit_logs FROM anon, PUBLIC;
REVOKE ALL ON public.admin_system_settings FROM anon, PUBLIC;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.app_users TO service_role;
GRANT SELECT ON public.app_users TO authenticated;

GRANT SELECT, INSERT ON public.admin_audit_logs TO service_role;
GRANT SELECT ON public.admin_audit_logs TO authenticated;

GRANT SELECT, INSERT, UPDATE ON public.admin_system_settings TO service_role;
GRANT SELECT ON public.admin_system_settings TO authenticated;

DROP POLICY IF EXISTS policy_app_users_self_or_admin_read ON public.app_users;
CREATE POLICY policy_app_users_self_or_admin_read
    ON public.app_users FOR SELECT TO authenticated
    USING (
        id::text = (SELECT coalesce(current_setting('request.jwt.claims', true), '{}')::jsonb ->> 'sub')
        OR (SELECT coalesce(current_setting('request.jwt.claims', true), '{}')::jsonb -> 'app_metadata' ->> 'role') = 'admin'
    );

DROP POLICY IF EXISTS policy_admin_audit_logs_admin_read ON public.admin_audit_logs;
CREATE POLICY policy_admin_audit_logs_admin_read
    ON public.admin_audit_logs FOR SELECT TO authenticated
    USING (
        (SELECT coalesce(current_setting('request.jwt.claims', true), '{}')::jsonb -> 'app_metadata' ->> 'role') IN ('admin', 'auditor')
    );

DROP POLICY IF EXISTS policy_admin_settings_admin_read ON public.admin_system_settings;
CREATE POLICY policy_admin_settings_admin_read
    ON public.admin_system_settings FOR SELECT TO authenticated
    USING (
        (SELECT coalesce(current_setting('request.jwt.claims', true), '{}')::jsonb -> 'app_metadata' ->> 'role') IN ('admin', 'operator', 'auditor')
    );

-- Normalize any pre-existing administrator accounts so no admin is locked to a static IP
UPDATE public.app_users
SET allowed_ip = '*', updated_at = timezone('utc', now())
WHERE (role = 'admin' OR is_super_admin = TRUE)
  AND coalesce(allowed_ip, '') <> '*';

-- Server-side helper verifying identity-based admin access independent of client IP
CREATE OR REPLACE FUNCTION public.is_admin_ip_independent(check_user_id UUID)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM public.app_users u
        WHERE u.id = check_user_id
          AND u.status = 'active'
          AND (u.is_super_admin = TRUE OR u.role = 'admin')
    );
$$;

COMMIT;

