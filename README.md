# StockCapitalFlow

台股籌碼流動追蹤系統 — daily ETL of Taiwan market institutional flows into Postgres, served through a FastAPI API and a React dashboard.

**Live:** https://stock-capital-flow.vercel.app

## Architecture

```
GitHub Actions (cron, Mon–Fri 17:30 Asia/Taipei)
  └─ fetch-direct.yml → backend/scripts/fetch_daily.py
       ├─ TWSE website JSON   (institutional buy/sell, per-stock T86, margin, turnover)
       ├─ TAIFEX website CSV  (futures / options open interest; OpenAPI as fallback)
       └─ FinMind API         (options P/C ratio, max-OI strikes, foreign holdings, industries)
            │  retry + backoff + rate limiting, strict parsing, batched upserts
            ▼
  Supabase Postgres 17  ◀── FastAPI backend on Render ◀── React + Vite frontend on Vercel
```

| Layer | Tech |
|---|---|
| Ingestion | Python 3.11, aiohttp, pandas, exchange-calendars (trading-day logic) |
| Storage | Supabase Postgres 17 (SQLite fallback for local dev), SQLAlchemy |
| API | FastAPI on Render (free plan) |
| Frontend | React 19, Vite, Tailwind CSS, Zustand, Recharts on Vercel |
| Orchestration | GitHub Actions scheduled workflows |
| Quality | GitHub Actions CI: pytest + actionlint |

## Data pipeline

The daily fetch runs directly on the GitHub Actions runner and writes to Supabase; it does not depend on the Render backend being awake.

| Job | Steps | Source |
|---|---|---|
| `institutional` | market-wide + per-stock institutional buy/sell, turnover | TWSE |
| `futures` | futures OI by investor type, options OI / P/C ratio | TAIFEX CSV (OpenAPI fallback), FinMind |
| `margin` | margin / short balances, USD/TWD rate | TWSE, FX source |
| `industry` | stock → industry mapping, market series | FinMind / TWSE (runs on non-trading days too) |

Reliability features:

- **Trading calendar**: non-trading days are skipped unless `force` is set (for backfills).
- **Freshness check**: on a trading day the run fails if a source returns data older than the expected trading date, so stale data is never silently accepted.
- **Batched upserts**: per-stock rows (~20k/day) are written in batches instead of row-by-row round trips.
- **FinMind client**: retries with exponential backoff, configurable concurrency and request interval.
- **TAIFEX**: the website CSV is published around 15:00 on the trading day, while the OpenAPI updates the next morning, so the CSV is primary and the OpenAPI is the fallback.

Manual run / backfill: *Actions → Direct Daily Fetch → Run workflow* (`jobs`: `all` or comma-separated job names; `force` to run on non-trading days).

### Scheduled workflows

| Workflow | Schedule (Asia/Taipei) | Purpose |
|---|---|---|
| `fetch-direct.yml` | Mon–Fri 17:30 | Daily ETL into Supabase |
| `daily-fetch.yml` | Daily 22:00 | Calls `/api/v1/admin/daily-digest` on the backend |
| `keep-awake.yml` | Every 5 h | `select 1` against Supabase + backend health ping |
| `ci.yml` | On push / PR | pytest + actionlint |

## API (selected)

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/health` | Status and last update time per dataset |
| GET | `/api/v1/market/summary` | Market institutional flows, margin, futures OI |
| GET | `/api/v1/market/options` | Options P/C ratio, max-OI strikes |
| GET | `/api/v1/market/exchange-rate` | USD/TWD |
| GET | `/api/v1/market/rotation` | Sector rotation |
| GET | `/api/v1/institutional/ranking` | Institutional buy/sell ranking |
| GET | `/api/v1/institutional/common-buy` | Stocks bought by both foreign and investment trusts |
| GET | `/api/v1/stocks/search?q=` | Search by ticker or name |
| GET | `/api/v1/stocks/{id}/chips` | Per-stock institutional history |
| GET | `/api/v1/stocks/{id}/concentration` | Concentration and foreign holding ratio |
| GET | `/api/v1/stocks/{id}/broker/flow` | Broker branch flows |
| GET | `/api/v1/industries` | Industry list and series |
| GET/POST/DELETE | `/api/v1/users/{id}/watchlist` | Watchlist |
| POST | `/api/v1/admin/trigger/{job}` | Trigger a fetch job (requires `TRIGGER_SECRET`) |

**Optional API key:** when `API_KEY` is set on the backend, mutation routes require an `X-API-Key` header. The frontend sends `VITE_API_KEY` if configured (it is visible in the client bundle, so treat it as a shared access gate, not a secret).

## Local development

Requirements: Python 3.11+, Node.js 18+.

```bash
# Backend
cd backend
pip install -r requirements.txt
cp .env.example .env          # without DATABASE_URL, a local SQLite file is used
uvicorn app.main:app --reload --port 8000

# Tests
python -m pytest -q

# Frontend
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

Run the ETL locally:

```bash
cd backend
python scripts/fetch_daily.py --jobs institutional,margin   # or --jobs all [--force]
```

## Configuration

Backend (`backend/.env` / Render):

| Variable | Description |
|---|---|
| `DATABASE_URL` | Supabase Postgres connection string (`postgres://` / `postgresql://` are normalized for SQLAlchemy) |
| `FINMIND_TOKEN` | FinMind API token |
| `TRIGGER_SECRET` | Secret for admin trigger endpoints |
| `API_KEY` | Optional; enables `X-API-Key` on mutation routes |
| `ALLOWED_ORIGINS` | CORS origins (Vercel domain) |
| `ENABLE_SCHEDULER` | `false` on Render; scheduling is done by GitHub Actions |
| `FINMIND_MAX_CONCURRENCY`, `FINMIND_MIN_INTERVAL_S` | FinMind rate limits |

GitHub Actions secrets: `DATABASE_URL`, `FINMIND_TOKEN`, `RENDER_BACKEND_URL`, `TRIGGER_SECRET`.

Frontend (Vercel): `VITE_API_KEY` (optional).

## Database migrations

Schema changes are applied as SQL scripts in `backend/migrations/`, each with a matching rollback script.

## Data timing

Sources publish at different times, so dashboard sections can show different dates; the page header shows the trading date for each metric.

- TWSE institutional / margin: after market close, available by the 17:30 run
- TAIFEX futures / options OI: website CSV around 15:00
- FinMind P/C ratio: same day or next day

## Disclaimer

For personal research and learning only. Not investment advice.
