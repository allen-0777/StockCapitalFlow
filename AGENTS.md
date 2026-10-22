# StockCapitalFlow / LiquidChip agent guide

This root `AGENTS.md` is the canonical agent guide. `.claude/settings.json` also exists and contains Claude Code settings. Use the current code and deployment/workflow definitions as the implementation truth. `README.md`, `docs/technical-spec.md`, and `docs/api-endpoints.md` provide context, but parts of the technical spec and endpoint document describe older behavior. In particular, do not copy their old SQLite deployment, scheduler, or T86 storage rules.

## Project and structure

LiquidChip (籌碼流動) tracks Taiwan institutional flows, margin, futures/options, broker flows, and industry rotation. Python/FastAPI and SQLAlchemy serve React 19 / Vite with Tailwind CSS, Zustand, Recharts, and Lucide.

- `backend/app/main.py`: FastAPI lifespan, CORS, router registration, optional scheduler.
- `backend/app/api/`: health, market, stocks, institutional, watchlist, broker, concentration, industries, and admin routes; `deps.py` implements access gates.
- `backend/app/services/`: ingestion, shared FinMind client, trading calendar, industry sync, rotation calculations, broker analysis, scheduling, and Telegram.
- `backend/app/models/database.py`: ORM tables, sessions, schema guard, unit helper, and TTL cache (in memory, or Redis when configured).
- `backend/scripts/fetch_daily.py`: daily ETL CLI used directly by GitHub Actions.
- `backend/scripts/probe_market_api_dates.py`: external API date probe.
- `backend/scripts/zheng2_push.py`: radar push entry point; exits non-zero with an explicit error before environment/DB setup when `app.services.zheng2_radar` is missing. No radar implementation was committed in available history.
- `backend/tests/`: pytest coverage for ingestion, schema/units, admin, notifications, rotation, authentication, and repository fixes.
- `backend/migrations/`: slim-schema migration, rollback, and destructive cleanup SQL.
- `frontend/src/`: `App.jsx`, dashboard `components/`, Zustand `store/useStore.js`, `apiHeaders.js`, styles, and assets.
- `.github/workflows/`: CI, ETL, digest, keep-awake, status checks, and radar workflow.
- `docs/`: technical specification, API reference, and supporting design/plan documents.

## Data sources and destinations

Service module paths below are relative to `backend/app/services/`.

| Source | Implemented fetcher | Destination |
| --- | --- | --- |
| TWSE BFI82U market institutional net amounts | `fetcher.py:fetch_institutional_market` | `market_daily` |
| TWSE T86 per-stock institutional net shares | `fetcher.py:fetch_institutional_stocks` | `daily_chips`; ticker/name mapping in `stocks` |
| TWSE MI_MARGN credit statistics | `fetcher.py:fetch_margin` | `market_daily.margin_long`, `margin_short` |
| TWSE FMTQIK market turnover | `fetcher.py:fetch_turnover` | `market_daily.market_volume` |
| TAIFEX TX/MTX institutional futures OI | `fetcher.py:fetch_futures_oi` | `market_daily` futures fields |
| TAIFEX foreign Call/Put net OI values | `fetcher.py:fetch_options_data` | `daily_options` |
| FinMind `TaiwanOptionDaily` for TXO | `fetcher.py:fetch_options_data` | `daily_options` P/C ratio, total OI, max-OI strikes |
| FinMind `TaiwanExchangeRate` for USD (Bank of Taiwan cash quotes) | `fetcher.py:fetch_exchange_rate` | `daily_exchange_rate` |
| FinMind `TaiwanStockInfo` | `industry_sync.py:sync_stock_industries` | `stock_industry` |
| FinMind `TaiwanStockTotalReturnIndex` (TAIEX/TPEx), `TaiwanStockPrice` industry proxies | `industry_sync.py:sync_market_series_daily` | `market_series_daily` |
| FinMind `TaiwanStockTradingDailyReport` | `finmind_fetcher.py:fetch_broker_daily` | `broker_daily` |
| FinMind `TaiwanStockPrice` | `finmind_fetcher.py:fetch_stock_price` | `stock_prices` |
| FinMind `TaiwanStockInstitutionalInvestorsBuySell`, `TaiwanStockShareholding` | `backend/app/api/concentration.py` | Response only; no table write |

