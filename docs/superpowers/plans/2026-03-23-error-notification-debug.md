# Error Notification & Debug Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Telegram notifications (per-job results + daily digest) and improve error surfacing in the fetch pipeline so failures are visible instead of silent.

**Architecture:** New `notification.py` service handles all Telegram messaging. `fetcher.py` raises exceptions instead of silently returning on API failures. `admin.py` catches per-function errors and returns structured step details. Notifications fire only on final attempts (not each retry) via a `notify: bool` param. A new `/admin/daily-digest` endpoint and GitHub Actions cron sends the morning digest.

**Tech Stack:** Python 3.14, FastAPI, aiohttp (Telegram HTTP), pytest + pytest-asyncio (tests), GitHub Actions

**Spec:** `docs/superpowers/specs/2026-03-23-error-notification-debug-design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `backend/app/services/notification.py` | All Telegram messaging logic |
| Create | `backend/tests/__init__.py` | Test package |
| Create | `backend/tests/test_notification.py` | Tests for NotificationService |
| Create | `backend/tests/test_fetcher_errors.py` | Tests for fetcher error raising |
| Create | `backend/tests/test_admin.py` | Tests for admin error capture + daily-digest |
| Modify | `backend/app/services/fetcher.py` | Raise on API failures, add timing logs |
| Modify | `backend/app/api/admin.py` | Per-step error capture, notify on final attempt, new endpoint |
| Modify | `backend/requirements.txt` | Add pytest, pytest-asyncio |
| Modify | `.github/workflows/daily-fetch.yml` | Exit 1 on errors, notify=true on final, add daily-digest job |

---

## Task 1: Test Infrastructure

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/tests/__init__.py`
- Create: `backend/pytest.ini`

- [ ] **Step 1: Add test dependencies**

In `backend/requirements.txt`, append:
```
pytest
pytest-asyncio
```

- [ ] **Step 2: Create test package and config**

Create `backend/tests/__init__.py` (empty file).

Create `backend/pytest.ini`:
```ini
[pytest]
asyncio_mode = auto
```

- [ ] **Step 3: Install and verify**

```bash
cd backend && .venv/bin/pip install pytest pytest-asyncio && .venv/bin/pytest --collect-only
```
Expected: "no tests ran" with 0 errors.

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt backend/tests/__init__.py backend/pytest.ini
git commit -m "chore: add pytest + pytest-asyncio test infrastructure"
```

---

## Task 2: NotificationService

**Files:**
- Create: `backend/app/services/notification.py`
- Create: `backend/tests/test_notification.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_notification.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock, call
from datetime import date
import os

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123456")


def _mock_telegram_session(status=200):
    """Helper: mock aiohttp.ClientSession for Telegram POST."""
    mock_resp = MagicMock()
    mock_resp.status = status
    mock_resp.text = AsyncMock(return_value="ok")
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


@pytest.mark.asyncio
async def test_send_message_posts_to_telegram():
    """send_message should POST to Telegram sendMessage API."""
    from app.services.notification import send_message

    mock_session = _mock_telegram_session()
    with patch("aiohttp.ClientSession", return_value=mock_session):
        await send_message("hello")

    mock_session.post.assert_called_once()
    url = mock_session.post.call_args[0][0]
    assert "sendMessage" in url
    assert "test-token" in url


@pytest.mark.asyncio
async def test_send_message_truncates_at_4096():
    """send_message must truncate text to 4096 chars before sending."""
    from app.services.notification import send_message

    captured = []

    async def fake_post(url, **kwargs):
        captured.append(kwargs["json"]["text"])
        resp = MagicMock()
        resp.status = 200
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        return resp

    mock_session = MagicMock()
    mock_session.post = fake_post
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        await send_message("x" * 5000)

    assert len(captured) == 1
    assert len(captured[0]) <= 4096


@pytest.mark.asyncio
async def test_send_message_does_not_raise_on_network_error():
    """send_message must swallow exceptions and never raise."""
    from app.services.notification import send_message

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.post = MagicMock(side_effect=Exception("network error"))

    with patch("aiohttp.ClientSession", return_value=mock_session):
        await send_message("hello")  # must not raise


