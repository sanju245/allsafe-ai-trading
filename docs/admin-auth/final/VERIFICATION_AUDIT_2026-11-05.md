# VERIFICATION_AUDIT_2026-11-05

Independent re-check of everything on branch `fix/admin-login-any-ip` against GitHub and against the code at HEAD. Labels: VERIFIED / FAILED / NOT TESTED / BLOCKED / UNVERIFIED.

## 1. GitHub state (VERIFIED by `git ls-remote https://github.com/sanju245/allsafe-ai-trading.git`, 2026-11-05)
- Remote heads: `main` = `8d9138b`, plus codex/live-groww-dashboard, feature/admin-customer-access, feature/groww-live-api, fix/auth-cors-admin-integrity, phase-2-market-data, phase-3-live-market-data; PRs #1-#6 only.
- **`fix/admin-login-any-ip` does not exist on GitHub. Commits `416216e`, `1acebe4`, `6984e29`, `b79c05d` are NOT on GitHub. No PR exists.**
- `git push -u origin fix/admin-login-any-ip` -> `remote: access denied by the git proxy: sanju245/allsafe-ai-trading is not in this session's authorized repository set` / `fatal: unable to access ... 403`. `add_repo` -> `link your GitHub account to let Claude access repositories`. Upload STOPPED here.
- github.com web URLs for the four commits returned HTTP 403 to the sandbox proxy (inconclusive on its own; `ls-remote` is conclusive).
- Dropbox: no connector or tool exists in this session -> BLOCKED. No links exist.

## 2. File-by-file (22 files vs `main` 8d9138b: 7 modified, 15 added, 0 deleted)
Local = present and committed, working tree clean. Remote = FAIL for every row (branch absent). Evidence = `git ls-remote` output above; blob ids are from the local HEAD tree.

| File | Change | Commits | Blob | Local/Git | Remote | Result |
|---|---|---|---|---|---|---|
| apps/api/app/security.py | M | 416216e,1acebe4,6984e29 | 48027e165b | committed | absent | FAIL (not uploaded) |
| apps/api/app/config.py | M | 416216e,6984e29 | 2e00cbaa26 | committed | absent | FAIL |
| apps/api/.env.example | M | 416216e,6984e29 | ca8e2f8085 | committed | absent | FAIL |
| apps/api/app/routers/auth.py | M | 416216e,1acebe4 | 60aafecc69 | committed | absent | FAIL |
| apps/web/src/components/auth/AuthProvider.tsx | M | 416216e,1acebe4 | 65ea534d54 | committed | absent | FAIL |
| apps/web/src/app/account/page.tsx | M | 416216e,1acebe4 | e91ae57e50 | committed | absent | FAIL |
| supabase/README.md | M | 416216e,1acebe4 | 3d8015fd6c | committed | absent | FAIL |
| apps/api/tests/test_auth_ip_policy.py | A | 1acebe4,6984e29 | 24c6812379 | committed | absent | FAIL |
| apps/api/tests/test_auth_ip_policy_api.py | A | 1acebe4,6984e29 | 601df1cdc1 | committed | absent | FAIL |
| apps/api/tests/test_auth_hardening.py | A | 6984e29 | 8f34b75a81 | committed | absent | FAIL |
| docs/admin-auth/CLAUDE_ADMIN_AUTH_FIX_REPORT.md | A | 416216e..b79c05d | 6aa68ec950 | committed | absent | FAIL |
| docs/admin-auth/CLAUDE_ADMIN_AUTH_TEST_REPORT.md | A | 416216e..b79c05d | 9351b65f37 | committed | absent | FAIL |
| docs/admin-auth/test-evidence-security-layer-shim-run.txt | A | 416216e,1acebe4 | 469293f350 | committed (OUTDATED, bannered) | absent | FAIL |
| docs/admin-auth/final/{FINAL_SECURITY_AUDIT,VULNERABILITY_FIXES,IMPLEMENTATION_REPORT,TEST_EVIDENCE,DEPLOYMENT_GUIDE,ROLLBACK_PLAN,PROJECT_STATUS,HANDOVER}.md | A | b79c05d | see git | committed | absent | FAIL |
| docs/admin-auth/final/test-evidence-shim-run-3.txt | A | b79c05d | cf729a0726 | committed | absent | FAIL |

