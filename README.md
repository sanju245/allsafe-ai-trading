# AllSafe AI Trading

A public Indian stock-market analysis website for **NIFTY 50** and **BANK NIFTY**, built around transparent, rule-based signals (UT Bot Alerts as the primary indicator).

> **Analysis only.** This project never places broker orders. Users trade manually. Nothing here is investment advice, and no strategy guarantees profit.

**Current phase:** 1 of the roadmap (foundation). There is no market data, no indicators and no signals yet. See [PROJECT_STATUS.md](PROJECT_STATUS.md) for exactly what exists and what has been tested.

## Repository layout

```
allsafe-ai-trading/
├─ apps/
│  ├─ web/   Next.js (App Router, TypeScript, Tailwind CSS) frontend
│  └─ api/   Python FastAPI backend (market logic lives here)
├─ docs/
│  └─ ARCHITECTURE.md
├─ PROJECT_STATUS.md
└─ README.md
```

## Prerequisites

- Node.js 20.9 or newer (22 recommended) and npm
- Python 3.11 or newer
- Git

All tooling used so far is free.

## Backend setup (FastAPI)

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env               # Windows: copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

Check it: open <http://127.0.0.1:8000/health>. Interactive docs are at <http://127.0.0.1:8000/docs>.

Run the backend test (from `apps/api`, venv active):

```bash
pytest
```

## Frontend setup (Next.js)

```bash
cd apps/web
npm install
cp .env.example .env.local         # Windows: copy .env.example .env.local
npm run dev
```

Open <http://localhost:3000>. The header shows **Backend online** when the API above is running, otherwise **Backend offline**.

Other frontend scripts:

```bash
npm run typecheck   # tsc --noEmit
npm run lint        # eslint
npm run build       # production build
```

## Environment variables

Real secrets must never be committed. Only the `.env.example` files are tracked.

| File | Purpose |
|---|---|
| `apps/api/.env.example` | Server-side settings (CORS, future Supabase and data-provider keys) |
| `apps/web/.env.example` | `API_BASE_URL` (server-only) and future public Supabase values |

Rules: provider keys and the Supabase service-role key belong only in `apps/api/.env`. Nothing sensitive may use the `NEXT_PUBLIC_` prefix.

## Data integrity rules

- No live prices are shown unless they come from a tested data provider.
- Sample or demo data must never be labelled live.
- Default signals use confirmed candle closes; provisional signals are labelled as such.
- Signal rules are deterministic. An LLM may only explain a signal; it never creates prices or decides trades.

## Roadmap

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [PROJECT_STATUS.md](PROJECT_STATUS.md).