TWSE requests use its main-site JSON APIs, not the obsolete TWSE OpenAPI fund routes. TAIFEX fetching tries website CSV data and compares it with OpenAPI data, preferring the newer date (CSV wins ties); CSV lookup walks back through recent weekdays. Options P/C is calculated from near-contract position OI in FinMind, not a separate TAIFEX P/C feed. Only FinMind rows matching the TAIFEX date populate that day's row; missing enrichment preserves existing values through `COALESCE` on update. Industry series are representative-stock proxies, not official sector indexes. Broker/price ingestion is triggered by the broker fetch API, outside the daily job set. `finmind_client.py` centralizes sessions, retries/backoff, concurrency, and rate limits.

## Storage and unit contracts

- `daily_chips` stores signed integer **shares (股)** for foreign/trust/dealer net buys. T86 values are stored directly as shares, with an int4 range check. Its primary key is `(stock_id, date)`; PostgreSQL date queries use a BRIN index.
- `shares_to_lots()` in `database.py` divides by **1000** for the chip APIs, watchlist, and institutional ranking/common-buy responses: one 張 = 1000 股. Do not divide again in consumers of those responses.
- Migration `001_slim_daily_chips.sql` multiplies old numeric 張 by **1000** to obtain integer 股; the rollback divides by **1000**. This is not daily ETL logic.
- Market aggregates live in `market_daily`, not a `daily_chips` ticker `0000` row. Institutional money and `market_volume` are 億元 (source 元 divided by `1e8`).
- Margin fields are **changes**, calculated as today's minus previous balance: `margin_long` is 千元; `margin_short` is 張. The market API divides the former by **100000** for `long_yi` and returns the latter as `short_zhang`.
- Futures OI is integer contracts (口). Despite their names, `mtx_retail_long` and `mtx_retail_short` store MTX foreign-investor OI in the current fetcher.
- Options foreign net values convert TAIFEX 千元 to 億元 by dividing by **100000**; `pc_ratio` is put OI / call OI × 100 (percent).
- Broker FinMind buy/sell values are stored as integer shares (股). Analysis stays in shares; the API converts flow `buy_shares`, `sell_shares`, `net_shares` and keypoints `recent_net` to 張 with `shares_to_lots()` (÷1000), retaining legacy field names. The widget displays lots directly. Prices, ratios, scores, and counts are unchanged.
- Concentration institutional responses retain FinMind shares; their widget converts to 張 with `/1000`. Preserve these endpoint-specific unit contracts.

## Deployment and configuration

Production uses Supabase Postgres (LiquidChip DB); `database.py` normalizes URLs for psycopg2. Without `DATABASE_URL`, it falls back to `backend/data.db` (SQLite). Startup calls `init_db()`, which checks the schema and creates tables/indexes/default user; starting the app is therefore a database-writing operation.

`render.yaml` defines the free Render backend with `rootDir: backend`:

```sh
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

`frontend/vercel.json` builds with `npm run build`, publishes `dist`, and rewrites `/api/:path*` to the Render backend. Local `frontend/vite.config.js` proxies `/api` to the backend on port 8000.

Configuration names only; obtain values from the owner's managed configuration:

- Deployment/integration settings: `DATABASE_URL`, `FINMIND_TOKEN`, `TRIGGER_SECRET`, `ALLOWED_ORIGINS`, `ENABLE_SCHEDULER`; Render supplies `PORT`.
- Optional backend settings: `API_KEY`, `FINMIND_MAX_CONCURRENCY`, `FINMIND_MIN_INTERVAL_S`, `REDIS_URL`.
- Telegram notifications: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
- Frontend optional setting: `VITE_API_KEY` (visible in the browser bundle).
- Workflow secrets: `DATABASE_URL`, `FINMIND_TOKEN`, `RENDER_BACKEND_URL`, `TRIGGER_SECRET`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, as needed per workflow.

Mutation gates use `X-API-Key` when `API_KEY` is set; unset allows mutations. Admin routes require `TRIGGER_SECRET`, supplied via `X-Trigger-Secret` or `secret` query.

## GitHub Actions

Cron expressions below are UTC; Taiwan is UTC+8. Render disables its scheduler; Actions runs production jobs.

| File in `.github/workflows/` | Active triggers | Purpose |
| --- | --- | --- |
| `ci.yml` | `push`, `pull_request` | Python 3.11 backend pytest, frontend lint/build, and actionlint |
| `fetch-direct.yml` | `30 9 * * 1-5`; `workflow_dispatch` | Weekdays 17:30 Taiwan: runner ETL directly into Supabase, independent of Render |
| `daily-fetch.yml` | `0 14 * * *`; `workflow_dispatch` | Daily 22:00 Taiwan: wake Render and POST `/api/v1/admin/daily-digest`; notification only |
| `keep-awake.yml` | `0 */5 * * *`; `workflow_dispatch` | Supabase `select 1` and backend health ping |
| `check-status.yml` | `workflow_dispatch` only | Query latest dataset dates and industry mapping count |
| `db-status.yml` | `workflow_dispatch` only | Same DB status checks as `check-status.yml` |
| `zheng2-radar.yml` | `workflow_dispatch` only | Radar push script; fails clearly because the radar service was never committed; schedule remains disabled |

`fetch-direct.yml` defines these exact dispatch inputs (neither declares `required`):

- `jobs`: `type: string`, `default: 'all'`, description `'Jobs to run (逗號分隔，或 all)'`.
- `force`: `type: boolean`, `default: false`, description `'非交易日也執行（補資料用）'`.

The runner passes inputs through `FETCH_JOBS` and `FETCH_FORCE`, not inline shell code. `jobs` accepts `all` or comma-separated `institutional`, `futures`, `margin`, `industry`. `institutional` runs market/T86/turnover; `futures` runs futures/options; `margin` runs margin/FX; `industry` runs mapping/market series. Industry is exempt from the CLI's non-trading-day skip. `--force` bypasses that skip and freshness enforcement; it still writes source dates, not arbitrary historical dates. Normal trading-day runs fail on missing/stale dates or exceptions. `daily-fetch.yml` has a required choice input `job`, default and sole option `daily-digest`. The radar workflow has no active cron schedule. History audit: `f689876` added only its workflow and script; the module path has no commits or deletion record in `git log --all`. `9784910` disabled scheduling; README and docs contain no radar implementation reference.

A past Telegram notification-step edit broke workflow YAML and scheduled runs silently stopped. Validate every workflow edit **before committing**. CI also runs actionlint. From the repo root, download and run actionlint v1.7.7 as CI does (do not commit the downloaded binary):

```sh
bash <(curl -sSfL https://raw.githubusercontent.com/rhysd/actionlint/v1.7.7/scripts/download-actionlint.bash) 1.7.7 && ./actionlint
```

Use `actionlint` for workflow semantics and/or this syntax check (requires PyYAML):

```sh
actionlint
python -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))" .github/workflows/fetch-direct.yml
```

Check each changed YAML file; parsing alone does not validate Actions expressions or semantics.

## Development and verification

The CI backend commands, starting at the repository root, are:

```sh
pip install -r backend/requirements.txt
cd backend
python -m pytest -q
```

Use Python 3.11 as CI does; `backend/pytest.ini` enables automatic asyncio mode. Tests use mocks and isolated SQLite fixtures; keep credentials out of test environments. Do not run ingestion, API date probes, notifications, app startup, or migrations as verification when database/network access has not been authorized.

Frontend commands, starting at the repository root:

```sh
cd frontend
npm ci
npm run lint
npm run build
```

`npm ci` uses the existing `package-lock.json` without rewriting it; prefer it over `npm install`. `npm run lint` and `npm run build` pass and run in CI. `npm run dev` starts Vite; `npm run preview` previews its build; no frontend test script exists. For behavior changes, add/adjust tests in `backend/tests/` and run relevant checks. Keep `docs/api-endpoints.md` synchronized when changing API responses and units.

## Change rules

- Work on a branch and open a PR to `main`; never push directly to `main`.
- Never force-push or rewrite history.
- Never commit secrets or `.env` files; document environment variable names only.
- Never run `backend/migrations/001_cleanup.sql` or drop columns, indexes, or tables without owner **Allen**'s approval. Cleanup deletes the retained pre-migration table and removes the rollback path.
- The schema guard rejects old `daily_chips` layouts to prevent share/lot corruption; do not bypass it or restore the redundant `idx_chips_stock_date` index.
- Respect the task's authorization boundaries for database writes and external services. An instruction to document a command is not authorization to execute it.