@pytest.mark.asyncio
async def test_send_job_result_success_contains_checkmark():
    """Success result should contain checkmark emoji and job name."""
    from app.services.notification import send_job_result

    sent = []
    with patch("app.services.notification.send_message", new=AsyncMock(side_effect=lambda t: sent.append(t))):
        await send_job_result(
            job="institutional",
            steps=[{
                "fn": "fetch_institutional_market",
                "status": "ok",
                "duration_s": 1.2,
                "rows": None,
                "error": None,
                "date": "2026-03-21",
            }],
            got_date=date(2026, 3, 21),
            expected_date=date(2026, 3, 21),
        )

    assert len(sent) == 1
    assert "✅" in sent[0]
    assert "institutional" in sent[0]


@pytest.mark.asyncio
async def test_send_job_result_partial_error_shows_warning_and_error_text():
    """Partial failure should show warning emoji and the error message."""
    from app.services.notification import send_job_result

    sent = []
    with patch("app.services.notification.send_message", new=AsyncMock(side_effect=lambda t: sent.append(t))):
        await send_job_result(
            job="futures",
            steps=[
                {"fn": "fetch_futures_oi", "status": "ok", "duration_s": 2.1, "rows": None, "error": None, "date": "2026-03-21"},
                {"fn": "fetch_options_data", "status": "error", "duration_s": 1.0, "rows": None, "error": "FinMind 配額已用盡", "date": None},
            ],
            got_date=date(2026, 3, 21),
            expected_date=date(2026, 3, 21),
        )

    assert len(sent) == 1
    assert "⚠️" in sent[0]
    assert "FinMind 配額已用盡" in sent[0]


@pytest.mark.asyncio
async def test_send_daily_digest_queries_db_and_sends_message():
    """send_daily_digest should query daily_chips and send a formatted message."""
    from app.services.notification import send_daily_digest
    from unittest.mock import MagicMock

    mock_db = MagicMock()
    # Simulate daily_chips row: (date, foreign_buy, trust_buy, dealer_buy,
    #   margin_long, margin_short, tx_foreign_long, tx_foreign_short,
    #   trust_tx_long, trust_tx_short)
    mock_db.execute.return_value.fetchone.side_effect = [
        ("2026-03-21", 12.3, -2.1, 0.8, 230000, -1200, 15234, 12100, 500, 300),
        None,  # no options row
    ]

    sent = []
    with patch("app.services.notification.send_message", new=AsyncMock(side_effect=lambda t: sent.append(t))):
        await send_daily_digest(mock_db)

    assert len(sent) == 1
    assert "2026-03-21" in sent[0]
    assert "法人" in sent[0]


@pytest.mark.asyncio
async def test_send_daily_digest_sends_fallback_when_no_data():
    """send_daily_digest should send a fallback message when DB is empty."""
    from app.services.notification import send_daily_digest

    mock_db = MagicMock()
    mock_db.execute.return_value.fetchone.return_value = None

    sent = []
    with patch("app.services.notification.send_message", new=AsyncMock(side_effect=lambda t: sent.append(t))):
        await send_daily_digest(mock_db)

    assert len(sent) == 1
    assert "資料庫尚無資料" in sent[0]
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && .venv/bin/pytest tests/test_notification.py -v
```
Expected: `ImportError` — notification.py doesn't exist yet.

- [ ] **Step 3: Create `notification.py`**

Create `backend/app/services/notification.py`:

```python
import os
import logging
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

# Status constants — imported by admin.py to avoid string literals
STEP_OK = "ok"
STEP_ERROR = "error"
JOB_OK = "ok"
JOB_PARTIAL = "partial_error"
JOB_ERROR = "error"


def _token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


def _chat_id() -> str:
    return os.getenv("TELEGRAM_CHAT_ID", "")


async def send_message(text: str) -> None:
    """Send a Telegram message. Truncates at 4096 chars. Never raises."""
    token = _token()
    chat_id = _chat_id()
    if not token or not chat_id:
        logger.warning("[notification] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set, skipping")
        return

    text = text[:4096]
    url = TELEGRAM_API.format(token=token)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning(f"[notification] Telegram returned {resp.status}: {body[:200]}")
    except Exception as e:
        logger.warning(f"[notification] Failed to send Telegram message: {e}")


