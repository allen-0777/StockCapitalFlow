import aiohttp
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models.database import get_db

router = APIRouter()

_stock_cache: list = []

async def _fetch_stock_list() -> list:
    global _stock_cache
    if _stock_cache:
        return _stock_cache
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            data = await resp.json(content_type=None)
            _stock_cache = [{"code": r["Code"], "name": r["Name"]} for r in data if r.get("Code")]
    return _stock_cache


@router.get("/api/v1/stocks/search")
async def search_stocks(q: str = Query(..., min_length=1)):
    """依股號或股名模糊搜尋，回傳最多 10 筆"""
    stocks = await _fetch_stock_list()
    q = q.strip()
    results = [s for s in stocks if q in s["code"] or q in s["name"]]
    return results[:10]


@router.get("/api/v1/stocks/{stock_id}/chips")
def stock_chips(stock_id: str, days: int = Query(default=5, ge=1, le=60), db: Session = Depends(get_db)):
    rows = db.execute(
        text("""
            SELECT date, foreign_buy, trust_buy, dealer_buy, margin_long, margin_short
            FROM daily_chips
            WHERE stock_id = :stock_id
            ORDER BY date DESC
            LIMIT :days
        """),
        {"stock_id": stock_id, "days": days}
    ).fetchall()

    return [
        {
            "date": str(r.date),
            "foreign_buy": float(r.foreign_buy or 0),
            "trust_buy": float(r.trust_buy or 0),
            "dealer_buy": float(r.dealer_buy or 0),
            "margin_long": r.margin_long or 0,
            "margin_short": r.margin_short or 0,
        }
        for r in rows
    ]
