from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models.database import get_db, cache_get, cache_set

router = APIRouter()


def _build_futures_oi(row) -> dict:
    if not row:
        return None
    tfl = int(row.tx_foreign_long or 0)
    tfs = int(row.tx_foreign_short or 0)
    mrl = int(row.mtx_retail_long or 0)
    mrs = int(row.mtx_retail_short or 0)
    tx_total = tfl + tfs
    mtx_total = mrl + mrs
    return {
        "tx_foreign_long": tfl,
        "tx_foreign_short": tfs,
        "tx_foreign_bull_pct": round(tfl / tx_total * 100, 2) if tx_total else None,
        "mtx_retail_long": mrl,
        "mtx_retail_short": mrs,
        "mtx_retail_bull_pct": round(mrl / mtx_total * 100, 2) if mtx_total else None,
    }


@router.get("/api/v1/market/summary")
def market_summary(db: Session = Depends(get_db)):
    cached = cache_get("market_summary", ttl_seconds=3600)
    if cached is not None:
        return cached

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

    # 期貨未平倉資料：取有 tx_foreign_long 的最新一筆
    futures_row = db.execute(
        text("""
            SELECT date, tx_foreign_long, tx_foreign_short,
                   mtx_retail_long, mtx_retail_short
            FROM daily_chips
            WHERE stock_id = '0000'
              AND tx_foreign_long IS NOT NULL
            ORDER BY date DESC
            LIMIT 1
        """)
    ).fetchone()

    if not inst_row and not margin_row:
        raise HTTPException(status_code=404, detail="尚無大盤籌碼資料，請等待每日排程執行")

    foreign = float(inst_row.foreign_buy or 0) if inst_row else 0
    trust   = float(inst_row.trust_buy   or 0) if inst_row else 0
    dealer  = float(inst_row.dealer_buy  or 0) if inst_row else 0

    result = {
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
        "futures_oi": _build_futures_oi(futures_row),
        "futures_oi_date": str(futures_row.date) if futures_row else None,
    }
    cache_set("market_summary", result)
    return result
