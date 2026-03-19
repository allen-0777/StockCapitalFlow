"""
Admin trigger endpoint — 供 GitHub Actions 排程呼叫，取代 APScheduler。
POST /api/v1/admin/trigger/{job}?secret=XXX
"""
import os
from fastapi import APIRouter, HTTPException
from app.services.fetcher import (
    fetch_institutional_market,
    fetch_institutional_stocks,
    fetch_margin,
    fetch_futures_oi,
    fetch_options_data,
)
from app.services.trading_calendar import is_trading_day, latest_trading_day
from app.models.database import cache_clear

router = APIRouter()

JOBS = {
    "institutional": [fetch_institutional_market, fetch_institutional_stocks],
    "futures":       [fetch_futures_oi, fetch_options_data],
    "margin":        [fetch_margin],
}


@router.post("/api/v1/admin/trigger/{job}")
async def trigger_job(job: str, secret: str = ""):
    expected_secret = os.getenv("TRIGGER_SECRET", "")
    if not expected_secret or secret != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid secret")

    if job not in JOBS:
        raise HTTPException(status_code=404, detail=f"Unknown job: {job}. Valid: {list(JOBS)}")

    if not is_trading_day():
        return {"status": "skipped", "reason": "非台股交易日"}

    expected = latest_trading_day()
    steps = []
    got_date = None

    for fn in JOBS[job]:
        result = await fn()
        steps.append({"fn": fn.__name__, "date": str(result)})
        if result is not None:
            got_date = result

    cache_clear()

    return {
        "status": "ok",
        "job": job,
        "expected_date": str(expected),
        "got_date": str(got_date),
        "date_match": got_date == expected,
        "steps": steps,
    }
