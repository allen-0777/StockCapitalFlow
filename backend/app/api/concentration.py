import asyncio
import aiohttp
from collections import defaultdict
from datetime import date, timedelta
from fastapi import APIRouter, HTTPException

from app.services.finmind_client import FinMindQuotaError, finmind_get, get_shared_session

router = APIRouter()


async def _get_finmind(dataset: str, data_id: str, start_date: str) -> list:
    try:
        session = await get_shared_session()
        return await finmind_get(
            session, dataset, data_id, start_date, timeout=30.0
        )
    except FinMindQuotaError:
        raise HTTPException(status_code=503, detail="FinMind API 配額已耗盡，請明日再試")
    except (aiohttp.ClientError, TimeoutError) as e:
        raise HTTPException(status_code=503, detail=f"FinMind API 暫時無法連線: {e}")


@router.get("/api/v1/stocks/{stock_id}/concentration")
async def get_concentration(stock_id: str, days: int = 60):
    start_date = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")

    institutional_rows, shareholding_rows = await asyncio.gather(
        _get_institutional(stock_id, start_date),
        _get_shareholding(stock_id, start_date),
    )

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
