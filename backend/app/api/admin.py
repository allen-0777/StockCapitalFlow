"""
Admin trigger endpoint — 供 GitHub Actions 排程呼叫，取代 APScheduler。
POST /api/v1/admin/trigger/{job}?secret=XXX&notify=true
POST /api/v1/admin/daily-digest?secret=XXX
"""
import os
import time
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from app.services import fetcher as _fetcher
from app.services.trading_calendar import is_trading_day, latest_trading_day
from app.models.database import cache_clear, get_db
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
    "institutional": ("fetch_institutional_market", "fetch_institutional_stocks"),
    "futures": ("fetch_futures_oi", "fetch_options_data"),
    "margin": ("fetch_margin",),
}


def _summarize_job_status(steps: list[dict]) -> str:
    n_ok = sum(1 for s in steps if s.get("status") == STEP_OK)
    n_err = sum(1 for s in steps if s.get("status") == STEP_ERROR)
    if n_err == 0:
        return JOB_OK
    if n_ok == 0:
        return JOB_ERROR
    return JOB_PARTIAL


@router.post("/api/v1/admin/trigger/{job}")
async def trigger_job(job: str, secret: str = "", notify: bool = False):
    expected_secret = os.getenv("TRIGGER_SECRET", "")
    if not expected_secret or secret != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid secret")

    if job not in JOB_STEPS:
        raise HTTPException(status_code=404, detail=f"Unknown job: {job}. Valid: {list(JOB_STEPS)}")

    if not is_trading_day():
        return {"status": "skipped", "reason": "非台股交易日"}

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
            "rows": None,
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

    if notify:
        await send_job_result(job, steps, got_date, expected)

    return {
        "status": job_status,
        "job": job,
        "expected_date": str(expected),
        "got_date": str(got_date) if got_date else None,
        "date_match": date_match,
        "steps": steps,
    }


@router.post("/api/v1/admin/daily-digest")
async def daily_digest(secret: str = "", db: Session = Depends(get_db)):
    """每日彙整推播（含假日）；由 GitHub Actions 另排程觸發。"""
    expected_secret = os.getenv("TRIGGER_SECRET", "")
    if not expected_secret or secret != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid secret")

    await send_daily_digest(db)
    return {"status": "ok"}
