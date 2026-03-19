from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models.database import get_db, cache_get, cache_set

router = APIRouter()


@router.get("/api/v1/institutional/ranking")
def institutional_ranking(
    type: str = Query(default="foreign", enum=["foreign", "trust", "dealer", "total"]),
    order: str = Query(default="buy", enum=["buy", "sell"]),
    limit: int = Query(default=20, ge=5, le=100),
    db: Session = Depends(get_db),
):
    cache_key = f"ranking:{type}:{order}:{limit}"
    cached = cache_get(cache_key, ttl_seconds=3600)
    if cached is not None:
        return cached

    col_map = {
        "foreign": "foreign_buy",
        "trust": "trust_buy",
        "dealer": "dealer_buy",
        "total": "(foreign_buy + trust_buy + dealer_buy)",
    }
    col = col_map[type]
    direction = "DESC" if order == "buy" else "ASC"

    # Pre-fetch max_date to avoid correlated subquery full-table scan
    max_date = db.execute(
        text("SELECT MAX(date) FROM daily_chips WHERE stock_id != '0000' AND foreign_buy IS NOT NULL")
    ).scalar()

    if not max_date:
        return []

    rows = db.execute(
        text(f"""
            SELECT c.stock_id, COALESCE(s.name, c.stock_id) AS name,
                   c.foreign_buy, c.trust_buy, c.dealer_buy,
                   (c.foreign_buy + c.trust_buy + c.dealer_buy) AS total
            FROM daily_chips c
            LEFT JOIN stocks s ON c.stock_id = s.stock_id
            WHERE c.stock_id != '0000'
              AND c.date = :max_date
              AND {col} IS NOT NULL
            ORDER BY {col} {direction}
            LIMIT :limit
        """),
        {"max_date": max_date, "limit": limit},
    ).fetchall()

    result = [
        {
            "stock_id": r.stock_id,
            "name": r.name,
            "foreign_buy": round(float(r.foreign_buy or 0), 2),
            "trust_buy": round(float(r.trust_buy or 0), 2),
            "dealer_buy": round(float(r.dealer_buy or 0), 2),
            "total": round(float(r.total or 0), 2),
        }
        for r in rows
    ]
    cache_set(cache_key, result)
    return result