async def send_job_result(
    job: str,
    steps: list[dict],
    got_date,
    expected_date,
) -> None:
    """Send job result summary to Telegram. Call once after all retries."""
    has_error = any(s.get("status") == STEP_ERROR for s in steps)
    all_error = all(s.get("status") == STEP_ERROR for s in steps)

    if all_error:
        emoji, label = "❌", "失敗"
    elif has_error:
        emoji, label = "⚠️", "部分失敗"
    else:
        emoji, label = "✅", "完成"

    date_str = str(got_date) if got_date else str(expected_date)
    lines = [f"{emoji} <b>{job}</b> {label} ({date_str})"]

    for s in steps:
        fn = s.get("fn", "")
        status = s.get("status", "")
        duration = s.get("duration_s")
        error = s.get("error")
        rows = s.get("rows")

        if status == STEP_OK:
            parts = []
            if rows:
                parts.append(f"{rows:,} 筆")
            if duration is not None:
                parts.append(f"{duration:.1f}s")
            detail = " | ".join(parts)
            lines.append(f"✓ {fn} — {detail}")
        else:
            lines.append(f"✗ {fn} — {error or '未知錯誤'}")

    if got_date and expected_date and got_date != expected_date:
        lines.append(f"<i>日期不符: 預期 {expected_date}, 實際 {got_date}</i>")

    await send_message("\n".join(lines))


async def send_daily_digest(db: Session) -> None:
    """Send daily digest with latest available data. Works on holidays."""
    chip_row = db.execute(
        text("""
            SELECT date, foreign_buy, trust_buy, dealer_buy,
                   margin_long, margin_short,
                   tx_foreign_long, tx_foreign_short,
                   trust_tx_long, trust_tx_short
            FROM daily_chips
            WHERE stock_id = '0000'
            ORDER BY date DESC LIMIT 1
        """)
    ).fetchone()

    if not chip_row:
        await send_message("📊 每日彙整：資料庫尚無資料")
        return

    opt_row = db.execute(
        text("""
            SELECT date, pc_ratio, call_max_strike, put_max_strike,
                   foreign_call_net_yi, foreign_put_net_yi
            FROM daily_options
            ORDER BY date DESC LIMIT 1
        """)
    ).fetchone()

    d = chip_row[0]
    foreign = chip_row[1] or 0
    trust = chip_row[2] or 0
    dealer = chip_row[3] or 0
    margin_long_kth = chip_row[4] or 0
    margin_short = chip_row[5] or 0
    tx_fl = chip_row[6] or 0
    tx_fs = chip_row[7] or 0

    margin_long_yi = round(margin_long_kth / 100000, 2)
    tx_net = tx_fl - tx_fs

    def sign(v: float) -> str:
        return f"+{v:.1f}" if v >= 0 else f"{v:.1f}"

    lines = [
        f"📊 <b>每日彙整 {d}</b>",
        f"法人: 外資 {sign(foreign)}億 | 投信 {sign(trust)}億 | 自營 {sign(dealer)}億",
        f"融資: {sign(margin_long_yi)}億 | 融券: {margin_short:+,} 張",
        f"台指外資: 多 {tx_fl:,} 空 {tx_fs:,} 淨 {tx_net:+,}",
    ]

    if opt_row:
        pc = opt_row[1]
        call_s = opt_row[2]
        put_s = opt_row[3]
        lines.append(f"選擇權: P/C={pc}% | 壓力 {call_s} | 支撐 {put_s}")

    await send_message("\n".join(lines))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && .venv/bin/pytest tests/test_notification.py -v
```
Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/notification.py backend/tests/test_notification.py backend/pytest.ini backend/tests/__init__.py backend/requirements.txt
git commit -m "feat: add NotificationService (send_message, send_job_result, send_daily_digest)"
```

---

## Task 3: fetcher.py — Error Raising + Timing

