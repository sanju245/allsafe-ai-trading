# AllSafe AI Trading — Admin Portal & Customer Portal Verification Report (`ADMIN_CUSTOMER_PORTAL_VERIFICATION_REPORT.md`)

- **Audit Date**: November 5, 2026
- **Verification Branch**: `audit/landing-auth-integration-verification`

## 1. Portal Separation Architecture

| Attribute | Admin Portal (`/admin/login` & `/admin`) | Customer Portal (`/login` & `/terminal`) |
| :--- | :--- | :--- |
| **Dedicated Login Route** | `/admin/login` (`apps/web/src/app/admin/login/page.tsx`) | `/login` (`apps/web/src/app/login/page.tsx`) |
| **Backend Login Endpoint** | `POST /api/v1/auth/admin/login` (`portal="admin"`) | `POST /api/v1/auth/login` (`portal="customer"`) |
| **Target Dashboard Route** | `/admin` (`apps/web/src/app/admin/page.tsx`) | `/terminal` (`apps/web/src/app/terminal/page.tsx`) |
| **IP Allowlist Policy** | **Exempt (`*` Global IP Access)**: Super Admin and `admin` accounts authenticate and roam across any IPv4/IPv6 network globally without static IP lockouts. | **Strictly Enforced**: Customer accounts (`role="user"`) with configured IP or CIDR rules (`allowed_ip`) are verified on login, `/api/v1/auth/me`, and `/api/v1/auth/refresh`. |
| **Role Authorization (Server-Side)** | Rejects `role="user"` at `POST /api/v1/auth/admin/login` (`403 Forbidden`, `auth.admin_portal.denied`) and on all `/api/v1/admin/*` endpoints via `require_admin_user` (`403 Forbidden`, `admin.access.denied`). | Authenticates active customer accounts for `/api/v1/live/*`, `/api/v1/market-data/*`, `/api/v1/auth/me`, and `/api/v1/auth/change-password`. |
| **Frontend Route Guard (`DashboardAccessGate`)** | `<DashboardAccessGate requireAdmin>`: Redirects unauthenticated visitors to `/admin/login?next=/admin`; redirects authenticated `role="user"` customers to `/terminal`. | `<DashboardAccessGate>`: Redirects unauthenticated visitors to `/login?next=/terminal`. Hides `Admin Control Center` navigation link from `role="user"` accounts. |
| **MFA / TOTP Support** | Prominent 6-digit RFC 6238 TOTP authenticator input on `/admin/login`, verified in constant time by `verify_totp_code()` (`apps/api/app/auth/security.py`). | Toggleable 2FA / TOTP code input on `/login` for customers who enable 2FA. |
| **Session & Logout Handling** | HMAC-SHA256 (`as_v1`) signed token + `HttpOnly` cookie + `X-CSRF-Token` verification on state-changing requests; `POST /api/v1/auth/logout` revokes `jti` server-side. | Identical cryptographic session & CSRF protections; password rotation (`POST /api/v1/auth/change-password`) automatically revokes prior sessions. |
