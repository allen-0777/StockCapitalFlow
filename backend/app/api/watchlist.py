from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from app.models.database import get_db

router = APIRouter()


class WatchlistAdd(BaseModel):
    stock_id: str


@router.get("/api/v1/users/{user_id}/watchlist")
def get_watchlist(user_id: int, db: Session = Depends(get_db)):
    stocks = db.execute(
        text("SELECT stock_id FROM watchlists WHERE user_id = :uid"),
        {"uid": user_id}
    ).fetchall()

    result = []
    for s in stocks:
        sid = s.stock_id
        row = db.execute(
            text("""
                SELECT c.date, c.foreign_buy, c.trust_buy, c.dealer_buy,
                       COALESCE(st.name, c.stock_id) AS name
                FROM daily_chips c
                LEFT JOIN stocks st ON c.stock_id = st.stock_id
                WHERE c.stock_id = :sid
                ORDER BY c.date DESC
                LIMIT 1
            """),
            {"sid": sid}
        ).fetchone()

        entry = {
            "stock_id": sid,
            "name": row.name if row else sid,
            "foreign_buy": float(row.foreign_buy or 0) if row else 0,
            "trust_buy": float(row.trust_buy or 0) if row else 0,
            "dealer_buy": float(row.dealer_buy or 0) if row else 0,
            "date": str(row.date) if row else None,
        }
        result.append(entry)

    return result


@router.post("/api/v1/users/{user_id}/watchlist", status_code=201)
def add_watchlist(user_id: int, body: WatchlistAdd, db: Session = Depends(get_db)):
    existing = db.execute(
        text("SELECT id FROM watchlists WHERE user_id=:uid AND stock_id=:sid"),
        {"uid": user_id, "sid": body.stock_id}
    ).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="已在觀察清單中")

    db.execute(
        text("INSERT INTO watchlists (user_id, stock_id) VALUES (:uid, :sid)"),
        {"uid": user_id, "sid": body.stock_id}
    )
    db.commit()
    return {"message": "新增成功", "stock_id": body.stock_id}


@router.delete("/api/v1/users/{user_id}/watchlist/{stock_id}", status_code=200)
def delete_watchlist(user_id: int, stock_id: str, db: Session = Depends(get_db)):
    db.execute(
        text("DELETE FROM watchlists WHERE user_id=:uid AND stock_id=:sid"),
        {"uid": user_id, "sid": stock_id}
    )
    db.commit()
    return {"message": "已移除", "stock_id": stock_id}
