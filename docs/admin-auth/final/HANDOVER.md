# HANDOVER

## Where things are
Branch `fix/admin-login-any-ip` (local to the agent session; delivered as `fix-admin-login-any-ip.bundle` plus patches). Base `main` @ `8d9138b`. Commits: `416216e`, `1acebe4`, `6984e29`, then documentation. Reports in `docs/admin-auth/` (earlier, superseded where they conflict) and `docs/admin-auth/final/` (authoritative).

## How to take it over
`git clone -b fix/admin-login-any-ip fix-admin-login-any-ip.bundle repo` → `git push -u origin fix/admin-login-any-ip` → open a PR to `main`. Run the commands in TEST_EVIDENCE.md before merging.

## Key decisions recorded
- Super Admin (`sanjay@gmail.com`, the single admin) may log in from any IP; MFA off by owner decision.
- Customers keep exact-IP restriction (owner confirmed).
- Defence-in-depth fixes added after audit; open risks listed in FINAL_SECURITY_AUDIT.md.

## Do-not list
Do not deploy or run migrations without owner approval; do not force-push or rewrite `416216e`/`1acebe4`; do not put credentials in code, docs, logs or chat; do not enable autonomous trading.

## Known limitations of this delivery
No real pytest/FastAPI or frontend build was run by the author; GitHub and Dropbox were unreachable; Vercel not inspected.

## Audit update 2026-11-05
A further docs-only commit on this branch records the verification audit (`VERIFICATION_AUDIT_2026-11-05.md`). Nothing has been pushed; the bundle delivered with this commit supersedes the `b79c05d` bundle. Before merging run the origin-bypass test in section 4 of that file.
