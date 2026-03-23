# Error Notification & Debug Enhancement Design

**Date**: 2026-03-23
**Status**: Approved
**Scope**: Backend notification service, improved error handling, GitHub Actions daily digest

---

## Problem Statement

Most database tables are empty or nearly empty due to silent failures in the fetch pipeline:
- `fetch_institutional_stocks` silently returns when TWSE T86 returns `stat != "OK"` → `stocks` table stays empty
- `fetch_options_data` silently returns when FinMind quota is exceeded → `daily_options` stays empty
- GitHub Actions always exits 0, so failures are invisible
- No notification when data is missing or stale

---

## Goals

1. Telegram notifications: failure alerts, per-job success summaries, daily morning digest
2. Structured per-step error details in API responses
3. Timing logs in backend fetchers
4. GitHub Actions exits non-zero on real errors (including partial failures)

---

## Architecture

### New / Modified Files

```
backend/app/services/notification.py   ← new
backend/app/services/fetcher.py        ← modify (error handling + timing)
backend/app/api/admin.py               ← modify (error capture + notification call)
.github/workflows/daily-fetch.yml     ← modify (daily-digest job, exit 1 on error)
```

### Data Flow

```
GitHub Actions
  → POST /api/v1/admin/trigger/{job}?secret=XXX
      → fetcher functions (with timing + exception raising)
      → [after all retries exhausted] NotificationService.send_job_result()
  → Returns detailed JSON per step

GitHub Actions (09:00 CST daily)
  → POST /api/v1/admin/daily-digest?secret=XXX
      → Query DB for most recent available data
      → NotificationService.send_daily_digest()
```

### Environment Variables

| Variable | Where to set | Purpose |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Render env only | Backend uses this to call Telegram API |
| `TELEGRAM_CHAT_ID` | Render env only | Backend uses this to identify target chat |

Note: GitHub Actions does NOT need these. Notification logic lives entirely in the backend. GitHub Actions only needs `RENDER_BACKEND_URL` and `TRIGGER_SECRET`.

---

## Component: NotificationService

**File**: `backend/app/services/notification.py`

### Functions

```python
async def send_message(text: str) -> None
# Base send. Truncates to 4096 chars (Telegram limit) before sending.
# Silently logs warning on failure — never raises.

async def send_job_result(job: str, steps: list[dict], got_date, expected_date) -> None
# Called ONCE after all retries are exhausted (not on each retry attempt).
# expected_date comes from latest_trading_day() in trading_calendar.py.

async def send_daily_digest(db: Session) -> None
# Called by /admin/daily-digest endpoint.
# Queries most recent row in daily_chips and daily_options regardless of date.
# Works correctly on holidays — shows last available data with its actual date.
```

### Status Constants

Use string constants to avoid inconsistent literals:

```python
STEP_OK = "ok"
STEP_ERROR = "error"
JOB_OK = "ok"
JOB_PARTIAL = "partial_error"
JOB_ERROR = "error"
```

### Message Formats

**Success:**
```
✅ institutional 完成 (2026-03-21)
外資: +12.3億 | 投信: -2.1億 | 自營: +0.8億
個股: 1,523 筆 | 耗時: 3.2s
```

**Partial failure:**
```
⚠️ futures 部分失敗 (2026-03-21)
✓ fetch_futures_oi — 2.1s
✗ fetch_options_data — FinMind 配額已用盡 (HTTP 402)
```

**Full failure:**
```
❌ institutional 失敗 (2026-03-21)
✗ fetch_institutional_market — TWSE BFI82U stat=CLOSE
✗ fetch_institutional_stocks — TWSE T86 stat=CLOSE
```

**Daily digest (09:00 CST):**
```
📊 每日彙整 2026-03-21
法人: 外資 +12.3億 | 投信 -2.1億 | 自營 +0.8億
融資: +2.3億 | 融券: -1,200 張
台指外資: 多 15,234 空 12,100 淨 +3,134
選擇權: P/C=92.3% | 壓力 19,500 | 支撐 19,000
```

