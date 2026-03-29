"""
Admin trigger endpoint — 供 GitHub Actions 排程呼叫，取代 APScheduler。
POST /api/v1/admin/trigger/all?secret=XXX  → 一次跑完三個 job（跳過已有資料的）
POST /api/v1/admin/trigger/{job}?secret=XXX  → 單獨跑某個 job
GET  /api/v1/admin/job-status/{job_or_all}?secret=XXX → polling 查詢結果
POST /api/v1/admin/daily-digest?secret=XXX

target_date（選填，YYYY-MM-DD）：
  用於「預期交易日」與 _job_already_done 比對。證交所／期交所公開 API 多數只回傳
  「最新一個已發布交易日」的資料，無法指定歷史日期重抓；此參數主要在「日曆已換日
  但 API 仍為昨日資料」時，將 expected 對齊該日以便 skip/force 判斷正確。
"""
import asyncio
import os
import time
from datetime import date
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text

from app.services import fetcher as _fetcher
from app.services.trading_calendar import is_trading_day
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

ALL_JOBS = ("institutional", "futures", "margin", "industry")

# 存函式名稱，執行時 getattr(_fetcher, name)，便於測試 patch fetcher 模組
JOB_STEPS: dict[str, tuple[str, ...]] = {
    "institutional": ("fetch_institutional_market", "fetch_institutional_stocks", "fetch_turnover"),
    "futures": ("fetch_futures_oi", "fetch_options_data"),
    "margin": ("fetch_margin", "fetch_exchange_rate"),
    "industry": ("sync_stock_industries", "sync_market_series_daily"),
}

# 每個 job 對應要檢查的欄位（stock_id='0000'），若已有值代表資料已抓過
JOB_CHECK_COL: dict[str, str] = {
    "institutional": "foreign_buy",
    "futures": "tx_foreign_long",
    "margin": "margin_long",
}

# In-memory job status store (process-level, resets on deploy)
_job_results: dict[str, dict] = {}


def _parse_expected_date(target_date: str) -> date:
    if not target_date or not str(target_date).strip():
        return date.today()
    try:
        return date.fromisoformat(str(target_date).strip())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid target_date; use YYYY-MM-DD",
        )


def _job_already_done(job: str, expected) -> bool:
    """檢查 DB 裡是否已有當天資料，有的話就不用重抓"""
    if job == "industry":
        with SessionLocal() as db:
            row = db.execute(
                sa_text(
                    "SELECT date FROM market_series_daily WHERE series_id='IDX:TAIEX' "
                    "ORDER BY date DESC LIMIT 1"
                )
            ).fetchone()
            if not row or row[0] is None:
                return False
            return str(row[0]) == str(expected)
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


async def _run_steps_for_job(job: str, expected) -> tuple[list[dict], object]:
    """執行單一 job 的所有 steps，回傳 (steps, got_date)"""
    steps = []
    got_date = None
    for fn_name in JOB_STEPS[job]:
        fn = getattr(_fetcher, fn_name)
        t0 = time.monotonic()
        step = {"job": job, "fn": fn_name, "status": None, "duration_s": None, "error": None, "date": None}
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
    return steps, got_date


async def _run_all_jobs(notify: bool, expected: date):
    """背景依序執行 ALL_JOBS，跳過已有資料的"""
    all_steps: list[dict] = []
    all_dates: dict[str, object] = {}
    t0_total = time.monotonic()

    for job in ALL_JOBS:
        if _job_already_done(job, expected):
            all_steps.append({"job": job, "fn": "cache_hit", "status": STEP_OK, "duration_s": 0})
            all_dates[job] = expected
            print(f"[admin:all] {job} already done, skipping")
            continue

        print(f"[admin:all] running {job}...")
        steps, got_date = await _run_steps_for_job(job, expected)
        all_steps.extend(steps)
        if got_date:
            all_dates[job] = got_date

    total_s = round(time.monotonic() - t0_total, 1)
    date_match = all(all_dates.get(j) == expected for j in ALL_JOBS)
    job_status = _summarize_job_status(all_steps)
    cache_clear()

    result = {
        "status": job_status,
        "job": "all",
        "expected_date": str(expected),
        "date_match": date_match,
        "duration_s": total_s,
        "steps": all_steps,
    }
    _job_results["all"] = result

    if notify:
        try:
            await send_job_result("all", all_steps, expected if date_match else None, expected)
        except Exception as e:
            print(f"[admin:all] notify error: {e}")

    print(f"[admin:all] finished in {total_s}s: {job_status} date_match={date_match}")


