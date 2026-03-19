import os
import aiohttp
from collections import defaultdict
from datetime import date, timedelta
from fastapi import APIRouter, HTTPException

router = APIRouter()

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"


def _token() -> str:
    return os.getenv("FINMIND_TOKEN", "")


async def _get_finmind(dataset: str, data_id: str, start_date: str) -> list:
    params = {"dataset": dataset, "data_id": data_id, "start_date": start_date}
    headers = {"Authorization": f"Bearer {_token()}"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                FINMIND_URL, params=params, headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 402:
                    raise HTTPException(status_code=503, detail="FinMind API 配額已耗盡，請明日再試")
                body = await resp.json(content_type=None)
                if body.get("status") != 200:
                    return []
                return body.get("data", [])
    except HTTPException:
        raise
    except (aiohttp.ClientError, TimeoutError) as e:
        raise HTTPException(status_code=503, detail=f"FinMind API 暫時無法連線: {e}")


@router.get("/api/v1/stocks/{stock_id}/concentration")
async def get_concentration(stock_id: str, days: int = 60):
    start_date = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")

    institutional_rows, shareholding_rows = await _get_institutional(stock_id, start_date), []
    shareholding_rows = await _get_shareholding(stock_id, start_date)

    # 整理法人買賣超：按日期聚合
    daily = defaultdict(lambda: {"foreign": 0, "trust": 0, "dealer": 0})
    name_map = {
        "Foreign_Investor": "foreign",
        "Foreign_Dealer_Self": "foreign",
        "Investment_Trust": "trust",
        "Dealer_self": "dealer",
        "Dealer_Hedging": "dealer",
    }
    for r in institutional_rows:
        key = name_map.get(r["name"])
        if key:
            d = r["date"]
            daily[d][key] += r["buy"] - r["sell"]

    institutional = [
        {"date": d, "foreign": v["foreign"], "trust": v["trust"], "dealer": v["dealer"]}
        for d, v in sorted(daily.items())
    ]

    # 整理外資持股比例
    shareholding = [
        {
            "date": r["date"],
            "foreign_ratio": round(r.get("ForeignInvestmentSharesRatio", 0), 2),
        }
        for r in shareholding_rows
    ]

    return {
        "stock_id": stock_id,
        "institutional": institutional,
        "shareholding": shareholding,
    }


async def _get_institutional(stock_id: str, start_date: str) -> list:
    return await _get_finmind("TaiwanStockInstitutionalInvestorsBuySell", stock_id, start_date)


async def _get_shareholding(stock_id: str, start_date: str) -> list:
    return await _get_finmind("TaiwanStockShareholding", stock_id, start_date)