### Fault Tolerance

Telegram send failures are caught and logged as warnings. They never propagate to the job or affect data writes.

---

## Component: fetcher.py Changes

### Error Handling

Replace silent `return` on API failures with `raise RuntimeError(...)`.

Two distinct error categories:

**API / infrastructure errors** (always raise):

| Function | Trigger | Error raised |
|----------|---------|-------------|
| `fetch_institutional_stocks` | TWSE `stat != "OK"` | `RuntimeError(f"TWSE T86 stat={stat}")` |
| `fetch_institutional_market` | TWSE `stat != "OK"` | `RuntimeError(f"TWSE BFI82U stat={stat}")` |
| `fetch_margin` | TWSE `stat != "OK"` | `RuntimeError(f"TWSE MI_MARGN stat={stat}")` |
| `fetch_futures_oi` / `fetch_options_data` | FinMind HTTP 402 | Already raises `RuntimeError("FinMind API 配額已用盡")` — keep as-is |

**Data not yet published** (return None → retry handles it):

| Function | Trigger | Behavior |
|----------|---------|---------|
| `fetch_futures_oi` | FinMind returns empty data for all 5 lookback days | `raise RuntimeError("FinMind 近 5 日查無期貨OI數據")` |
| `fetch_options_data` | Same | `raise RuntimeError("FinMind 近 5 日查無選擇權數據")` |

Note: "No data for 5 days" is treated as an error (not a retry candidate) because the retry loop in GitHub Actions already covers the case where data isn't published yet on day 0.

### Timing Logs

Each function logs execution time:
```
[fetcher][institutional_stocks] 1,523 筆 in 2.3s (2026-03-21)
[fetcher][fetch_futures_oi] ERROR in 1.2s: FinMind 配額已用盡
```

---

## Component: admin.py Changes

### Per-Step Error Capture

Wrap each `fn()` call in try-except. Accumulate step results:

```python
steps.append({
    "fn": fn.__name__,
    "status": STEP_OK | STEP_ERROR,   # use constants
    "duration_s": float,
    "rows": int | None,               # where applicable
    "error": str | None,
    "date": str | None,
})
```

### Status Logic

| Condition | Returned `status` |
|-----------|------------------|
| All functions succeed | `"ok"` |
| Some functions fail | `"partial_error"` |
| All functions fail | `"error"` |

### Notification Timing

`send_job_result()` is called **once**, after all fetch functions have run. Never called mid-retry.

### Authentication

`POST /api/v1/admin/daily-digest?secret=XXX` uses the same `TRIGGER_SECRET` validation as the existing trigger endpoint. Returns HTTP 403 on invalid/missing secret.

### New Endpoint

```
POST /api/v1/admin/daily-digest?secret=XXX
```

Queries most recent row from `daily_chips` (stock_id='0000') and `daily_options`, formats, and calls `send_daily_digest()`. Returns `{"status": "ok", "date": "..."}`.

---

## Component: GitHub Actions Changes

### Exit Codes

| Final STATUS | Exit code | Effect |
|-------------|-----------|--------|
| `"ok"` | 0 | Success |
| `"skipped"` | 0 | Non-trading day |
| `"partial_error"` | 1 | GitHub marks run failed, emails owner |
| `"error"` | 1 | GitHub marks run failed, emails owner |
| Retries exhausted, no success | 1 | GitHub marks run failed, emails owner |

### New `daily-digest` Job

```yaml
- cron: '0 1 * * 1-5'   # 09:00 CST — daily digest
```

Calls `/api/v1/admin/daily-digest?secret=XXX`. Always exits 0 (digest failure should not spam as "failure").

---

## Out of Scope

- `stock_prices` and `broker_daily` fetching (on-demand, not daily cron)
- Backup API sources (separate concern)
- Frontend error display
- Retry-per-attempt notifications (would cause spam)
