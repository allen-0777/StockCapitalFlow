"""
Admin trigger endpoint — 供 GitHub Actions 排程呼叫，取代 APScheduler。
POST /api/v1/admin/trigger/{job}?secret=XXX  → 立即回傳，背景執行
GET  /api/v1/admin/job-status/{job}?secret=XXX → polling 查詢結果
POST /api/v1/admin/daily-digest?secret=XXX
"""
import asyncio
import os
import time
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text

from app.services import fetcher as _fetcher
from app.services.trading_calendar import is_trading_day, latest_trading_day
from app.models.database import cache_clear, get_db, SessionLocal
from app.services.notification import (
    STEP_OK,
    STEP_ERROR,
    JOB_OK,
    JOB_PARTIAL,
    JOB_ERROR,
    send_job_result,
    send_daily_digest,
)

router = APIRouter()

# 存函式名稱，執行時 getattr(_fetcher, name)，便於測試 patch fetcher 模組
JOB_STEPS: dict[str, tuple[str, ...]] = {
    "institutional": ("fetch_institutional_market", "fetch_institutional_stocks", "fetch_turnover"),
    "futures": ("fetch_futures_oi", "fetch_options_data"),
    "margin": ("fetch_margin", "fetch_exchange_rate"),
}

# 每個 job 對應要檢查的欄位（stock_id='0000'），若已有值代表資料已抓過
JOB_CHECK_COL: dict[str, str] = {
    "institutional": "foreign_buy",
    "futures": "tx_foreign_long",
    "margin": "margin_long",
}

# In-memory job status store (process-level, resets on deploy)
_job_results: dict[str, dict] = {}


def _job_already_done(job: str, expected) -> bool:
    """檢查 DB 裡是否已有當天資料，有的話就不用重抓"""
    col = JOB_CHECK_COL.get(job)
    if not col:
        return False
    with SessionLocal() as db:
        row = db.execute(
            sa_text(f"SELECT {col} FROM daily_chips WHERE date=:d AND stock_id='0000'"),
            {"d": expected}
        ).fetchone()
        if row is None or row[0] is None:
            return False
        if job == "futures":
            opt = db.execute(
                sa_text("SELECT date FROM daily_options WHERE date=:d"),
                {"d": expected}
            ).fetchone()
            if opt is None:
                return False
        return True


def _summarize_job_status(steps: list[dict]) -> str:
    n_ok = sum(1 for s in steps if s.get("status") == STEP_OK)
    n_err = sum(1 for s in steps if s.get("status") == STEP_ERROR)
    if n_err == 0:
        return JOB_OK
    if n_ok == 0:
        return JOB_ERROR
    return JOB_PARTIAL


async def _run_job(job: str, notify: bool):
    """背景執行 job，結果存到 _job_results"""
    expected = latest_trading_day()
    steps: list[dict] = []
    got_date = None

    for fn_name in JOB_STEPS[job]:
        fn = getattr(_fetcher, fn_name)
        t0 = time.monotonic()
        step: dict = {
            "fn": fn_name,
            "status": None,
            "duration_s": None,
            "error": None,
            "date": None,
        }
        try:
            result = await fn()
            step["status"] = STEP_OK
            step["duration_s"] = round(time.monotonic() - t0, 1)
            if result is not None:
                step["date"] = str(result)
                got_date = result
        except Exception as e:
            step["status"] = STEP_ERROR
            step["duration_s"] = round(time.monotonic() - t0, 1)
            step["error"] = str(e)
        steps.append(step)

    job_status = _summarize_job_status(steps)
    date_match = got_date == expected if got_date else False
    cache_clear()

    result = {
        "status": job_status,
        "job": job,
        "expected_date": str(expected),
        "got_date": str(got_date) if got_date else None,
        "date_match": date_match,
        "steps": steps,
    }
    _job_results[job] = result

    if notify:
        try:
            await send_job_result(job, steps, got_date, expected)
        except Exception as e:
            print(f"[admin] notify error: {e}")

    print(f"[admin] {job} finished: {job_status} date_match={date_match}")


@router.post("/api/v1/admin/trigger/{job}")
async def trigger_job(job: str, secret: str = "", notify: bool = False, force: bool = False):
    expected_secret = os.getenv("TRIGGER_SECRET", "")
    if not expected_secret or secret != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid secret")

    if job not in JOB_STEPS:
        raise HTTPException(status_code=404, detail=f"Unknown job: {job}. Valid: {list(JOB_STEPS)}")

    if not is_trading_day():
        return {"status": "skipped", "reason": "非台股交易日"}

    expected = latest_trading_day()

    # 若資料已存在，直接回傳成功（除非 force=true）
    if not force and _job_already_done(job, expected):
        print(f"[admin] {job} already done for {expected}, skipping")
        result = {
            "status": JOB_OK,
            "job": job,
            "expected_date": str(expected),
            "got_date": str(expected),
            "date_match": True,
            "steps": [{"fn": "cache_hit", "status": STEP_OK, "duration_s": 0}],
            "cached": True,
        }
        _job_results[job] = result
        return result

    # 非同步背景執行，立即回傳 accepted
    _job_results[job] = {"status": "running", "job": job, "expected_date": str(expected)}
    asyncio.create_task(_run_job(job, notify))

    return {"status": "accepted", "job": job, "expected_date": str(expected)}


@router.get("/api/v1/admin/job-status/{job}")
async def job_status(job: str, secret: str = ""):
    """Polling endpoint — workflow 用來查背景 job 是否完成"""
    expected_secret = os.getenv("TRIGGER_SECRET", "")
    if not expected_secret or secret != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid secret")

    if job not in JOB_STEPS:
        raise HTTPException(status_code=404, detail=f"Unknown job: {job}")

    result = _job_results.get(job)
    if not result:
        return {"status": "unknown", "job": job}
    return result


@router.post("/api/v1/admin/daily-digest")
async def daily_digest(secret: str = "", db: Session = Depends(get_db)):
    """每日彙整推播（含假日）；由 GitHub Actions 另排程觸發。"""
    expected_secret = os.getenv("TRIGGER_SECRET", "")
    if not expected_secret or secret != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid secret")

    await send_daily_digest(db)
    return {"status": "ok"}