**Files:**
- Modify: `backend/app/services/fetcher.py`
- Create: `backend/tests/test_fetcher_errors.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_fetcher_errors.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


def _mock_twse_get(json_body: dict):
    """Mock aiohttp.ClientSession for a TWSE GET response."""
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value=json_body)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


def _mock_finmind_get(json_body: dict):
    """Mock aiohttp.ClientSession for a FinMind GET response (empty data)."""
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=json_body)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


@pytest.mark.asyncio
async def test_fetch_institutional_market_raises_on_closed_stat():
    from app.services.fetcher import fetch_institutional_market
    body = {"stat": "CLOSED", "date": "20260321", "data": []}
    with patch("aiohttp.ClientSession", return_value=_mock_twse_get(body)):
        with pytest.raises(RuntimeError, match="TWSE BFI82U stat=CLOSED"):
            await fetch_institutional_market()


@pytest.mark.asyncio
async def test_fetch_institutional_stocks_raises_on_closed_stat():
    from app.services.fetcher import fetch_institutional_stocks
    body = {"stat": "CLOSED", "date": "20260321", "data": []}
    with patch("aiohttp.ClientSession", return_value=_mock_twse_get(body)):
        with pytest.raises(RuntimeError, match="TWSE T86 stat=CLOSED"):
            await fetch_institutional_stocks()


@pytest.mark.asyncio
async def test_fetch_margin_raises_on_closed_stat():
    from app.services.fetcher import fetch_margin
    body = {"stat": "CLOSED", "date": "20260321", "tables": []}
    with patch("aiohttp.ClientSession", return_value=_mock_twse_get(body)):
        with pytest.raises(RuntimeError, match="TWSE MI_MARGN stat=CLOSED"):
            await fetch_margin()


@pytest.mark.asyncio
async def test_fetch_futures_oi_raises_when_no_data_in_5_days():
    from app.services.fetcher import fetch_futures_oi
    empty = {"data": []}
    with patch("aiohttp.ClientSession", return_value=_mock_finmind_get(empty)):
        with pytest.raises(RuntimeError, match="近 5 日查無期貨OI數據"):
            await fetch_futures_oi()


@pytest.mark.asyncio
async def test_fetch_options_data_raises_when_no_data_in_5_days():
    from app.services.fetcher import fetch_options_data
    empty = {"data": []}
    with patch("aiohttp.ClientSession", return_value=_mock_finmind_get(empty)):
        with pytest.raises(RuntimeError, match="近 5 日查無選擇權數據"):
            await fetch_options_data()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && .venv/bin/pytest tests/test_fetcher_errors.py -v
```
Expected: All 5 tests FAIL (functions return None instead of raising).

- [ ] **Step 3: Update `fetcher.py` — error raising**

Add `import time` at the top of `backend/app/services/fetcher.py` (after existing imports).

Make the following targeted replacements:

**In `fetch_institutional_market`**: replace the `stat != "OK"` block:
```python
    if data.get("stat") != "OK":
        print(f"[fetcher] BFI82U stat={data.get('stat')}, skipping")
        return
```
→
```python
    if data.get("stat") != "OK":
        raise RuntimeError(f"TWSE BFI82U stat={data.get('stat')}")
```

**In `fetch_institutional_stocks`**: replace:
```python
    if data.get("stat") != "OK":
        print(f"[fetcher] T86 stat={data.get('stat')}, skipping")
        return
```
→
```python
    if data.get("stat") != "OK":
        raise RuntimeError(f"TWSE T86 stat={data.get('stat')}")
```

**In `fetch_margin`**: replace:
```python
    if data.get("stat") != "OK":
        print(f"[fetcher] MI_MARGN stat={data.get('stat')}, skipping")
        return
```
→
```python
    if data.get("stat") != "OK":
        raise RuntimeError(f"TWSE MI_MARGN stat={data.get('stat')}")
```

**In `fetch_futures_oi`**: replace:
```python
    if not trade_date:
        print("[fetcher] 期貨OI: FinMind 近 5 日查無數據，跳過寫入")
        return
```
→
```python
    if not trade_date:
        raise RuntimeError("FinMind 近 5 日查無期貨OI數據")
```

**In `fetch_options_data`**: replace:
```python
    if not trade_date:
        print("[fetcher] 選擇權: 查無近期數據，跳過")
        return
```
→
```python
    if not trade_date:
        raise RuntimeError("FinMind 近 5 日查無選擇權數據")
```

- [ ] **Step 4: Update `fetcher.py` — timing logs**

Wrap each `async def fetch_*` function body with timing using this exact pattern. Apply to all 5 functions:

