# Project Status

**Project:** AllSafe AI Trading
**Last updated:** 2026-10-09
**Current phase:** Phase 1 (Foundation), files written, NOT yet built or tested end to end

> Read the "Tests actually run" and "Installation problems" sections first. Phase 1 code has **not** been installed, built, type-checked, linted or unit-tested, because package registries were unreachable in the build environment.

## Completed tasks

- [x] Repository structure created (`apps/web`, `apps/api`, `docs`)
- [x] Next.js (App Router, TypeScript, Tailwind CSS v4) frontend files written by hand
- [x] Separate FastAPI backend written with `GET /health`
- [x] Landing page with honest "No data source" placeholders (no prices, no signals)
- [x] Frontend shows backend status by calling `/health` server-side
- [x] Environment examples without secrets (`apps/api/.env.example`, `apps/web/.env.example`)
- [x] README with setup and startup instructions
- [x] `.gitignore` for env files, virtual environments, dependencies and build output
- [x] Health test written (`apps/api/tests/test_health.py`)
- [x] Git initialised on branch `main` (no commits yet)
- [ ] Dependencies installed (blocked, see below)
- [ ] Health test executed (blocked, see below)
- [ ] Frontend built and type-checked (blocked, see below)

## Files created

```
.gitignore
README.md
PROJECT_STATUS.md
docs/ARCHITECTURE.md
apps/api/.env.example
apps/api/pytest.ini
apps/api/requirements.txt
apps/api/requirements-dev.txt
apps/api/app/__init__.py
apps/api/app/config.py
apps/api/app/main.py
apps/api/app/providers/__init__.py      (placeholder, Phase 2)
apps/api/app/indicators/__init__.py     (placeholder, Phase 3)
apps/api/app/signals/__init__.py        (placeholder, Phase 4)
apps/api/tests/test_health.py
apps/web/.env.example
apps/web/package.json
apps/web/tsconfig.json
apps/web/next.config.ts
apps/web/postcss.config.mjs
apps/web/eslint.config.mjs
apps/web/src/app/globals.css
apps/web/src/app/layout.tsx
apps/web/src/app/page.tsx
apps/web/src/components/ApiStatus.tsx
apps/web/src/lib/api.ts
```

Deviation from the architecture plan: env examples are per app (`apps/api`, `apps/web`) instead of one root file, because Next.js and FastAPI each load their own env file.

No existing files were overwritten or deleted. The workspace was empty.

## Commands executed

Phase 1 session (build environment: Linux, Node 22.22, Python 3.13):

| Command (summary) | Outcome |
|---|---|
| `mkdir -p` project directory tree | Succeeded |
| Python `ast.parse` over all 7 `.py` files | 0 syntax errors |
| Python `json.load` on `package.json`, `tsconfig.json` | Both valid |
| TypeScript `transpileModule` over 5 `.ts/.tsx` files | 0 syntax errors (see caveat below) |
| `grep` for non-empty values in `.env.example` files | Only `development`, `http://localhost:3000`, `http://127.0.0.1:8000` |
| `git init -b main` | Succeeded |
| `git check-ignore` on env, venv, `node_modules`, `.next`, `__pycache__` paths | All ignored |
| `git check-ignore` on both `.env.example` files | Not ignored (will be tracked) |
| `git add -n -A` (dry run) | 25 files would be tracked, no secrets |

Earlier inspection session (before Phase 1):

| Command | Outcome |
|---|---|
| `npm view lightweight-charts version` | **Failed**, see below |
| `python3 -m pip download fastapi==0.115.0 --no-deps` | **Failed**, see below |
| `curl $HTTPS_PROXY/__agentproxy/status` | Proxy enabled, no relay failures recorded |

No `npm install`, `create-next-app`, `pip install`, `pytest`, `next build`, `tsc`, or `eslint` was run in this phase.

## Tests actually run and their results

- **Unit tests (pytest): NOT RUN.** `fastapi`, `pytest`, `httpx` and `pydantic-settings` are not installed in the build environment and could not be installed.
- **Frontend build, `tsc --noEmit`, `eslint`: NOT RUN.** `next`, `react`, `tailwindcss` and the `@types/*` packages are not installed.
- **What did run** was static, offline checking only:
  - Python files parse without syntax errors.
  - JSON config files are valid.
  - TypeScript files parse without syntax errors. This used a TypeScript compiler (6.0.3) that already existed in the environment's global tools, not the project's own dependency, and checks syntax only. It does **not** prove the types, imports or Next.js APIs are correct.
- **Live integration: NOT TESTED.** The frontend-to-backend `/health` call has never been executed.

## Installation problems

Exact failures observed (not retried, because the proxy documentation says 403 responses are an organisation egress policy that must be reported, not bypassed):

```
$ npm view lightweight-charts version
npm error code E403
npm error 403 403 Forbidden - GET https://registry.npmjs.org/lightweight-charts

$ python3 -m pip download fastapi==0.115.0 --no-deps
ERROR: Could not find a version that satisfies the requirement fastapi==0.115.0 (from versions: none)
ERROR: No matching distribution found for fastapi==0.115.0
```

Consequences:

- `create-next-app` could not be used, so the Next.js scaffold was **written by hand** to mirror what it generates.
- **Dependency versions in `apps/web/package.json` are from memory and unverified** (`next ^16`, `react ^19.2`, `tailwindcss ^4`, `eslint ^9`, `eslint-config-next ^16`, `typescript ^5`). If `npm install` reports a version or peer-dependency problem, adjust the version or regenerate with `create-next-app` and copy `src/` over.
- The `eslint.config.mjs` import paths follow the Next.js 16 flat-config layout and have not been executed.
- No lockfiles exist yet. Commit `package-lock.json` after the first successful `npm install`.

## Known risks to verify on first local run

1. `npm install`, `npm run typecheck`, `npm run lint`, `npm run build` may reveal version or config issues.
2. `pytest` has never executed; the test relies on `httpx` (listed in `requirements-dev.txt`).
3. `next-env.d.ts` is generated on first `npm run dev` or `build` and is intentionally git-ignored.

## Remaining tasks

**Phase 1 close-out (needs a machine with registry access):**
- Install dependencies and run `pytest`, `npm run typecheck`, `npm run lint`, `npm run build`.
- Fix any errors, commit lockfiles, make the first Git commit.

**Later phases:**
- Phase 2: market-data provider interface, candle schema, validation, stale/missing data handling. Provider not yet chosen.
- Phase 3: UT Bot Alerts and other indicators in pandas, with unit tests.
- Phase 4: deterministic signal engine (confirmed vs provisional).
- Phase 5: candlestick charts, Supabase auth, dashboards.
- Phase 6: multi-timeframe analysis, backtesting, paper trading.
- Phase 7: admin dashboard; news analysis afterwards.

**Open decisions:** market-data source and its terms of use; free-tier hosting terms for a public site; regulatory review of publishing buy/sell signals in India (get qualified advice before public launch).

## Next recommended prompt

> Phase 1 is verified locally (pytest, typecheck, lint and build pass; results below). Begin Phase 2: define a market-data provider interface and a validated Candle schema in `apps/api/app/providers`. Add validation for ordering, duplicates, gaps, invalid OHLC values, and stale data, with unit tests. Do not connect a real data provider yet and do not implement indicators. Any test fixtures must be clearly labelled SAMPLE. Update PROJECT_STATUS.md and stop.
>
> Local results: [paste the output of pytest / npm run typecheck / npm run lint / npm run build]
