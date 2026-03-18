from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models.database import get_db

router = APIRouter()


@router.get("/api/v1/market/summary")
def market_summary(db: Session = Depends(get_db)):
    # 法人資料：取有 foreign_buy 的最新一筆
    inst_row = db.execute(
        text("""
            SELECT date, foreign_buy, trust_buy, dealer_buy
            FROM daily_chips
            WHERE stock_id = '0000'
              AND foreign_buy IS NOT NULL
            ORDER BY date DESC
            LIMIT 1
        """)
    ).fetchone()

    # 融資券資料：取有 margin_long 的最新一筆
    margin_row = db.execute(
        text("""
            SELECT date, margin_long, margin_short
            FROM daily_chips
            WHERE stock_id = '0000'
              AND margin_long IS NOT NULL
            ORDER BY date DESC
            LIMIT 1
        """)
    ).fetchone()

    if not inst_row and not margin_row:
        raise HTTPException(status_code=404, detail="尚無大盤籌碼資料，請等待每日排程執行")

    foreign = float(inst_row.foreign_buy or 0) if inst_row else 0
    trust   = float(inst_row.trust_buy   or 0) if inst_row else 0
    dealer  = float(inst_row.dealer_buy  or 0) if inst_row else 0

    return {
        "date": str(inst_row.date) if inst_row else None,
        "institutional": {
            "foreign": foreign,
            "trust":   trust,
            "dealer":  dealer,
            "total":   round(foreign + trust + dealer, 2),
        },
        "institutional_date": str(inst_row.date) if inst_row else None,
        "margin": {
            "long_balance_change":  margin_row.margin_long  or 0 if margin_row else 0,
            "short_balance_change": margin_row.margin_short or 0 if margin_row else 0,
        },
        "margin_date": str(margin_row.date) if margin_row else None,
    }
