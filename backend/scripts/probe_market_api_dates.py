#!/usr/bin/env python3
"""
只讀探測：期交所 TAIFEX、證交所 TWSE 融資券 API 目前回傳的「資料交易日」。
fetch_daily 單次執行只會寫入這些 API 各自回傳的那一天，無法在同一次呼叫內補兩個歷史日。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from app.services.fetcher import (
    TWSE_BASE,
    _get_json_with_retry,
    _get_taifex_json,
    _parse_twse_date,
)


async def main() -> None:
    print("=== TAIFEX 期貨三大法人未平倉 ===")
    fut = await _get_taifex_json(
        "/MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate"
    )
    if fut:
        d = fut[0].get("Date")
        print(f"  第一筆 Date (YYYYMMDD): {d}")
    else:
        print("  空資料")

    print("=== TAIFEX 選擇權三大法人 ===")
    opt = await _get_taifex_json(
        "/MarketDataOfMajorInstitutionalTradersDetailsOfCallsAndPutsBytheDate"
    )
    if opt:
        d = opt[0].get("Date")
        print(f"  第一筆 Date (YYYYMMDD): {d}")
    else:
        print("  空資料")

    print("=== TWSE 融資券 MI_MARGN ===")
    try:
        data = await _get_json_with_retry(
            f"{TWSE_BASE}/marginTrading/MI_MARGN?response=json&selectType=MS"
        )
        td = _parse_twse_date(data)
        print(f"  解析後交易日: {td}  stat={data.get('stat')}")
    except Exception as e:
        print(f"  ERROR: {e}")

    print()
    print(
        "說明：若上三者皆為「最近一個已公布日」（例如週五 3/27），"
        "則 fetch_daily 單跑一趟只會更新該日；要補 3/26 須 API 仍提供該日或另有歷史參數（目前 fetcher 未帶日期參數）。"
    )


if __name__ == "__main__":
    asyncio.run(main())
