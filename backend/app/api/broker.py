import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models.database import get_db
from app.services.finmind_fetcher import fetch_broker_daily, fetch_stock_price
from app.services.broker_analysis import get_recent_flow, get_key_branches

router = APIRouter()


def _stock_name(db: Session, stock_id: str) -> str:
    row = db.execute(
        text("SELECT name FROM stocks WHERE stock_id=:s"), {"s": stock_id}
    ).fetchone()
    return row.name if row else stock_id


def _date_range(db: Session, stock_id: str, days: int) -> dict:
    rows = db.execute(
        text("""SELECT MIN(date) AS from_d, MAX(date) AS to_d FROM broker_daily
                WHERE stock_id=:s AND date >= date('now', :offset)"""),
        {"s": stock_id, "offset": f"-{days} days"}
    ).fetchone()
    return {"from": rows.from_d or "", "to": rows.to_d or ""}


@router.get("/api/v1/stocks/{stock_id}/broker/flow")
def broker_flow(stock_id: str, days: int = 30, db: Session = Depends(get_db)):
    """近 N 日各分點買賣超排行"""
    branches = get_recent_flow(db, stock_id, days)
    return {
        "stock_id":   stock_id,
        "stock_name": _stock_name(db, stock_id),
        "days":       days,
        "date_range": _date_range(db, stock_id, days),
        "branches":   branches,
    }


@router.get("/api/v1/stocks/{stock_id}/broker/keypoints")
def broker_keypoints(stock_id: str, lookforward: int = 5, days: int = 90,
                     db: Session = Depends(get_db)):
    """關鍵分點回測結果"""
    branches = get_key_branches(db, stock_id, lookforward, days)
    return {
        "stock_id":             stock_id,
        "stock_name":           _stock_name(db, stock_id),
        "lookforward_days":     lookforward,
        "backtest_period_days": days,
        "branches":             branches,
    }


@router.post("/api/v1/stocks/{stock_id}/broker/fetch")
async def broker_fetch(stock_id: str):
    """手動觸發抓取指定股票的分點資料（broker + price）"""
    try:
        broker_count, price_count = await asyncio.gather(
            fetch_broker_daily(stock_id, days=90),
            fetch_stock_price(stock_id, days=100),
        )
        return {
            "status":       "ok",
            "stock_id":     stock_id,
            "broker_rows":  broker_count,
            "price_rows":   price_count,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