**`fetch_institutional_market`** — add `t0 = time.monotonic()` at function start, and replace the final `return trading_date` and surrounding print with:
```python
    elapsed = round(time.monotonic() - t0, 1)
    print(f"[fetcher][institutional_market] done in {elapsed}s ({trading_date}): 外資={foreign_buy:.2f}億 投信={trust_buy:.2f}億 自營={dealer_buy:.2f}億")
    return trading_date
```
Add error timing by wrapping the function body in try/except:
```python
async def fetch_institutional_market():
    """抓大盤三大法人買賣超 → stock_id='0000'"""
    t0 = time.monotonic()
    try:
        # ... existing body (with raise replacing return on bad stat) ...
        elapsed = round(time.monotonic() - t0, 1)
        print(f"[fetcher][institutional_market] done in {elapsed}s ({trading_date})")
        return trading_date
    except Exception:
        elapsed = round(time.monotonic() - t0, 1)
        print(f"[fetcher][institutional_market] ERROR in {elapsed}s")
        raise
```

**`fetch_institutional_stocks`** — log includes row count:
```python
async def fetch_institutional_stocks():
    """抓個股三大法人買賣超（bulk upsert）"""
    t0 = time.monotonic()
    try:
        # ... existing body ...
        elapsed = round(time.monotonic() - t0, 1)
        print(f"[fetcher][institutional_stocks] {len(rows_data):,} 筆 in {elapsed}s ({trading_date})")
        return trading_date
    except Exception:
        elapsed = round(time.monotonic() - t0, 1)
        print(f"[fetcher][institutional_stocks] ERROR in {elapsed}s")
        raise
```

Apply the same `t0 / try / except / raise` wrapper to:
- `fetch_margin` → log name `margin`
- `fetch_futures_oi` → log name `futures_oi`
- `fetch_options_data` → log name `options_data`

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && .venv/bin/pytest tests/test_fetcher_errors.py -v
```
Expected: All 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/fetcher.py backend/tests/test_fetcher_errors.py
git commit -m "fix: raise RuntimeError on TWSE/FinMind API failures, add timing logs to all fetchers"
```

---

## Task 4: admin.py — Error Capture, `notify` Param, Daily Digest Endpoint

**Files:**
- Modify: `backend/app/api/admin.py`
- Create: `backend/tests/test_admin.py`

**Note:** `cache_clear` is already defined in `app.models.database` (line 24) — no change needed to that import.

**Design note on notifications:** The trigger endpoint accepts a `notify: bool = False` query param. GitHub Actions passes `notify=true` only on success (immediately) or on the final retry (whether success or failure). This ensures one notification per job execution, not one per retry attempt.

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_admin.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
import os
import datetime

os.environ.setdefault("TRIGGER_SECRET", "test-secret")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123456")

TODAY = datetime.date(2026, 3, 21)


def _client():
    from app.main import app
    return TestClient(app)


def test_trigger_response_includes_step_duration():
    """Response steps must include duration_s field."""
    async def fake_fn():
        return TODAY

    with patch("app.api.admin.JOBS", {"institutional": [fake_fn]}), \
         patch("app.api.admin.is_trading_day", return_value=True), \
         patch("app.api.admin.latest_trading_day", return_value=TODAY), \
         patch("app.api.admin.send_job_result", new=AsyncMock()):
        resp = _client().post("/api/v1/admin/trigger/institutional?secret=test-secret")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "duration_s" in data["steps"][0]
    assert data["steps"][0]["status"] == "ok"


def test_trigger_returns_partial_error_on_one_step_failure():
    """When one step fails, status must be partial_error."""
    async def ok_fn():
        return TODAY

    async def fail_fn():
        raise RuntimeError("FinMind 配額已用盡")

    with patch("app.api.admin.JOBS", {"futures": [ok_fn, fail_fn]}), \
         patch("app.api.admin.is_trading_day", return_value=True), \
         patch("app.api.admin.latest_trading_day", return_value=TODAY), \
         patch("app.api.admin.send_job_result", new=AsyncMock()):
        resp = _client().post("/api/v1/admin/trigger/futures?secret=test-secret")

    data = resp.json()
    assert data["status"] == "partial_error"
    failed = [s for s in data["steps"] if s["status"] == "error"]
    assert len(failed) == 1
    assert "FinMind 配額已用盡" in failed[0]["error"]