async def _run_job(job: str, notify: bool, expected: date):
    """背景執行單一 job，結果存到 _job_results"""
    steps, got_date = await _run_steps_for_job(job, expected)
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


# ── trigger/all ─────────────────────────────────────────────

@router.post("/api/v1/admin/trigger/all")
async def trigger_all(
    secret: str = "",
    notify: bool = False,
    force: bool = False,
    target_date: str = "",
):
    expected_secret = os.getenv("TRIGGER_SECRET", "")
    if not expected_secret or secret != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid secret")

    if not is_trading_day():
        return {"status": "skipped", "reason": "非台股交易日"}

    expected = _parse_expected_date(target_date)

    # 檢查哪些 job 需要跑
    jobs_to_run = []
    jobs_cached = []
    for job in ALL_JOBS:
        if not force and _job_already_done(job, expected):
            jobs_cached.append(job)
        else:
            jobs_to_run.append(job)

    if not jobs_to_run:
        result = {
            "status": JOB_OK,
            "job": "all",
            "expected_date": str(expected),
            "date_match": True,
            "jobs_cached": jobs_cached,
            "jobs_to_run": [],
            "cached": True,
        }
        _job_results["all"] = result
        return result

    # 背景執行
    _job_results["all"] = {
        "status": "running",
        "job": "all",
        "expected_date": str(expected),
        "jobs_cached": jobs_cached,
        "jobs_to_run": jobs_to_run,
    }
    asyncio.create_task(_run_all_jobs(notify, expected))

    return {
        "status": "accepted",
        "job": "all",
        "expected_date": str(expected),
        "jobs_cached": jobs_cached,
        "jobs_to_run": jobs_to_run,
    }


# ── trigger/{job} (single) ──────────────────────────────────

@router.post("/api/v1/admin/trigger/{job}")
async def trigger_job(
    job: str,
    secret: str = "",
    notify: bool = False,
    force: bool = False,
    target_date: str = "",
):
    expected_secret = os.getenv("TRIGGER_SECRET", "")
    if not expected_secret or secret != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid secret")

    if job not in JOB_STEPS:
        raise HTTPException(status_code=404, detail=f"Unknown job: {job}. Valid: {list(JOB_STEPS)}")

    if job != "industry" and not is_trading_day():
        return {"status": "skipped", "reason": "非台股交易日"}

    expected = _parse_expected_date(target_date)

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

    _job_results[job] = {"status": "running", "job": job, "expected_date": str(expected)}
    asyncio.create_task(_run_job(job, notify, expected))

    return {"status": "accepted", "job": job, "expected_date": str(expected)}


# ── job-status polling ───────────────────────────────────────

@router.get("/api/v1/admin/job-status/{job}")
async def job_status(job: str, secret: str = ""):
    """Polling endpoint — workflow 用來查背景 job 是否完成"""
    expected_secret = os.getenv("TRIGGER_SECRET", "")
    if not expected_secret or secret != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid secret")

    result = _job_results.get(job)
    if not result:
        return {"status": "unknown", "job": job}
    return result


# ── daily-digest ─────────────────────────────────────────────

@router.post("/api/v1/admin/daily-digest")
async def daily_digest(secret: str = "", db: Session = Depends(get_db)):
    """每日彙整推播（含假日）；由 GitHub Actions 另排程觸發。"""
    expected_secret = os.getenv("TRIGGER_SECRET", "")
    if not expected_secret or secret != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid secret")

    await send_daily_digest(db)
    return {"status": "ok"}
