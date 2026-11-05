# DEPLOYMENT_GUIDE (NOT executed — requires explicit owner approval)

## Verified configuration (read-only, 2026-11-03)
Render `allsafe-ai-api` (`srv-db5qv2flk1mc73augr40`): free plan, 1 instance, Singapore, branch `main`, auto-deploy on commit, root `apps/api`, build `pip install -r requirements.txt`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, no health-check path, inbound IP rule `0.0.0.0/0`, PR previews off. **Vercel: BLOCKED** (scope consent not granted; project `allsafe-ai-trading`). Branch pushes are expected to create Vercel preview deployments (UNVERIFIED).

## Database
No migration and no data change required. Do not run any migration. The separate two-admin migration is out of scope.

## Pre-deploy gates
1. Push branch, open PR to `main`.
2. In a full environment run the real suite and the web checks (see TEST_EVIDENCE.md); all must pass.
3. Decide O-1 (CF-Connecting-IP trust) — confirm with Render support or accept the risk in writing.
4. Rotate the Super Admin password (it was shared in chat).

## Deploy (after approval)
Merge PR → Render auto-deploys `main`; watch build/deploy logs → Vercel redeploys the web app.
Optional env vars (defaults are fine): `AUTH_RATE_LIMIT_PER_MINUTE`, `AUTH_FAILURE_LIMIT`, `AUTH_IP_MISMATCH_LIMIT`.

## Post-deploy verification
1. Admin sign-in from a network other than the stored IP → `/auth/me` 200; `/admin/users` loads.
2. A test customer from a non-registered IP → 403 `ip_not_allowed`; from the registered IP → 200.
3. Paused test customer → 403. Invalid token → 401.
4. Check Render logs for errors; free-plan cold start (~1 min) is normal.
Do not test with real customer accounts.