def test_trigger_returns_error_when_all_steps_fail():
    """When all steps fail, status must be error."""
    async def fail_fn():
        raise RuntimeError("TWSE T86 stat=CLOSED")

    with patch("app.api.admin.JOBS", {"institutional": [fail_fn]}), \
         patch("app.api.admin.is_trading_day", return_value=True), \
         patch("app.api.admin.latest_trading_day", return_value=TODAY), \
         patch("app.api.admin.send_job_result", new=AsyncMock()):
        resp = _client().post("/api/v1/admin/trigger/institutional?secret=test-secret")

    assert resp.json()["status"] == "error"


def test_trigger_calls_send_job_result_when_notify_true():
    """send_job_result should be called when notify=true."""
    async def fake_fn():
        return TODAY

    mock_notify = AsyncMock()
    with patch("app.api.admin.JOBS", {"institutional": [fake_fn]}), \
         patch("app.api.admin.is_trading_day", return_value=True), \
         patch("app.api.admin.latest_trading_day", return_value=TODAY), \
         patch("app.api.admin.send_job_result", new=mock_notify):
        _client().post("/api/v1/admin/trigger/institutional?secret=test-secret&notify=true")

    mock_notify.assert_called_once()


def test_trigger_does_not_call_send_job_result_when_notify_false():
    """send_job_result should NOT be called when notify=false (default)."""
    async def fake_fn():
        return TODAY

    mock_notify = AsyncMock()
    with patch("app.api.admin.JOBS", {"institutional": [fake_fn]}), \
         patch("app.api.admin.is_trading_day", return_value=True), \
         patch("app.api.admin.latest_trading_day", return_value=TODAY), \
         patch("app.api.admin.send_job_result", new=mock_notify):
        _client().post("/api/v1/admin/trigger/institutional?secret=test-secret")

    mock_notify.assert_not_called()


def test_daily_digest_returns_ok_with_date():
    """daily-digest should return status=ok and a date field."""
    with patch("app.api.admin.send_daily_digest", new=AsyncMock()), \
         patch("app.api.admin.SessionLocal"):
        resp = _client().post("/api/v1/admin/daily-digest?secret=test-secret")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "date" in data


def test_daily_digest_rejects_wrong_secret():
    """daily-digest must return 403 on wrong secret."""
    resp = _client().post("/api/v1/admin/daily-digest?secret=wrong")
    assert resp.status_code == 403
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && .venv/bin/pytest tests/test_admin.py -v
```
Expected: Tests fail — missing `duration_s`, missing `partial_error`, missing `notify` param, missing `daily-digest` endpoint.

- [ ] **Step 3: Rewrite `admin.py`**

Replace the full content of `backend/app/api/admin.py`:

```python
"""
Admin trigger endpoint — 供 GitHub Actions 排程呼叫。
POST /api/v1/admin/trigger/{job}?secret=XXX&notify=false
POST /api/v1/admin/daily-digest?secret=XXX
"""
import os
import time
from datetime import date
from fastapi import APIRouter, HTTPException
from app.services.fetcher import (
    fetch_institutional_market,
    fetch_institutional_stocks,
    fetch_margin,
    fetch_futures_oi,
    fetch_options_data,
)
from app.services.notification import (
    send_job_result, send_daily_digest,
    STEP_OK, STEP_ERROR, JOB_OK, JOB_PARTIAL, JOB_ERROR,
)
from app.services.trading_calendar import is_trading_day, latest_trading_day
from app.models.database import SessionLocal, cache_clear

router = APIRouter()

JOBS = {
    "institutional": [fetch_institutional_market, fetch_institutional_stocks],
    "futures":       [fetch_futures_oi, fetch_options_data],
    "margin":        [fetch_margin],
}


def _check_secret(secret: str):
    expected = os.getenv("TRIGGER_SECRET", "")
    if not expected or secret != expected:
        raise HTTPException(status_code=403, detail="Invalid secret")


