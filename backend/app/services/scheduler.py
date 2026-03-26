import asyncio
import time
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.services.fetcher import (
    fetch_institutional_market,
    fetch_institutional_stocks,
    fetch_margin,
    fetch_futures_oi,
    fetch_options_data,
    sync_stock_industries,
    sync_market_series_daily,
)
from app.services.trading_calendar import is_trading_day, latest_trading_day
from app.models.database import cache_clear

RETRY_WAIT_SEC = 600   # 資料日期不符時等待 10 分鐘
MAX_RETRIES    = 3


def _run_async(coro):
    return asyncio.run(coro)


def _run_job(job_name: str, steps: list, expected_date=None):
    """
    通用排程執行器，包含三層保護：
      1. 交易日判斷（非交易日直接跳過）
      2. 日期驗證（抓到的資料日期 ≠ 預期交易日 → 等待後重試）
      3. 例外捕捉（網路/API 錯誤時記錄並退出，不影響其他排程）
    """
    if not is_trading_day():
        print(f"[scheduler] {job_name}: 今日非台股交易日，跳過")
        return

    expected = expected_date or latest_trading_day()

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            got_date = None
            for fn in steps:
                result = _run_async(fn())
                if result is not None:
                    got_date = result      # 取最後一個有回傳日期的 step

            # 日期驗證：若資料日期 ≠ 預期最新交易日
            if got_date and got_date != expected:
                if attempt < MAX_RETRIES:
                    print(
                        f"[scheduler] ⏳ {job_name}: 資料日期 {got_date} ≠ 預期 {expected}，"
                        f"等待 {RETRY_WAIT_SEC // 60} 分鐘後重試 ({attempt}/{MAX_RETRIES})"
                    )
                    time.sleep(RETRY_WAIT_SEC)
                    continue
                else:
                    print(f"[scheduler] ⚠️  {job_name}: 重試耗盡，使用最新可得資料 ({got_date})")

            cache_clear()
            print(f"[scheduler] ✅ {job_name} 完成 (資料日期: {got_date or expected})")
            return

        except Exception as e:
            print(f"[scheduler] ❌ {job_name} 第 {attempt} 次失敗: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_WAIT_SEC)


def _job_institutional():
    _run_job("法人買賣超", [fetch_institutional_market, fetch_institutional_stocks])


def _job_futures_oi():
    _run_job("期貨OI + 選擇權", [fetch_futures_oi, fetch_options_data])


def _job_margin():
    _run_job("融資券", [fetch_margin])


def _job_industry():
    """產業對照 + 大盤／產業 proxy 日線（FinMind）；非交易日略過。"""
    if not is_trading_day():
        print("[scheduler] industry: 今日非台股交易日，跳過")
        return
    try:
        _run_async(sync_stock_industries())
        got = _run_async(sync_market_series_daily())
        cache_clear()
        print(f"[scheduler] ✅ industry 完成 (最新序列日: {got})")
    except Exception as e:
        print(f"[scheduler] ❌ industry 失敗: {e}")


def start_scheduler():
    scheduler = BackgroundScheduler(timezone="Asia/Taipei")

    # 時間後移：避開收盤後各平台擠入 API 的高峰期，並給 FinMind 充足同步時間
    scheduler.add_job(
        _job_institutional,
        CronTrigger(hour=17, minute=0),    # 原 16:30 → 17:00
        id="institutional",
        replace_existing=True,
    )
    scheduler.add_job(
        _job_futures_oi,
        CronTrigger(hour=17, minute=30),   # 原 17:15 → 17:30
        id="futures_oi",
        replace_existing=True,
    )
    scheduler.add_job(
        _job_margin,
        CronTrigger(hour=17, minute=45),   # 原 17:30 → 17:45
        id="margin",
        replace_existing=True,
    )
    scheduler.add_job(
        _job_industry,
        CronTrigger(hour=18, minute=5),
        id="industry",
        replace_existing=True,
    )

    scheduler.start()
    print("[scheduler] APScheduler started")
    print("[scheduler]   17:00 法人買賣超（交易日驗證 + 10 分鐘重試）")
    print("[scheduler]   17:30 期貨OI + 選擇權（交易日驗證 + 10 分鐘重試）")
    print("[scheduler]   17:45 融資券（交易日驗證 + 10 分鐘重試）")
    print("[scheduler]   18:05 產業／市場序列（FinMind，交易日）")
    return scheduler
