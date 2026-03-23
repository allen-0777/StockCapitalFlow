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
4. GitHub Actions exits non-zero on real errors

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
      → NotificationService.send_job_result()
  → Returns detailed JSON per step

GitHub Actions (09:00 CST daily)
  → POST /api/v1/admin/daily-digest?secret=XXX
      → Query DB for latest data
      → NotificationService.send_daily_digest()
```

### New Environment Variables

| Variable | Where to set |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Render env + GitHub Secrets |
| `TELEGRAM_CHAT_ID` | Render env + GitHub Secrets |

---

## Component: NotificationService

**File**: `backend/app/services/notification.py`

### Functions

```python
async def send_message(text: str) -> None
# Base send. All other functions call this.
# Silently logs warning on failure — never raises.

async def send_job_result(job: str, steps: list[dict], got_date, expected_date) -> None
# Called at end of every trigger job (success or failure).

async def send_daily_digest(db: Session) -> None
# Called by /admin/daily-digest endpoint.
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
✗ fetch_options_data — FinMind 配額已用盡
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

Replace silent `return` on API failures with `raise RuntimeError(...)`:

| Function | Current | New |
|----------|---------|-----|
| `fetch_institutional_stocks` | prints + returns None if `stat != "OK"` | raises `RuntimeError(f"TWSE T86 stat={stat}")` |
| `fetch_institutional_market` | prints + returns None if `stat != "OK"` | raises `RuntimeError(f"TWSE BFI82U stat={stat}")` |
| `fetch_margin` | prints + returns None if `stat != "OK"` | raises `RuntimeError(f"TWSE MI_MARGN stat={stat}")` |
| `fetch_futures_oi` | prints + returns None if no data | raises `RuntimeError("FinMind 近 5 日查無期貨OI數據")` |
| `fetch_options_data` | prints + returns None if no data | raises `RuntimeError("FinMind 近 5 日查無選擇權數據")` |

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
    "status": "ok" | "error",
    "duration_s": float,
    "rows": int | None,    # where applicable
    "error": str | None,
    "date": str | None,
})
```

### Status Logic

| Condition | Returned status |
|-----------|----------------|
| All functions succeed | `"ok"` |
| Some functions fail | `"partial_error"` |
| All functions fail | `"error"` |

### New Endpoint

```
POST /api/v1/admin/daily-digest?secret=XXX
```

Queries `daily_chips` and `daily_options` for the latest trading day, then calls `send_daily_digest()`.

---

## Component: GitHub Actions Changes

### daily-fetch.yml

1. **Exit 1 on real errors**: if final STATUS is `"error"` after all retries, exit 1 (enables GitHub email + marks run as failed)
2. **New `daily-digest` job**: cron `0 1 * * 1-5` (UTC 01:00 = CST 09:00), calls `/admin/daily-digest`

```yaml
- cron: '0 1 * * 1-5'   # 09:00 CST — daily digest
```

---

## Out of Scope

- `stock_prices` and `broker_daily` fetching (on-demand, not daily cron)
- Backup API sources (separate concern)
- Frontend error display
