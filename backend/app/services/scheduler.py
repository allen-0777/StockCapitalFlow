import asyncio
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.services.fetcher import (
    fetch_institutional_market,
    fetch_institutional_stocks,
    fetch_margin,
    fetch_futures_oi,
    fetch_options_data,
)
from app.models.database import cache_clear


def _run_async(coro):
    asyncio.run(coro)


def _job_institutional():
    try:
        _run_async(fetch_institutional_market())
        _run_async(fetch_institutional_stocks())
        cache_clear()
        print("[scheduler] institutional 完成，快取已清除")
    except Exception as e:
        print(f"[scheduler] ❌ institutional 失敗: {e}")


def _job_margin():
    try:
        _run_async(fetch_margin())
        cache_clear()
        print("[scheduler] margin 完成，快取已清除")
    except Exception as e:
        print(f"[scheduler] ❌ margin 失敗: {e}")


def _job_futures_oi():
    try:
        _run_async(fetch_futures_oi())
        _run_async(fetch_options_data())
        cache_clear()
        print("[scheduler] futures_oi + options 完成，快取已清除")
    except Exception as e:
        print(f"[scheduler] ❌ futures_oi/options 失敗: {e}")


def start_scheduler():
    scheduler = BackgroundScheduler(timezone="Asia/Taipei")

    scheduler.add_job(
        _job_institutional,
        CronTrigger(hour=16, minute=30),
        id="institutional",
        replace_existing=True,
    )
    scheduler.add_job(
        _job_margin,
        CronTrigger(hour=17, minute=30),
        id="margin",
        replace_existing=True,
    )
    scheduler.add_job(
        _job_futures_oi,
        CronTrigger(hour=17, minute=15),
        id="futures_oi",
        replace_existing=True,
    )

    scheduler.start()
    print("[scheduler] APScheduler started (16:30 法人, 17:15 期貨OI, 17:30 融資券)")
    return scheduler
