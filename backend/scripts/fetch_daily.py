#!/usr/bin/env python3
"""
直接寫入 Supabase 的每日資料抓取腳本。
供 GitHub Actions 直接呼叫，不需喚醒 Render。

用法：
  python backend/scripts/fetch_daily.py               # 抓所有 job
  python backend/scripts/fetch_daily.py --jobs institutional,futures
  python backend/scripts/fetch_daily.py --jobs industry  # 不受交易日限制
  python backend/scripts/fetch_daily.py --jobs futures,margin --force  # 週末也跑（仍只寫 API 回傳之交易日）
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

# 讓 Python 找得到 app 模組
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from app.models.database import init_db
from app.services import fetcher as _fetcher
from app.services.trading_calendar import is_trading_day, latest_trading_day

# 與 admin.py 的 JOB_STEPS 對應
JOBS: dict[str, list[str]] = {
    "institutional": ["fetch_institutional_market", "fetch_institutional_stocks", "fetch_turnover"],
    "futures":       ["fetch_futures_oi", "fetch_options_data"],
    "margin":        ["fetch_margin", "fetch_exchange_rate"],
    "industry":      ["sync_stock_industries", "sync_market_series_daily"],
}

DATA_READY_HOUR = 15  # 台北時間

# industry 在非交易日也要跑（產業資料不依賴當日行情）
TRADING_DAY_EXEMPT = {"industry"}


async def run(job_names: list[str], *, force: bool = False) -> int:
    """執行指定 job，回傳失敗數。force=True 時略過「非交易日跳過」（industry 本來就不跳過）。"""
    failures = 0
    now = datetime.now(ZoneInfo("Asia/Taipei"))
    today = now.date()
    trading_today = is_trading_day(today)
    # 盤後資料約 15:00 後才陸續公布；之前手動執行時以前一個交易日為預期日期
    expected = latest_trading_day(today if now.hour >= DATA_READY_HOUR else today - timedelta(days=1))
    # force 補抓與非交易日手動執行不要求當日行情；例外仍算失敗。
    check_freshness = trading_today and not force
    stale = []
    try:
        for job in job_names:
            if job not in JOBS:
                print(f"[ERROR] 未知 job: {job}，可用: {list(JOBS)}")
                failures += 1
                continue

            if not force and job not in TRADING_DAY_EXEMPT and not trading_today:
                print(f"[{job}] 非交易日，跳過")
                continue

            for fn_name in JOBS[job]:
                fn = getattr(_fetcher, fn_name)
                t0 = time.monotonic()
                try:
                    result = await fn()
                    elapsed = round(time.monotonic() - t0, 1)
                    print(f"[{job}] {fn_name} → {result} ({elapsed}s)")
                    # 產業分類是 metadata，不回傳行情日期。
                    if check_freshness and fn_name != "sync_stock_industries" and str(result) != expected.isoformat():
                        stale.append(f"{job}/{fn_name}: got={result}, expected={expected}")
                        failures += 1
                except Exception as e:
                    elapsed = round(time.monotonic() - t0, 1)
                    print(f"[{job}] {fn_name} ERROR ({elapsed}s): {e}")
                    failures += 1

    finally:
        from app.services.finmind_client import close_shared_session

        await close_shared_session()

    if stale:
        print("[ERROR] Stale/missing data: " + "; ".join(stale))
    return failures


# 補資料：TWSE 端點支援指定日期、匯率走 FinMind 區間；TAIFEX OpenAPI（期貨/選擇權）只提供最新一日，無法回補
BACKFILL_TWSE_FNS = ["fetch_institutional_market", "fetch_institutional_stocks", "fetch_margin", "fetch_turnover"]
BACKFILL_FINMIND_REQUESTS = 11  # 匯率 1 次 + sync_market_series_daily（2 指數 + 8 代理股），皆一次抓整段區間


def backfill_days(start: date, end: date) -> list[date]:
    """start..end（含）之間的台股交易日。"""
    days, d = [], start
    while d <= end:
        if is_trading_day(d):
            days.append(d)
        d += timedelta(days=1)
    return days


async def backfill(start: date, end: date, *, interval_s: float = 3.0, dry_run: bool = False) -> int:
    """依交易日逐日回補 TWSE 籌碼資料，最後一次性回補 market_series_daily（FinMind）。回傳失敗數。"""
    days = backfill_days(start, end)
    twse_requests = len(days) * len(BACKFILL_TWSE_FNS)
    print(f"[backfill] {start}..{end}: {len(days)} 個交易日，TWSE 約 {twse_requests} 次請求"
          f"（間隔 {interval_s}s，約 {round(twse_requests * interval_s / 60)} 分鐘），"
          f"FinMind {BACKFILL_FINMIND_REQUESTS} 次")
    print("[backfill] 期貨/選擇權（TAIFEX OpenAPI）僅提供最新資料，不在回補範圍")
    if dry_run:
        return 0

    from app.services.finmind_client import close_shared_session

    failures = 0
    try:
        for d in days:
            for fn_name in BACKFILL_TWSE_FNS:
                fn = getattr(_fetcher, fn_name)
                try:
                    got = await fn(target=d)
                    if got != d:
                        print(f"[backfill] {fn_name} {d}: API 回傳日期 {got}，不符")
                        failures += 1
                except Exception as e:
                    print(f"[backfill] {fn_name} {d} ERROR: {e}")
                    failures += 1
                await asyncio.sleep(interval_s)  # TWSE 對短時間大量請求會封鎖 IP
        try:
            latest_fx = await _fetcher.fetch_exchange_rate(start=start)
            print(f"[backfill] exchange_rate from {start} → latest={latest_fx}")
        except Exception as e:
            print(f"[backfill] fetch_exchange_rate ERROR: {e}")
            failures += 1
        days_back = (_taipei_today() - start).days + 1
        try:
            latest = await _fetcher.sync_market_series_daily(days=days_back)
            print(f"[backfill] market_series_daily days={days_back} → latest={latest}")
        except Exception as e:
            print(f"[backfill] sync_market_series_daily ERROR: {e}")
            failures += 1
    finally:
        await close_shared_session()
    return failures


def _taipei_today() -> date:
    return datetime.now(ZoneInfo("Asia/Taipei")).date()


def main() -> None:
    parser = argparse.ArgumentParser(description="每日台股籌碼資料抓取")
    parser.add_argument(
        "--jobs",
        default="all",
        help="逗號分隔的 job 名稱，或 'all'（預設）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="非交易日仍執行（週末／假日手動補抓；寫入日期仍依 API 回傳）",
    )
    parser.add_argument("--start", type=date.fromisoformat, help="補資料起日 YYYY-MM-DD（與 --end 一起使用）")
    parser.add_argument("--end", type=date.fromisoformat, help="補資料迄日 YYYY-MM-DD（預設今日）")
    parser.add_argument("--interval", type=float, default=3.0, help="補資料時 TWSE 請求間隔秒數")
    parser.add_argument("--dry-run", action="store_true", help="只印出補資料的交易日數與預估請求數")
    args = parser.parse_args()

    if args.start:
        end = args.end or _taipei_today()
        if args.start > end:
            parser.error("--start 不可晚於 --end")
        if not args.dry_run:
            init_db()
        failures = asyncio.run(backfill(args.start, end, interval_s=args.interval, dry_run=args.dry_run))
        sys.exit(1 if failures else 0)

    init_db()

    job_list = list(JOBS.keys()) if args.jobs == "all" else args.jobs.split(",")
    print(f"[fetch_daily] 執行 jobs: {job_list}" + (" [force]" if args.force else ""))

    failures = asyncio.run(run(job_list, force=args.force))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
