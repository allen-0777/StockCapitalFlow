import asyncio
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.services.fetcher import (
    fetch_institutional_market,
    fetch_institutional_stocks,
    fetch_margin,
)


def _run_async(coro):
    asyncio.run(coro)


def _job_institutional():
    _run_async(fetch_institutional_market())
    _run_async(fetch_institutional_stocks())


def _job_margin():
    _run_async(fetch_margin())


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

    scheduler.start()
    print("[scheduler] APScheduler started (16:30 法人, 17:30 融資券)")
    return scheduler
