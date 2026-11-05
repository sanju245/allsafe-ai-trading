"""Thread-safe Authentication, RBAC, Session, Audit Log, and System Settings Store."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import secrets
import threading
import time
import uuid

from fastapi import HTTPException, Request

from app import __version__
from app.auth.models import (
    AdminAuditLogSchema,
    AdminContentConfigSchema,
    AdminErrorEntrySchema,
    AdminHealthResponse,
    AdminRoleDefinitionSchema,
    AdminStatsResponse,
    AdminSystemSettingsSchema,
    AppUserSchema,
    CreateUserRequest,
    LoginResponse,
    SessionInfoSchema,
    UpdateContentConfigRequest,
    UpdateRolePermissionsRequest,
    UpdateSystemSettingsRequest,
    UpdateUserRequest,
)
from app.auth.security import (
    PERMANENT_SUPER_ADMIN_ID,
    create_session_token,
    extract_client_ip,
    hash_password,
    is_client_ip_allowed,
    validate_and_normalize_allowed_ip,
    validate_password_strength,
    verify_password,
    JWKSCache,
    verify_jwt_with_jwks_or_secret,
    verify_session_token,
    verify_totp_code,
)
from app.config import Settings, get_settings
from app.providers.groww_auth import redact_groww_secrets as redact_text

ROLE_DEFAULT_PERMISSIONS: dict[str, list[str]] = {
    "super_admin": [
        "*",
        "users:read",
        "users:write",
        "users:delete",
        "roles:manage",
        "content:manage",
        "settings:manage",
        "audit:read",
        "system:health",
        "security:ip_override",
    ],
    "admin": [
        "users:read",
        "users:write",
        "users:delete",
        "roles:manage",
        "content:manage",
        "settings:manage",
        "audit:read",
        "system:health",
    ],
    "operator": [
        "users:read",
        "content:manage",
        "audit:read",
        "system:health",
    ],
    "auditor": [
        "users:read",
        "audit:read",
        "system:health",
    ],
    "user": [
        "market:read",
        "intelligence:read",
        "account:self",
    ],
}


@dataclass
class StoredUser:
    id: str
    username: str
    email: str
    password_hash: str
    role: str = "user"
    is_super_admin: bool = False
    status: str = "active"
    allowed_ip: str | None = None
    totp_secret: str = ""
    last_login_at: str | None = None
    last_login_ip: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class StoredSession:
    jti: str
    user_id: str
    username: str
    email: str
    role: str
    ip_address: str
    user_agent: str
    csrf_token: str
    created_at: str
    expires_at_epoch: int
    revoked: bool = False


class AuthStore:
    """Centralized, thread-safe authentication and administration state coordinator."""

    def __init__(self, settings: Settings | None = None, *, fast_hash: bool = False) -> None:
        self._lock = threading.RLock()
        self.settings = settings or get_settings()
        self._started_at_monotonic = time.monotonic()
        self._pbkdf2_iterations = 20_000 if fast_hash else 600_000

        self._users: dict[str, StoredUser] = {}
        self._sessions: dict[str, StoredSession] = {}
        self._ip_login_buckets: dict[str, deque[float]] = {}
        self._failed_attempts: dict[str, list[float]] = {}
        self._lockout_until: dict[str, float] = {}

        self.jwks_cache = JWKSCache(
            cache_ttl_seconds=float(getattr(self.settings, 'jwks_cache_ttl_seconds', 3600)),
            refresh_cooldown_seconds=float(getattr(self.settings, 'jwks_refresh_cooldown_seconds', 30)),
        )
        self._audit_logs: deque[AdminAuditLogSchema] = deque(maxlen=1000)
        self._error_logs: deque[AdminErrorEntrySchema] = deque(maxlen=500)

        now_iso = datetime.now(timezone.utc).isoformat()
        self._role_definitions: dict[str, AdminRoleDefinitionSchema] = {
            "super_admin": AdminRoleDefinitionSchema(
                role="super_admin",
                label="Super Administrator",
                description="Permanent root identity with full system control, global IP access, and deletion protection.",
                is_system_role=True,
                permissions=list(ROLE_DEFAULT_PERMISSIONS["super_admin"]),
            ),
            "admin": AdminRoleDefinitionSchema(
                role="admin",
                label="Administrator",
                description="Full access to user directory, access rules, content settings, audit logs, and system health.",
                is_system_role=True,
                permissions=list(ROLE_DEFAULT_PERMISSIONS["admin"]),
            ),
            "operator": AdminRoleDefinitionSchema(
                role="operator",
                label="Market Operations",
                description="Can manage market content banners, risk defaults, and inspect system telemetry.",
                is_system_role=False,
                permissions=list(ROLE_DEFAULT_PERMISSIONS["operator"]),
            ),
            "auditor": AdminRoleDefinitionSchema(
                role="auditor",
                label="Security Auditor",
                description="Read-only access to account directory, security audit trails, and system health diagnostics.",
                is_system_role=False,
                permissions=list(ROLE_DEFAULT_PERMISSIONS["auditor"]),
            ),
            "user": AdminRoleDefinitionSchema(
                role="user",
                label="Standard Trader",
                description="Read-only access to live NIFTY 50 & BANK NIFTY charts, 5-indicator signals, and AI market intelligence.",
                is_system_role=True,
                permissions=list(ROLE_DEFAULT_PERMISSIONS["user"]),
            ),
        }

        self._content_config = AdminContentConfigSchema(
            announcement_banner="NSE Index Terminal operating in strictly Read-Only Analytical Mode. Confirmed 5m candles are separated from forming candles.",
            announcement_enabled=True,
            featured_instruments=["NIFTY50", "BANKNIFTY"],
            default_timeframe="5m",
            default_capital_inr=200000,
            default_risk_pct=1.0,
            max_risk_pct_cap=2.0,
            min_risk_reward_ratio=1.5,
            educational_disclaimer="Educational market analysis only; not investment advice. No broker orders are placed by this platform.",
            read_only_safety_lock=True,
            updated_at=now_iso,
            updated_by=self.settings.super_admin_username or "superadmin",
        )

        self._system_settings = AdminSystemSettingsSchema(
            admin_global_ip_access=bool(self.settings.admin_global_ip_access),
            session_ttl_seconds=int(self.settings.auth_session_ttl_seconds),
            login_rate_limit_per_minute=int(self.settings.auth_login_rate_limit_per_minute),
            max_failed_login_attempts=int(self.settings.auth_max_failed_attempts),
            lockout_duration_seconds=int(self.settings.auth_lockout_seconds),
            live_poll_interval_seconds=15,
            off_hours_poll_interval_seconds=60,
            require_strong_passwords=True,
            csrf_protection_enabled=True,
            maintenance_mode=False,
            read_only_trading_invariant=True,
            updated_at=now_iso,
            updated_by=self.settings.super_admin_username or "superadmin",
        )

        self._provision_super_admin()

    def _provision_super_admin(self) -> None:
        """Ensure the permanent Super Admin account exists with global IP access ('*')."""
        sa_id = (self.settings.super_admin_id or PERMANENT_SUPER_ADMIN_ID).strip() or PERMANENT_SUPER_ADMIN_ID
        sa_username = (self.settings.super_admin_username or "superadmin").strip().lower()
        sa_email = (self.settings.super_admin_email or "admin@allsafe.ai").strip().lower()
        sa_totp = (self.settings.super_admin_totp_secret or "").strip()

        configured_hash = (self.settings.super_admin_password_hash or "").strip()
        initial_pw = (self.settings.super_admin_initial_password or "").strip()

        if configured_hash and configured_hash.startswith("pbkdf2_sha256$"):
            pw_hash = configured_hash
            provision_mode = "env_password_hash"
        elif initial_pw:
            pw_hash = hash_password(initial_pw, iterations=self._pbkdf2_iterations)
            provision_mode = "env_initial_password_hashed"
        else:
            # Generate a cryptographically random non-guessable password if unconfigured
            ephemeral_pw = f"AllSafe!{secrets.token_urlsafe(18)}#9"
            pw_hash = hash_password(ephemeral_pw, iterations=20_000)
            provision_mode = "ephemeral_random_hash"

        now_iso = datetime.now(timezone.utc).isoformat()
        super_admin = StoredUser(
            id=sa_id,
            username=sa_username,
            email=sa_email,
            password_hash=pw_hash,
            role="admin",
            is_super_admin=True,
            status="active",
            allowed_ip="*",
            totp_secret=sa_totp,
            created_at=now_iso,
            updated_at=now_iso,
        )
        self._users[sa_id] = super_admin
        self.record_audit_log(
            actor_id=sa_id,
            actor_email=sa_email,
            action="super_admin.provisioned",
            target_type="user",
            target_id=sa_id,
            severity="info",
            ip_address="system",
            status="success",
            details=f"Permanent Super Admin '{sa_username}' ({sa_id}) provisioned via {provision_mode} with global IP access (*).",
        )

    def set_super_admin_password(self, raw_password: str) -> None:
        """Update the Super Admin password hash securely (used by provisioning CLI and tests)."""
        validate_password_strength(raw_password)
        with self._lock:
            sa = self.get_super_admin_record()
            sa.password_hash = hash_password(raw_password, iterations=self._pbkdf2_iterations)
            sa.updated_at = datetime.now(timezone.utc).isoformat()

    def get_super_admin_record(self) -> StoredUser:
        with self._lock:
            for u in self._users.values():
                if u.is_super_admin:
                    return u
            self._provision_super_admin()
            return next(u for u in self._users.values() if u.is_super_admin)

    def _permissions_for_user(self, u: StoredUser) -> list[str]:
        if u.is_super_admin:
            return list(self._role_definitions["super_admin"].permissions)
        role_def = self._role_definitions.get(u.role)
        if role_def is not None:
            return list(role_def.permissions)
        return list(ROLE_DEFAULT_PERMISSIONS.get(u.role, ROLE_DEFAULT_PERMISSIONS["user"]))

    def _to_user_schema(self, u: StoredUser, *, now_epoch: float | None = None) -> AppUserSchema:
        now_ts = now_epoch if now_epoch is not None else time.time()
        lock_until = self._lockout_until.get(u.id, 0.0)
        effective_status = u.status
        if lock_until > now_ts and not u.is_super_admin:
            effective_status = "locked"
        elif lock_until <= now_ts and u.id in self._lockout_until:
            self._lockout_until.pop(u.id, None)
            self._failed_attempts.pop(u.id, None)

        return AppUserSchema(
            id=u.id,
            username=u.username,
            email=u.email,
            role="admin" if u.is_super_admin else u.role,  # type: ignore[arg-type]
            is_super_admin=u.is_super_admin,
            status=effective_status,  # type: ignore[arg-type]
            allowed_ip="*" if u.is_super_admin else u.allowed_ip,
            permissions=self._permissions_for_user(u),
            mfa_enabled=bool(u.totp_secret.strip()),
            last_login_at=u.last_login_at,
            last_login_ip=u.last_login_ip,
            created_at=u.created_at,
            updated_at=u.updated_at,
        )

    def record_audit_log(
        self,
        *,
        actor_id: str,
        actor_email: str,
        action: str,
        target_type: str,
        target_id: str | None = None,
        severity: str = "info",
        ip_address: str = "127.0.0.1",
        status: str = "success",
        details: str = "",
    ) -> AdminAuditLogSchema:
        with self._lock:
            entry = AdminAuditLogSchema(
                id=f"aud_{uuid.uuid4().hex[:12]}",
                timestamp=datetime.now(timezone.utc).isoformat(),
                actor_id=actor_id,
                actor_email=actor_email,
                action=action,
                target_type=target_type,
                target_id=target_id,
                severity=severity,  # type: ignore[arg-type]
                ip_address=ip_address,
                status=status,  # type: ignore[arg-type]
                details=redact_text(details),
            )
            self._audit_logs.appendleft(entry)
            return entry

    def record_error(
        self,
        *,
        component: str,
        message: str,
        severity: str = "error",
    ) -> AdminErrorEntrySchema:
        with self._lock:
            entry = AdminErrorEntrySchema(
                id=f"err_{uuid.uuid4().hex[:10]}",
                timestamp=datetime.now(timezone.utc).isoformat(),
                component=component,
                severity=severity,  # type: ignore[arg-type]
                message=redact_text(message),
                resolved=False,
            )
            self._error_logs.appendleft(entry)
            return entry

    def _check_ip_rate_limit(self, client_ip: str, *, now_epoch: float) -> None:
        window = 60.0
        limit = max(1, int(self._system_settings.login_rate_limit_per_minute))
        bucket = self._ip_login_buckets.setdefault(client_ip, deque())
        cutoff = now_epoch - window
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = max(1, int((bucket[0] + window) - now_epoch + 0.999))
            self.record_audit_log(
                actor_id="anonymous",
                actor_email="anonymous",
                action="auth.login.rate_limited",
                target_type="ip",
                target_id=client_ip,
                severity="warning",
                ip_address=client_ip,
                status="denied",
                details=f"Login rate limit exceeded from IP {client_ip} ({limit}/min).",
            )
            raise HTTPException(
                status_code=429,
                detail=f"Too many login attempts from this network. Please retry in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now_epoch)

    def _find_user_by_identifier(self, identifier: str) -> StoredUser | None:
        cleaned = identifier.strip().lower()
        if not cleaned:
            return None
        for u in self._users.values():
            if u.email.lower() == cleaned or u.username.lower() == cleaned:
                return u
        return None

    def authenticate(
        self,
        *,
        identifier: str,
        password: str,
        totp_code: str | None = None,
        client_ip: str = "127.0.0.1",
        user_agent: str = "unknown",
        now_epoch: float | None = None,
        portal: str | None = None,
    ) -> LoginResponse:
        now_ts = now_epoch if now_epoch is not None else time.time()
        with self._lock:
            self._check_ip_rate_limit(client_ip, now_epoch=now_ts)
            user = self._find_user_by_identifier(identifier)

            if user is None:
                # Constant-time dummy PBKDF2 work to prevent username enumeration timing attacks
                verify_password(
                    password,
                    "pbkdf2_sha256$20000$00112233445566778899aabbccddeeff$00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff",
                )
                self.record_audit_log(
                    actor_id="anonymous",
                    actor_email=identifier[:64] or "unknown",
                    action="auth.login.failed",
                    target_type="auth",
                    severity="warning",
                    ip_address=client_ip,
                    status="denied",
                    details="Invalid credentials for unknown account identifier.",
                )
                raise HTTPException(status_code=401, detail="Invalid email/username or password.")

            # Check brute-force lockout
            lock_until = self._lockout_until.get(user.id, 0.0)
            if lock_until > now_ts:
                retry_after = max(1, int(lock_until - now_ts))
                self.record_audit_log(
                    actor_id=user.id,
                    actor_email=user.email,
                    action="auth.login.locked_out",
                    target_type="user",
                    target_id=user.id,
                    severity="warning",
                    ip_address=client_ip,
                    status="denied",
                    details=f"Account temporarily locked due to repeated failed login attempts ({retry_after}s remaining).",
                )
                raise HTTPException(
                    status_code=429,
                    detail=f"Account temporarily locked after repeated failed attempts. Retry in {retry_after} seconds.",
                    headers={"Retry-After": str(retry_after)},
                )

            if not verify_password(password, user.password_hash):
                attempts = self._failed_attempts.setdefault(user.id, [])
                cutoff = now_ts - float(self._system_settings.lockout_duration_seconds)
                attempts[:] = [t for t in attempts if t > cutoff]
                attempts.append(now_ts)
                max_attempts = max(3, int(self._system_settings.max_failed_login_attempts))
                if len(attempts) >= max_attempts:
                    self._lockout_until[user.id] = now_ts + float(self._system_settings.lockout_duration_seconds)
                    self.record_audit_log(
                        actor_id=user.id,
                        actor_email=user.email,
                        action="auth.account.locked",
                        target_type="user",
                        target_id=user.id,
                        severity="critical",
                        ip_address=client_ip,
                        status="denied",
                        details=f"Brute-force protection triggered after {len(attempts)} failed login attempts.",
                    )
                else:
                    self.record_audit_log(
                        actor_id=user.id,
                        actor_email=user.email,
                        action="auth.login.failed",
                        target_type="user",
                        target_id=user.id,
                        severity="warning",
                        ip_address=client_ip,
                        status="denied",
                        details=f"Invalid password attempt ({len(attempts)}/{max_attempts}).",
                    )
                raise HTTPException(status_code=401, detail="Invalid email/username or password.")

            # Verify optional TOTP 2FA if configured on account
            if user.totp_secret.strip():
                if not verify_totp_code(user.totp_secret, totp_code):
                    self.record_audit_log(
                        actor_id=user.id,
                        actor_email=user.email,
                        action="auth.login.mfa_failed",
                        target_type="user",
                        target_id=user.id,
                        severity="warning",
                        ip_address=client_ip,
                        status="denied",
                        details="Invalid or missing 2FA TOTP verification code.",
                    )
                    raise HTTPException(status_code=401, detail="Valid two-factor authentication (TOTP) code required.")

            # Clear failed attempts and release rate-limit slot after successful credential verification
            self._failed_attempts.pop(user.id, None)
            self._lockout_until.pop(user.id, None)
            ip_bucket = self._ip_login_buckets.get(client_ip)
            if ip_bucket:
                ip_bucket.pop()

            # Check account status (Super Admin is always active)
            if not user.is_super_admin and user.status != "active":
                self.record_audit_log(
                    actor_id=user.id,
                    actor_email=user.email,
                    action="auth.login.paused_account",
                    target_type="user",
                    target_id=user.id,
                    severity="warning",
                    ip_address=client_ip,
                    status="denied",
                    details=f"Sign-in blocked because account status is '{user.status}'.",
                )
                raise HTTPException(status_code=403, detail="Account access is currently paused. Contact an administrator.")

            # Enforce Admin Portal vs Customer Portal role separation when portal='admin'
            if portal == "admin" and not (
                user.is_super_admin or user.role in {"admin", "operator", "auditor"}
            ):
                self.record_audit_log(
                    actor_id=user.id,
                    actor_email=user.email,
                    action="auth.admin_portal.denied",
                    target_type="user",
                    target_id=user.id,
                    severity="warning",
                    ip_address=client_ip,
                    status="denied",
                    details=f"Customer account (role={user.role}) attempted to sign in via the Admin Portal.",
                )
                raise HTTPException(
                    status_code=403,
                    detail="Customer accounts are not authorized to sign in to the Admin Portal. Please use the Customer Sign-In Portal (/login).",
                )
            if False and not user.is_super_admin and user.status != "active":
                self.record_audit_log(
                    actor_id=user.id,
                    actor_email=user.email,
                    action="auth.login.paused_account",
                    target_type="user",
                    target_id=user.id,
                    severity="warning",
                    ip_address=client_ip,
                    status="denied",
                    details=f"Sign-in blocked because account status is '{user.status}'.",
                )
                raise HTTPException(status_code=403, detail="Account access is currently paused. Contact an administrator.")

            # Check IP policy (Super Admin and global-enabled admins can sign in from ANY IP globally)
            if not is_client_ip_allowed(
                client_ip,
                user.allowed_ip,
                is_super_admin=user.is_super_admin,
                role=user.role,
                global_admin_ip_enabled=self._system_settings.admin_global_ip_access,
            ):
                self.record_audit_log(
                    actor_id=user.id,
                    actor_email=user.email,
                    action="auth.login.ip_restricted",
                    target_type="user",
                    target_id=user.id,
                    severity="warning",
                    ip_address=client_ip,
                    status="denied",
                    details=f"Client IP {client_ip} is not permitted by account allowed_ip '{user.allowed_ip}'.",
                )
                raise HTTPException(
                    status_code=403,
                    detail=f"Access from IP address {client_ip} is not authorized for this account.",
                )

            ttl = int(self._system_settings.session_ttl_seconds)
            token, jti, exp_epoch = create_session_token(
                user_id=user.id,
                username=user.username,
                email=user.email,
                role="admin" if user.is_super_admin else user.role,
                is_super_admin=user.is_super_admin,
                secret_key=self.settings.auth_secret_key,
                ttl_seconds=ttl,
                now_epoch=int(now_ts),
            )
            csrf_token = secrets.token_hex(24)
            now_iso = datetime.now(timezone.utc).isoformat()
            user.last_login_at = now_iso
            user.last_login_ip = client_ip
            user.updated_at = now_iso

            self._sessions[jti] = StoredSession(
                jti=jti,
                user_id=user.id,
                username=user.username,
                email=user.email,
                role="admin" if user.is_super_admin else user.role,
                ip_address=client_ip,
                user_agent=(user_agent or "unknown")[:200],
                csrf_token=csrf_token,
                created_at=now_iso,
                expires_at_epoch=exp_epoch,
                revoked=False,
            )

            self.record_audit_log(
                actor_id=user.id,
                actor_email=user.email,
                action="auth.login.success",
                target_type="session",
                target_id=jti,
                severity="info",
                ip_address=client_ip,
                status="success",
                details=f"Authenticated session created from IP {client_ip} (role={'super_admin' if user.is_super_admin else user.role}).",
            )

            return LoginResponse(
                access_token=token,
                token_type="bearer",
                expires_in=ttl,
                csrf_token=csrf_token,
                user=self._to_user_schema(user, now_epoch=now_ts),
            )

    def verify_request_session(
        self,
        token: str,
        *,
        client_ip: str = "127.0.0.1",
        now_epoch: float | None = None,
    ) -> tuple[AppUserSchema, StoredSession]:
        now_ts = now_epoch if now_epoch is not None else time.time()
        claims = verify_session_token(
            token,
            secret_key=self.settings.auth_secret_key,
            now_epoch=int(now_ts),
        )
        if claims is None:
            # Check if token is a verified Supabase/JWKS JWT; if so, resolve authoritative server-side user record
            jwt_claims = verify_jwt_with_jwks_or_secret(
                token,
                jwks_cache=self.jwks_cache,
                hmac_secret=self.settings.supabase_jwt_secret,
                now_epoch=int(now_ts),
            )
            if jwt_claims is not None:
                with self._lock:
                    sub_id = str(jwt_claims.get("sub", "")).strip()
                    email_claim = str(jwt_claims.get("email", "")).strip().lower()
                    user = self._users.get(sub_id) or (
                        self._find_user_by_identifier(email_claim) if email_claim else None
                    )
                    if user is None:
                        raise HTTPException(status_code=401, detail="Account no longer exists.")
                    if not user.is_super_admin and user.status != "active":
                        raise HTTPException(status_code=403, detail="Account access is paused.")
                    # CRITICAL: Always enforce IP policy using server-side user.role & user.is_super_admin, NEVER JWT claims
                    if not is_client_ip_allowed(
                        client_ip,
                        user.allowed_ip,
                        is_super_admin=user.is_super_admin,
                        role=user.role,
                        global_admin_ip_enabled=self._system_settings.admin_global_ip_access,
                    ):
                        raise HTTPException(
                            status_code=403,
                            detail=f"Session access from IP {client_ip} is not permitted for this account.",
                        )
                    synthetic_session = StoredSession(
                        jti=str(jwt_claims.get("jti") or f"jwt_{sub_id[:12]}"),
                        user_id=user.id,
                        username=user.username,
                        email=user.email,
                        role="admin" if user.is_super_admin else user.role,
                        ip_address=client_ip,
                        user_agent="jwt-bearer",
                        csrf_token="",
                        created_at=datetime.now(timezone.utc).isoformat(),
                        expires_at_epoch=int(jwt_claims.get("exp", int(now_ts) + 3600)),
                        revoked=False,
                    )
                    return self._to_user_schema(user, now_epoch=now_ts), synthetic_session
            raise HTTPException(status_code=401, detail="Invalid or expired session token.")

        jti = str(claims.get("jti", ""))
        user_id = str(claims.get("sub", ""))
        with self._lock:
            session = self._sessions.get(jti)
            if session is None or session.revoked or session.expires_at_epoch <= int(now_ts):
                raise HTTPException(status_code=401, detail="Session has been revoked or expired.")

            user = self._users.get(user_id)
            if user is None:
                raise HTTPException(status_code=401, detail="Account no longer exists.")

            if not user.is_super_admin and user.status != "active":
                raise HTTPException(status_code=403, detail="Account access is paused.")

            if not is_client_ip_allowed(
                client_ip,
                user.allowed_ip,
                is_super_admin=user.is_super_admin,
                role=user.role,
                global_admin_ip_enabled=self._system_settings.admin_global_ip_access,
            ):
                raise HTTPException(
                    status_code=403,
                    detail=f"Session access from IP {client_ip} is not permitted for this account.",
                )

            if client_ip and session.ip_address != client_ip:
                session.ip_address = client_ip
                user.last_login_ip = client_ip

            return self._to_user_schema(user, now_epoch=now_ts), session


    def refresh_session(
        self,
        token: str,
        *,
        client_ip: str = "127.0.0.1",
        user_agent: str = "unknown",
        now_epoch: float | None = None,
    ) -> LoginResponse:
        """Rotate an active session token after re-verifying user status and IP policy."""
        now_ts = now_epoch if now_epoch is not None else time.time()
        with self._lock:
            user_schema, old_session = self.verify_request_session(
                token, client_ip=client_ip, now_epoch=now_ts
            )
            old_session.revoked = True
            user = self._users[user_schema.id]
            ttl = int(self._system_settings.session_ttl_seconds)
            new_token, new_jti, exp_epoch = create_session_token(
                user_id=user.id,
                username=user.username,
                email=user.email,
                role="admin" if user.is_super_admin else user.role,
                is_super_admin=user.is_super_admin,
                secret_key=self.settings.auth_secret_key,
                ttl_seconds=ttl,
                now_epoch=int(now_ts),
            )
            new_csrf = secrets.token_hex(24)
            now_iso = datetime.now(timezone.utc).isoformat()
            self._sessions[new_jti] = StoredSession(
                jti=new_jti,
                user_id=user.id,
                username=user.username,
                email=user.email,
                role="admin" if user.is_super_admin else user.role,
                ip_address=client_ip,
                user_agent=(user_agent or old_session.user_agent or "unknown")[:200],
                csrf_token=new_csrf,
                created_at=now_iso,
                expires_at_epoch=exp_epoch,
                revoked=False,
            )
            self.record_audit_log(
                actor_id=user.id,
                actor_email=user.email,
                action="auth.session.refreshed",
                target_type="session",
                target_id=new_jti,
                severity="info",
                ip_address=client_ip,
                status="success",
                details=f"Rotated session {old_session.jti[:8]} -> {new_jti[:8]} from IP {client_ip}.",
            )
            return LoginResponse(
                access_token=new_token,
                token_type="bearer",
                expires_in=ttl,
                csrf_token=new_csrf,
                user=self._to_user_schema(user, now_epoch=now_ts),
            )

    def revoke_session(self, jti: str, *, actor_email: str = "self", ip_address: str = "127.0.0.1") -> bool:
        with self._lock:
            session = self._sessions.get(jti)
            if session is None:
                return False
            session.revoked = True
            self.record_audit_log(
                actor_id=session.user_id,
                actor_email=actor_email,
                action="auth.logout",
                target_type="session",
                target_id=jti,
                severity="info",
                ip_address=ip_address,
                status="success",
                details=f"Session {jti[:8]} revoked.",
            )
            return True

    def revoke_all_user_sessions(self, user_id: str, *, actor: AppUserSchema, ip_address: str = "127.0.0.1") -> int:
        with self._lock:
            count = 0
            for s in self._sessions.values():
                if s.user_id == user_id and not s.revoked:
                    s.revoked = True
                    count += 1
            self.record_audit_log(
                actor_id=actor.id,
                actor_email=actor.email,
                action="admin.user.revoke_sessions",
                target_type="user",
                target_id=user_id,
                severity="warning",
                ip_address=ip_address,
                status="success",
                details=f"Revoked {count} active session(s) for user {user_id}.",
            )
            return count

    def change_password(
        self,
        *,
        user_id: str,
        current_password: str,
        new_password: str,
        ip_address: str = "127.0.0.1",
    ) -> None:
        validate_password_strength(new_password)
        with self._lock:
            user = self._users.get(user_id)
            if user is None:
                raise HTTPException(status_code=404, detail="User not found.")
            if not verify_password(current_password, user.password_hash):
                self.record_audit_log(
                    actor_id=user.id,
                    actor_email=user.email,
                    action="auth.password_change.failed",
                    target_type="user",
                    target_id=user.id,
                    severity="warning",
                    ip_address=ip_address,
                    status="denied",
                    details="Password change rejected due to incorrect current password.",
                )
                raise HTTPException(status_code=400, detail="Current password is incorrect.")
            user.password_hash = hash_password(new_password, iterations=self._pbkdf2_iterations)
            user.updated_at = datetime.now(timezone.utc).isoformat()
            # Revoke any other sessions for this user upon password rotation
            for s in self._sessions.values():
                if s.user_id == user.id and not s.revoked:
                    s.revoked = True
            self.record_audit_log(
                actor_id=user.id,
                actor_email=user.email,
                action="auth.password_change.success",
                target_type="user",
                target_id=user.id,
                severity="info",
                ip_address=ip_address,
                status="success",
                details="Account password hash rotated successfully.",
            )

    def list_users(
        self,
        *,
        search: str | None = None,
        role: str | None = None,
        status: str | None = None,
    ) -> list[AppUserSchema]:
        with self._lock:
            now_ts = time.time()
            results = [self._to_user_schema(u, now_epoch=now_ts) for u in self._users.values()]
            if search and search.strip():
                q = search.strip().lower()
                results = [
                    u
                    for u in results
                    if q in u.email.lower()
                    or q in u.username.lower()
                    or q in u.id.lower()
                    or (u.allowed_ip and q in u.allowed_ip.lower())
                ]
            if role and role.strip() and role.strip().lower() != "all":
                r = role.strip().lower()
                results = [u for u in results if u.role.lower() == r or (r == "super_admin" and u.is_super_admin)]
            if status and status.strip() and status.strip().lower() != "all":
                s = status.strip().lower()
                results = [u for u in results if u.status.lower() == s]
            # Sort Super Admin first, then by created_at desc
            results.sort(key=lambda u: (0 if u.is_super_admin else 1, u.email))
            return results

    def create_user(
        self,
        req: CreateUserRequest,
        *,
        actor: AppUserSchema,
        ip_address: str = "127.0.0.1",
    ) -> AppUserSchema:
        with self._lock:
            email_lower = req.email.strip().lower()
            username_clean = (req.username or email_lower.split("@")[0]).strip().lower()
            for existing in self._users.values():
                if existing.email.lower() == email_lower:
                    raise HTTPException(status_code=409, detail=f"An account with email '{email_lower}' already exists.")
                if existing.username.lower() == username_clean:
                    username_clean = f"{username_clean}_{secrets.token_hex(2)}"

            try:
                normalized_ip = validate_and_normalize_allowed_ip(req.allowed_ip, is_super_admin=False)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

            raw_pw = (req.password or "").strip()
            if raw_pw:
                try:
                    validate_password_strength(raw_pw)
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc
            else:
                raw_pw = f"AllSafe!{secrets.token_urlsafe(12)}#7"

            now_iso = datetime.now(timezone.utc).isoformat()
            user_id = str(uuid.uuid4())
            stored = StoredUser(
                id=user_id,
                username=username_clean,
                email=email_lower,
                password_hash=hash_password(raw_pw, iterations=self._pbkdf2_iterations),
                role=req.role,
                is_super_admin=False,
                status=req.status,
                allowed_ip=normalized_ip,
                created_at=now_iso,
                updated_at=now_iso,
            )
            self._users[user_id] = stored
            self.record_audit_log(
                actor_id=actor.id,
                actor_email=actor.email,
                action="admin.user.created",
                target_type="user",
                target_id=user_id,
                severity="info",
                ip_address=ip_address,
                status="success",
                details=f"Created user '{email_lower}' (role={req.role}, status={req.status}, allowed_ip={normalized_ip or 'global'}). Set password hash via PBKDF2.",
            )
            return self._to_user_schema(stored)

    def update_user(
        self,
        user_id: str,
        req: UpdateUserRequest,
        *,
        actor: AppUserSchema,
        ip_address: str = "127.0.0.1",
    ) -> AppUserSchema:
        with self._lock:
            target = self._users.get(user_id)
            if target is None:
                raise HTTPException(status_code=404, detail=f"User '{user_id}' not found.")

            if target.is_super_admin:
                if req.role is not None and req.role != "admin":
                    raise HTTPException(
                        status_code=403,
                        detail="The permanent Super Admin role cannot be demoted.",
                    )
                if req.status is not None and req.status != "active":
                    raise HTTPException(
                        status_code=403,
                        detail="The permanent Super Admin account cannot be paused or suspended.",
                    )
                if req.allowed_ip is not None and req.allowed_ip.strip() not in {"", "*", "any", "global", "0.0.0.0/0"}:
                    raise HTTPException(
                        status_code=403,
                        detail="The permanent Super Admin must retain global IP access ('*') to prevent administrative lockout.",
                    )

            changes: list[str] = []
            if req.username is not None and req.username.strip():
                new_uname = req.username.strip().lower()
                for other in self._users.values():
                    if other.id != user_id and other.username.lower() == new_uname:
                        raise HTTPException(status_code=409, detail=f"Username '{new_uname}' is already in use.")
                target.username = new_uname
                changes.append(f"username={new_uname}")

            if req.role is not None and not target.is_super_admin:
                target.role = req.role
                changes.append(f"role={req.role}")

            if req.status is not None and not target.is_super_admin:
                target.status = req.status
                changes.append(f"status={req.status}")
                if req.status != "active":
                    for s in self._sessions.values():
                        if s.user_id == user_id:
                            s.revoked = True

            if "allowed_ip" in req.model_fields_set and not target.is_super_admin:
                try:
                    normalized_ip = validate_and_normalize_allowed_ip(req.allowed_ip, is_super_admin=False)
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc
                target.allowed_ip = normalized_ip
                changes.append(f"allowed_ip={normalized_ip or 'global'}")

            if req.password is not None and req.password.strip():
                if target.is_super_admin and not actor.is_super_admin:
                    raise HTTPException(
                        status_code=403,
                        detail="Only the Super Admin can rotate the Super Admin password.",
                    )
                try:
                    validate_password_strength(req.password.strip())
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc
                target.password_hash = hash_password(req.password.strip(), iterations=self._pbkdf2_iterations)
                changes.append("password_hash=rotated")

            target.updated_at = datetime.now(timezone.utc).isoformat()
            self.record_audit_log(
                actor_id=actor.id,
                actor_email=actor.email,
                action="admin.user.updated",
                target_type="user",
                target_id=user_id,
                severity="info",
                ip_address=ip_address,
                status="success",
                details=f"Updated user '{target.email}': {', '.join(changes) if changes else 'no-op'}.",
            )
            return self._to_user_schema(target)

    def delete_user(
        self,
        user_id: str,
        *,
        actor: AppUserSchema,
        ip_address: str = "127.0.0.1",
    ) -> None:
        with self._lock:
            target = self._users.get(user_id)
            if target is None:
                raise HTTPException(status_code=404, detail=f"User '{user_id}' not found.")
            if target.is_super_admin or target.id == PERMANENT_SUPER_ADMIN_ID:
                self.record_audit_log(
                    actor_id=actor.id,
                    actor_email=actor.email,
                    action="admin.user.delete_blocked",
                    target_type="user",
                    target_id=user_id,
                    severity="critical",
                    ip_address=ip_address,
                    status="denied",
                    details="Attempted deletion of permanent Super Admin was blocked.",
                )
                raise HTTPException(
                    status_code=403,
                    detail="The permanent Super Admin identity cannot be deleted.",
                )
            if target.id == actor.id:
                raise HTTPException(
                    status_code=400,
                    detail="You cannot delete your own currently active administrator account.",
                )

            deleted_email = target.email
            self._users.pop(user_id, None)
            self._failed_attempts.pop(user_id, None)
            self._lockout_until.pop(user_id, None)
            for s in self._sessions.values():
                if s.user_id == user_id:
                    s.revoked = True

            self.record_audit_log(
                actor_id=actor.id,
                actor_email=actor.email,
                action="admin.user.deleted",
                target_type="user",
                target_id=user_id,
                severity="warning",
                ip_address=ip_address,
                status="success",
                details=f"Deleted user '{deleted_email}' ({user_id}) and revoked associated sessions.",
            )

    def unlock_user(
        self,
        user_id: str,
        *,
        actor: AppUserSchema,
        ip_address: str = "127.0.0.1",
    ) -> AppUserSchema:
        with self._lock:
            target = self._users.get(user_id)
            if target is None:
                raise HTTPException(status_code=404, detail=f"User '{user_id}' not found.")
            self._failed_attempts.pop(user_id, None)
            self._lockout_until.pop(user_id, None)
            if target.status == "locked":
                target.status = "active"
            target.updated_at = datetime.now(timezone.utc).isoformat()
            self.record_audit_log(
                actor_id=actor.id,
                actor_email=actor.email,
                action="admin.user.unlocked",
                target_type="user",
                target_id=user_id,
                severity="info",
                ip_address=ip_address,
                status="success",
                details=f"Cleared brute-force lockout counters for '{target.email}'.",
            )
            return self._to_user_schema(target)

    def list_roles(self) -> list[AdminRoleDefinitionSchema]:
        with self._lock:
            users = list(self._users.values())
            result: list[AdminRoleDefinitionSchema] = []
            for role_key, role_def in self._role_definitions.items():
                if role_key == "super_admin":
                    cnt = sum(1 for u in users if u.is_super_admin)
                else:
                    cnt = sum(1 for u in users if not u.is_super_admin and u.role == role_key)
                result.append(
                    AdminRoleDefinitionSchema(
                        role=role_def.role,
                        label=role_def.label,
                        description=role_def.description,
                        is_system_role=role_def.is_system_role,
                        permissions=list(role_def.permissions),
                        user_count=cnt,
                    )
                )
            return result

    def update_role_permissions(
        self,
        role_name: str,
        req: UpdateRolePermissionsRequest,
        *,
        actor: AppUserSchema,
        ip_address: str = "127.0.0.1",
    ) -> AdminRoleDefinitionSchema:
        with self._lock:
            cleaned = role_name.strip().lower()
            if cleaned == "super_admin":
                raise HTTPException(
                    status_code=403,
                    detail="Super Administrator permissions are immutable.",
                )
            role_def = self._role_definitions.get(cleaned)
            if role_def is None:
                raise HTTPException(status_code=404, detail=f"Role '{cleaned}' not found.")
            role_def.permissions = [p.strip() for p in req.permissions if p.strip()]
            if req.description is not None:
                role_def.description = req.description.strip()
            self.record_audit_log(
                actor_id=actor.id,
                actor_email=actor.email,
                action="admin.role.updated",
                target_type="role",
                target_id=cleaned,
                severity="info",
                ip_address=ip_address,
                status="success",
                details=f"Updated permissions for role '{cleaned}': {', '.join(role_def.permissions)}.",
            )
            return role_def

    def get_content_config(self) -> AdminContentConfigSchema:
        with self._lock:
            return self._content_config.model_copy(deep=True)

    def update_content_config(
        self,
        req: UpdateContentConfigRequest,
        *,
        actor: AppUserSchema,
        ip_address: str = "127.0.0.1",
    ) -> AdminContentConfigSchema:
        with self._lock:
            if req.announcement_banner is not None:
                self._content_config.announcement_banner = req.announcement_banner.strip()
            if req.announcement_enabled is not None:
                self._content_config.announcement_enabled = bool(req.announcement_enabled)
            if req.featured_instruments is not None:
                allowed = [s.strip().upper() for s in req.featured_instruments if s.strip().upper() in {"NIFTY50", "BANKNIFTY"}]
                if not allowed:
                    raise HTTPException(status_code=422, detail="At least one supported instrument (NIFTY50 or BANKNIFTY) must remain enabled.")
                self._content_config.featured_instruments = allowed
            if req.default_capital_inr is not None:
                self._content_config.default_capital_inr = int(req.default_capital_inr)
            if req.default_risk_pct is not None:
                self._content_config.default_risk_pct = float(req.default_risk_pct)
            if req.min_risk_reward_ratio is not None:
                self._content_config.min_risk_reward_ratio = float(req.min_risk_reward_ratio)
            if req.educational_disclaimer is not None and req.educational_disclaimer.strip():
                self._content_config.educational_disclaimer = req.educational_disclaimer.strip()

            self._content_config.read_only_safety_lock = True
            self._content_config.updated_at = datetime.now(timezone.utc).isoformat()
            self._content_config.updated_by = actor.email

            self.record_audit_log(
                actor_id=actor.id,
                actor_email=actor.email,
                action="admin.content.updated",
                target_type="content_config",
                severity="info",
                ip_address=ip_address,
                status="success",
                details="Updated application content and default risk parameters.",
            )
            return self._content_config.model_copy(deep=True)

    def get_system_settings(self) -> AdminSystemSettingsSchema:
        with self._lock:
            return self._system_settings.model_copy(deep=True)

    def update_system_settings(
        self,
        req: UpdateSystemSettingsRequest,
        *,
        actor: AppUserSchema,
        ip_address: str = "127.0.0.1",
    ) -> AdminSystemSettingsSchema:
        with self._lock:
            if req.admin_global_ip_access is not None:
                self._system_settings.admin_global_ip_access = bool(req.admin_global_ip_access)
            if req.session_ttl_seconds is not None:
                self._system_settings.session_ttl_seconds = int(req.session_ttl_seconds)
            if req.login_rate_limit_per_minute is not None:
                self._system_settings.login_rate_limit_per_minute = int(req.login_rate_limit_per_minute)
            if req.max_failed_login_attempts is not None:
                self._system_settings.max_failed_login_attempts = int(req.max_failed_login_attempts)
            if req.lockout_duration_seconds is not None:
                self._system_settings.lockout_duration_seconds = int(req.lockout_duration_seconds)
            if req.live_poll_interval_seconds is not None:
                self._system_settings.live_poll_interval_seconds = int(req.live_poll_interval_seconds)
            if req.off_hours_poll_interval_seconds is not None:
                self._system_settings.off_hours_poll_interval_seconds = int(req.off_hours_poll_interval_seconds)
            if req.maintenance_mode is not None:
                self._system_settings.maintenance_mode = bool(req.maintenance_mode)

            self._system_settings.read_only_trading_invariant = True
            self._system_settings.updated_at = datetime.now(timezone.utc).isoformat()
            self._system_settings.updated_by = actor.email

            self.record_audit_log(
                actor_id=actor.id,
                actor_email=actor.email,
                action="admin.settings.updated",
                target_type="system_settings",
                severity="warning",
                ip_address=ip_address,
                status="success",
                details=(
                    f"Updated system settings (admin_global_ip_access={self._system_settings.admin_global_ip_access}, "
                    f"session_ttl={self._system_settings.session_ttl_seconds}s, "
                    f"rate_limit={self._system_settings.login_rate_limit_per_minute}/min)."
                ),
            )
            return self._system_settings.model_copy(deep=True)

    def list_audit_logs(
        self,
        *,
        search: str | None = None,
        severity: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[AdminAuditLogSchema]:
        with self._lock:
            logs = list(self._audit_logs)
            if severity and severity.strip().lower() != "all":
                sev = severity.strip().lower()
                logs = [item for item in logs if item.severity.lower() == sev]
            if status and status.strip().lower() != "all":
                st = status.strip().lower()
                logs = [item for item in logs if item.status.lower() == st]
            if search and search.strip():
                q = search.strip().lower()
                logs = [
                    item
                    for item in logs
                    if q in item.action.lower()
                    or q in item.actor_email.lower()
                    or q in item.details.lower()
                    or q in item.ip_address.lower()
                ]
            return logs[: max(1, min(500, int(limit)))]

    def list_active_sessions(self, *, current_jti: str = "") -> list[SessionInfoSchema]:
        with self._lock:
            now_ts = int(time.time())
            items: list[SessionInfoSchema] = []
            for s in self._sessions.values():
                if s.revoked or s.expires_at_epoch <= now_ts:
                    continue
                items.append(
                    SessionInfoSchema(
                        jti=s.jti,
                        user_id=s.user_id,
                        username=s.username,
                        email=s.email,
                        role=s.role,
                        ip_address=s.ip_address,
                        user_agent=s.user_agent,
                        created_at=s.created_at,
                        expires_at=datetime.fromtimestamp(s.expires_at_epoch, tz=timezone.utc).isoformat(),
                        is_current=(s.jti == current_jti),
                    )
                )
            items.sort(key=lambda x: x.created_at, reverse=True)
            return items

    def get_stats(self, *, feed_state: str = "closed", session_open: bool = False) -> AdminStatsResponse:
        with self._lock:
            users = [self._to_user_schema(u) for u in self._users.values()]
            sa = self.get_super_admin_record()
            active_sessions = len(self.list_active_sessions())
            return AdminStatsResponse(
                total_users=len(users),
                active_users=sum(1 for u in users if u.status == "active"),
                paused_users=sum(1 for u in users if u.status == "paused"),
                locked_users=sum(1 for u in users if u.status == "locked"),
                admin_users=sum(1 for u in users if u.role == "admin" or u.is_super_admin),
                super_admin_id=sa.id,
                super_admin_username=sa.username,
                global_ip_access_enabled=self._system_settings.admin_global_ip_access,
                active_sessions=active_sessions,
                audit_events_count=len(self._audit_logs),
                error_events_count=len(self._error_logs),
                read_only_mode=True,
                execution_disabled=True,
                market_feed_state=feed_state,
                market_session_open=session_open,
                api_version=__version__,
                environment=self.settings.app_env,
                checked_at=datetime.now(timezone.utc).isoformat(),
            )

    def get_health_report(self, *, market_feed_info: dict[str, object]) -> AdminHealthResponse:
        with self._lock:
            sa = self.get_super_admin_record()
            supabase_configured = bool(
                self.settings.supabase_url.strip() and self.settings.supabase_service_role_key.strip()
            )
            return AdminHealthResponse(
                status="healthy",
                service="allsafe-ai-trading-api",
                version=__version__,
                environment=self.settings.app_env,
                checked_at=datetime.now(timezone.utc).isoformat(),
                uptime_seconds=round(max(0.0, time.monotonic() - self._started_at_monotonic), 2),
                database_mode="supabase_postgres" if supabase_configured else "in_memory_verified_store",
                supabase_configured=supabase_configured,
                super_admin_provisioned=bool(sa and sa.is_super_admin),
                global_ip_access_enabled=self._system_settings.admin_global_ip_access,
                market_feed=market_feed_info,
                security_posture={
                    "password_hashing": "PBKDF2-HMAC-SHA256",
                    "session_signing": "HMAC-SHA256 (as_v1)",
                    "super_admin_id": sa.id,
                    "super_admin_global_ip": sa.allowed_ip == "*",
                    "rate_limit_per_minute": self._system_settings.login_rate_limit_per_minute,
                    "brute_force_max_attempts": self._system_settings.max_failed_login_attempts,
                    "csrf_protection": self._system_settings.csrf_protection_enabled,
                    "read_only_trading_invariant": True,
                },
                recent_errors=list(self._error_logs)[:50],
            )

    def clear_errors(self, *, actor: AppUserSchema, ip_address: str = "127.0.0.1") -> int:
        with self._lock:
            cnt = len(self._error_logs)
            self._error_logs.clear()
            self.record_audit_log(
                actor_id=actor.id,
                actor_email=actor.email,
                action="admin.errors.cleared",
                target_type="error_log",
                severity="info",
                ip_address=ip_address,
                status="success",
                details=f"Cleared {cnt} error diagnostic entries.",
            )
            return cnt


_default_auth_store: AuthStore | None = None


def get_default_auth_store() -> AuthStore:
    global _default_auth_store
    if _default_auth_store is None:
        _default_auth_store = AuthStore()
    return _default_auth_store


def get_auth_store(request: Request) -> AuthStore:
    store = getattr(request.app.state, "auth_store", None)
    if isinstance(store, AuthStore):
        return store
    return get_default_auth_store()


def set_auth_store(app: object, store: AuthStore | None) -> None:
    global _default_auth_store
    _default_auth_store = store
    state = getattr(app, "state", None)
    if state is not None:
        setattr(state, "auth_store", store)