Added by this audit commit: `final/VERIFICATION_AUDIT_2026-11-05.md`, `final/test-evidence-shim-run-head-b79c05d.txt`; edited: TEST_EVIDENCE, IMPLEMENTATION_REPORT, PROJECT_STATUS, HANDOVER, the earlier test report, and the outdated log (banner).
Local checks (VERIFIED): working tree clean; no untracked files; `git diff --check` clean; `compileall` OK; no `.env` tracked; secret-pattern scan of the added lines found nothing; code files unchanged between `6984e29` and `b79c05d`.
Issues found and fixed in this audit commit: approximate mutation counts ("8+"), stale 58-test log, file totals missing from IMPLEMENTATION_REPORT. Each of the 8 required deliverables exists in `final/`.

## 3. The five fixes at HEAD (code read + tests + probes)
| # | Fix | Evidence | Verdict |
|---|---|---|---|
| 1 | Customer wrong-IP attempts counted per account, 10 / 900 s, then 429 | `security.py` `ip_mismatch_throttle.check(user_id, ...)` runs only on mismatch; mutation M4 fails 1 test | PRESENT (mocked tests) |
| 2 | Signing-key refresh limited | `_load_jwks`: forced refresh skipped when cached and < 30 s since last attempt; M5 fails 2 tests. Pre-existing 600 s cache TTL path unchanged | PRESENT |
| 3 | Failures without trusted IP use shared bucket (5x limit); valid tokens never throttled | `_record_failed_authentication` only called on 401; M7 fails 1 test | PRESENT |
| 4 | Duplicate `CF-Connecting-IP` fail closed | probe: duplicate identical/different and comma list -> 503; M6 fails 1 test | PRESENT |
| 5 | IPv4-mapped IPv6 canonicalised both sides | probe: `::ffff:192.0.2.10`, hex form, upper case -> `192.0.2.10`; stored `::ffff:...` /128 -> IPv4; ranges rejected; M3 fails 3 tests | PRESENT |
Other probes: `X-Forwarded-For`, `X-Real-IP`, `Forwarded`, `True-Client-IP` without `CF-Connecting-IP` -> 503; CF header wins over a conflicting XFF; leading-zero IPv4 and empty header -> 503.

Weaknesses (none new regressions): (a) a zone-id IPv6 string is accepted as a client IP string - it can only fail to match, harmless; (b) IPv4-compatible `::a.b.c.d` is not mapped - fails closed; (c) limiters are process-local (O-2); (d) if the origin were directly reachable, a forged `CF-Connecting-IP` could both defeat a customer's IP check (for a token holder who knows the registered IP) and fill another IP's failed-auth bucket (affects only failing requests).

## 4. Render origin bypass - UNVERIFIED (not production-safe on evidence)
Not provable from this sandbox: requests to `*.onrender.com` are refused by the sandbox proxy (HTTP 403 from the proxy, not from Render), and Render does not document that its origin is reachable only via Cloudflare. The IP restriction for customers is therefore **defence in depth, not a proven control**. Test to run from an outside network (with a test customer, never the admin): send `GET https://allsafe-ai-api.onrender.com/api/v1/auth/me` with that customer's valid token from an IP that is NOT registered, adding header `CF-Connecting-IP: <registered IP>`. Expect 403 `ip_not_allowed`; a 200 means the header can be forged and the IP rule is bypassable.

## 5. Tests
- Real backend `pytest`: NOT RUN (FastAPI/pytest/httpx cannot be installed; PyPI refused). A reviewer's 320/320 on the older bundle (416216e/1acebe4) is not reproduced and predates 6984e29.
- Stand-in harness on HEAD: 71 passed, 0 failed, exit 0 - NOT a substitute for the project tests.
- Frontend `npm ci`, lint, typecheck, build: NOT RUN (npm registry refused; `node_modules` is an incomplete partial install without next/typescript/eslint).
- Integration tests (`test_auth_ip_policy_api.py`, CORS, admin API): NOT RUN.
