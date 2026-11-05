# AllSafe AI Trading — Landing Page & Authentication Integration Report (`LANDING_PAGE_AUTH_INTEGRATION_REPORT.md`)

- **Audit Date**: November 5, 2026
- **Verification Branch**: `audit/landing-auth-integration-verification`

## 1. Root Cause & Resolution of the `apps/web/src/app/login/page.tsx` Build Issue

### Root Cause
On `main` (`ee90f9eee376cca3b09fff82fbc8f18029221ac6`), `apps/web/src/lib/api.ts` contained only the server-side `getApiHealth()` helper and `HealthResult` type (`// Only import this from Server Components or route handlers: API_BASE_URL is intentionally not exposed to the browser`). When `apps/web/src/app/login/page.tsx` imported `{ API_BASE_URL, fetchApi } from "@/lib/api"` against `main`'s `api.ts` (or when `api.ts` directly evaluated server-only `process.env.API_BASE_URL` at module scope in a client-imported file), Next.js build / CI checks reported missing exports or mixed server/client environment usage.

### Remediation Implemented
1. **Created Browser-Safe `apps/web/src/lib/clientApi.ts`**:
   - Exports `PUBLIC_API_BASE_URL`, `API_BASE_URL` (alias for backwards compatibility), `AuthApiError`, `FetchApiOptions`, and `fetchApi<T>()`.
   - Reads **exclusively** `process.env.NEXT_PUBLIC_API_BASE_URL` (falling back to `https://allsafe-ai-api.onrender.com` in production or `http://localhost:8000` in development).
   - Contains **zero** references to server-only `process.env.API_BASE_URL` or server-only modules.
2. **Updated `apps/web/src/lib/api.ts`**:
   - Keeps `getApiHealth()` and `HealthResult` for Server Components (`apps/web/src/app/page.tsx`, `apps/web/src/app/what-we-done/page.tsx`, `apps/web/src/components/ApiStatus.tsx`).
   - Re-exports `PUBLIC_API_BASE_URL`, `API_BASE_URL`, `AuthApiError`, `fetchApi`, and `type FetchApiOptions` from `./clientApi` so any existing import (`import { API_BASE_URL, fetchApi } from "@/lib/api"`) and any direct client import (`from "@/lib/clientApi"`) both resolve cleanly during TypeScript typechecking, ESLint, and Next.js production builds.

## 2. Landing Page & "What We Done" (5 AI Agents) Integration with Authentication

| Route | Component | Authentication Integration & Security Behavior |
| :--- | :--- | :--- |
| `/` | `apps/web/src/app/page.tsx` -> `LandingPage.tsx` | Server Component fetches `/health` via `getApiHealth()` for initial IST clock calibration; `LandingPage` reads `useAuth()` to show `Open Live Terminal` (`/terminal`) when signed in and routes **Customer Sign In** buttons directly to `/login`. Discloses **zero** proprietary indicator names. |
| `/what-we-done` | `apps/web/src/app/what-we-done/page.tsx` -> `WhatWeDonePage.tsx` | Dedicated page explaining the **Five Specialized AI Agents** that inspect the Indian stock market (**NIFTY 50** & **BANK NIFTY**) and reach unanimous `5/5` consensus to signal **when to BUY**, **when to SELL**, and **when to WAIT**. Discloses **zero** indicator names and routes sign-in actions to `/login`. |
| `/login` | `apps/web/src/app/login/page.tsx` | Dedicated **Customer Sign-In Portal** authenticating via `POST /api/v1/auth/login`, storing session state via `AuthProvider.signIn()`, enforcing customer IP allowlists, and redirecting customers to `/terminal`. |
| `/admin/login` | `apps/web/src/app/admin/login/page.tsx` | Dedicated **Admin Portal Sign-In** authenticating via `POST /api/v1/auth/admin/login` (`portal: "admin"`), supporting TOTP 2FA, enforcing global IP-independent admin access (`*`), blocking customer accounts (`403`), and redirecting administrators to `/admin`. |
| `/terminal` | `apps/web/src/app/terminal/page.tsx` | Protected by `<DashboardAccessGate>` (redirects unauthenticated visitors to `/login?next=/terminal`). Renders `<LiveMarketDashboard />` with zero proprietary indicator names in page headers. |
| `/admin` | `apps/web/src/app/admin/page.tsx` | Protected by `<DashboardAccessGate requireAdmin>` (redirects unauthenticated visitors to `/admin/login?next=/admin` and redirects non-admin `role="user"` accounts to `/terminal`). |
