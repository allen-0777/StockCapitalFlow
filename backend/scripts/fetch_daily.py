#!/usr/bin/env python3
"""
直接寫入 Supabase 的每日資料抓取腳本。
供 GitHub Actions 直接呼叫，不需喚醒 Render。

用法：
  python backend/scripts/fetch_daily.py               # 抓所有 job
  python backend/scripts/fetch_daily.py --jobs institutional,futures
  python backend/scripts/fetch_daily.py --jobs industry  # 不受交易日限制
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

# 讓 Python 找得到 app 模組
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from app.models.database import init_db
from app.services import fetcher as _fetcher
from app.services.trading_calendar import is_trading_day

# 與 admin.py 的 JOB_STEPS 對應
JOBS: dict[str, list[str]] = {
    "institutional": ["fetch_institutional_market", "fetch_institutional_stocks", "fetch_turnover"],
    "futures":       ["fetch_futures_oi", "fetch_options_data"],
    "margin":        ["fetch_margin", "fetch_exchange_rate"],
    "industry":      ["sync_stock_industries", "sync_market_series_daily"],
}

# industry 在非交易日也要跑（產業資料不依賴當日行情）
TRADING_DAY_EXEMPT = {"industry"}


async def run(job_names: list[str]) -> int:
    """執行指定 job，回傳失敗數"""
    failures = 0
    for job in job_names:
        if job not in JOBS:
            print(f"[ERROR] 未知 job: {job}，可用: {list(JOBS)}")
            failures += 1
            continue

        if job not in TRADING_DAY_EXEMPT and not is_trading_day():
            print(f"[{job}] 非交易日，跳過")
            continue

        for fn_name in JOBS[job]:
            fn = getattr(_fetcher, fn_name)
            t0 = time.monotonic()
            try:
                result = await fn()
                elapsed = round(time.monotonic() - t0, 1)
                print(f"[{job}] {fn_name} → {result} ({elapsed}s)")
            except Exception as e:
                elapsed = round(time.monotonic() - t0, 1)
                print(f"[{job}] {fn_name} ERROR ({elapsed}s): {e}")
                failures += 1

    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description="每日台股籌碼資料抓取")
    parser.add_argument(
        "--jobs",
        default="all",
        help="逗號分隔的 job 名稱，或 'all'（預設）",
    )
    args = parser.parse_args()

    init_db()

    job_list = list(JOBS.keys()) if args.jobs == "all" else args.jobs.split(",")
    print(f"[fetch_daily] 執行 jobs: {job_list}")

    failures = asyncio.run(run(job_list))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