@router.post("/api/v1/admin/trigger/{job}")
async def trigger_job(job: str, secret: str = "", notify: bool = False):
    """
    Run a named fetch job and return per-step details.
    Pass notify=true to send a Telegram notification after completion.
    GitHub Actions should pass notify=true only on the final retry or on success.
    """
    _check_secret(secret)

    if job not in JOBS:
        raise HTTPException(status_code=404, detail=f"Unknown job: {job}. Valid: {list(JOBS)}")

    if not is_trading_day():
        return {"status": "skipped", "reason": "非台股交易日"}

    expected = latest_trading_day()
    steps = []
    got_date = None

    for fn in JOBS[job]:
        t0 = time.monotonic()
        try:
            result = await fn()
            duration = round(time.monotonic() - t0, 2)
            steps.append({
                "fn": fn.__name__,
                "status": STEP_OK,
                "duration_s": duration,
                "rows": None,
                "error": None,
                "date": str(result) if result else None,
            })
            if result is not None:
                got_date = result
        except Exception as e:
            duration = round(time.monotonic() - t0, 2)
            steps.append({
                "fn": fn.__name__,
                "status": STEP_ERROR,
                "duration_s": duration,
                "rows": None,
                "error": str(e),
                "date": None,
            })

    cache_clear()

    has_error = any(s["status"] == STEP_ERROR for s in steps)
    all_error = all(s["status"] == STEP_ERROR for s in steps)
    if all_error:
        overall = JOB_ERROR
    elif has_error:
        overall = JOB_PARTIAL
    else:
        overall = JOB_OK

    if notify:
        await send_job_result(job, steps, got_date, expected)

    return {
        "status": overall,
        "job": job,
        "expected_date": str(expected),
        "got_date": str(got_date),
        "date_match": got_date == expected,
        "steps": steps,
    }


@router.post("/api/v1/admin/daily-digest")
async def daily_digest(secret: str = ""):
    _check_secret(secret)
    digest_date = None
    with SessionLocal() as db:
        await send_daily_digest(db)
        row = db.execute(
            __import__("sqlalchemy").text(
                "SELECT date FROM daily_chips WHERE stock_id='0000' ORDER BY date DESC LIMIT 1"
            )
        ).fetchone()
        if row:
            digest_date = str(row[0])
    return {"status": "ok", "date": digest_date}
```

- [ ] **Step 4: Fix the `__import__` style in daily_digest**

The `__import__("sqlalchemy").text(...)` in the endpoint above is awkward. Replace it with a proper import. Add `from sqlalchemy import text` to the imports at the top of `admin.py`, then simplify:

```python
from sqlalchemy import text

# In daily_digest():
        row = db.execute(
            text("SELECT date FROM daily_chips WHERE stock_id='0000' ORDER BY date DESC LIMIT 1")
        ).fetchone()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && .venv/bin/pytest tests/test_admin.py -v
```
Expected: All 7 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/admin.py backend/tests/test_admin.py
git commit -m "feat: add per-step error capture, notify param, and daily-digest endpoint in admin"
```

---

## Task 5: GitHub Actions — Exit 1 + `notify=true` + Daily Digest Job

**Files:**
- Modify: `.github/workflows/daily-fetch.yml`

- [ ] **Step 1: Update trigger loop to pass `notify=true` on final attempt**

In the "Trigger fetch with retry" step, update the curl call to include `&notify=false`, and on the final iteration pass `&notify=true`. Also exit 1 on error/partial_error statuses.

Replace the entire `run: |` block of "Trigger fetch with retry" with:

```bash
        run: |
          if [ "$JOB_NAME" = "all" ]; then
            JOBS="institutional futures margin"
          else
            JOBS="$JOB_NAME"
          fi

          for CURRENT_JOB in $JOBS; do
            echo "=== Triggering job: $CURRENT_JOB ==="
            MAX_RETRIES=3
            WAIT_SEC=180
            JOB_SUCCESS=false

            for i in $(seq 1 $MAX_RETRIES); do
              IS_FINAL="false"
              if [ $i -eq $MAX_RETRIES ]; then IS_FINAL="true"; fi

              echo "--- Attempt $i / $MAX_RETRIES (notify=$IS_FINAL) ---"
              RESPONSE=$(curl -s --max-time 300 -X POST \
                "$BACKEND_URL/api/v1/admin/trigger/$CURRENT_JOB?secret=$TRIGGER_SECRET&notify=$IS_FINAL") || RESPONSE="{}"
              echo "Response: $RESPONSE"

              STATUS=$(echo "$RESPONSE" | python3 -c \
                "import sys,json; d=json.load(sys.stdin); print(d.get('status','error'))" 2>/dev/null || echo "error")
              DATE_MATCH=$(echo "$RESPONSE" | python3 -c \
                "import sys,json; d=json.load(sys.stdin); print(d.get('date_match','false'))" 2>/dev/null || echo "false")

              if [ "$STATUS" = "skipped" ]; then
                echo "Today is not a trading day. Skipping."
                JOB_SUCCESS=true
                break
              fi

              if [ "$STATUS" = "error" ] || [ "$STATUS" = "partial_error" ]; then
                echo "Job reported errors: $STATUS"
                # notify=true was already sent if this is the final attempt
                break
              fi

              DATE_MATCH_LOWER=$(echo "$DATE_MATCH" | tr '[:upper:]' '[:lower:]')
              if [ "$STATUS" = "ok" ] && [ "$DATE_MATCH_LOWER" = "true" ]; then
                echo "Success! Data date matches expected."
                # If not the final attempt, send notify=true now for this success
                if [ "$IS_FINAL" = "false" ]; then
                  curl -s --max-time 30 -X POST \
                    "$BACKEND_URL/api/v1/admin/trigger/$CURRENT_JOB?secret=$TRIGGER_SECRET&notify=true" > /dev/null || true
                fi
                JOB_SUCCESS=true
                break
              fi

              if [ $i -lt $MAX_RETRIES ]; then
                echo "Data not yet updated. Waiting 3 minutes before retry..."
                sleep $WAIT_SEC
              fi
            done

            if [ "$JOB_SUCCESS" = "false" ]; then
              echo "=== FAILED: $CURRENT_JOB ==="
              exit 1
            fi

            echo "=== Done: $CURRENT_JOB ==="
          done

          exit 0
```

- [ ] **Step 2: Add daily-digest cron and job**

In `.github/workflows/daily-fetch.yml`, under `schedule:`, add:
```yaml
    - cron: '0 1 * * 1-5'    # 09:00 CST — daily digest
```

After the existing `fetch:` job (at the same indentation level), add:

```yaml
  daily-digest:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    if: github.event.schedule == '0 1 * * 1-5'
    steps:
      - name: Send daily digest
        env:
          BACKEND_URL: ${{ secrets.RENDER_BACKEND_URL }}
          TRIGGER_SECRET: ${{ secrets.TRIGGER_SECRET }}
        run: |
          curl -s --max-time 30 -X POST \
            "$BACKEND_URL/api/v1/admin/daily-digest?secret=$TRIGGER_SECRET" || true
          echo "Daily digest triggered."
```

Note: `|| true` on the curl ensures this job always exits 0 — a digest failure should not mark the run as failed.

- [ ] **Step 3: Update `fetch` job to skip on digest cron**

The existing `fetch` job must not run when the digest cron fires. Add a job-level `if:` condition to the `fetch` job:

```yaml
  fetch:
    runs-on: ubuntu-latest
    timeout-minutes: 90
    if: github.event.schedule != '0 1 * * 1-5'
```

- [ ] **Step 4: Verify YAML is valid**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/daily-fetch.yml'))" && echo "YAML OK"
```
Expected: `YAML OK`.

- [ ] **Step 5: Commit and push**

```bash
git add .github/workflows/daily-fetch.yml
git commit -m "feat: exit 1 on fetch errors, notify=true on final attempt, add daily-digest cron at 09:00 CST"
git push origin main
```

---

## Task 6: Configure Environment Variables (Manual)

- [ ] **Step 1: Create Telegram bot and get credentials**

1. Open Telegram → search `@BotFather` → `/newbot` → follow prompts → save `BOT_TOKEN`
2. Send any message to your new bot
3. Visit `https://api.telegram.org/bot<BOT_TOKEN>/getUpdates` in a browser
4. Find `"chat": {"id": <number>}` → save as `CHAT_ID`

- [ ] **Step 2: Set on Render**

Render dashboard → your backend service → Environment → Add:
- `TELEGRAM_BOT_TOKEN` = `<BOT_TOKEN>`
- `TELEGRAM_CHAT_ID` = `<CHAT_ID>`

Trigger a manual redeploy.

- [ ] **Step 3: End-to-end verification**

From GitHub Actions UI, trigger workflow manually with `job=all`. Check Telegram for:
- 3 messages (one per job: institutional / futures / margin)
- Each message shows job name, step results, timing
- No duplicate messages (notify fires once per job)

---

## Run All Tests

```bash
cd backend && .venv/bin/pytest tests/ -v
```
Expected: All tests pass (green).
