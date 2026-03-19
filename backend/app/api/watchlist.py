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
    rows = db.execute(
        text("""
            SELECT w.stock_id,
                   COALESCE(s.name, w.stock_id) AS name,
                   c.date,
                   c.foreign_buy,
                   c.trust_buy,
                   c.dealer_buy
            FROM watchlists w
            LEFT JOIN stocks s ON w.stock_id = s.stock_id
            LEFT JOIN daily_chips c
                ON c.stock_id = w.stock_id
               AND c.date = (
                   SELECT MAX(c2.date) FROM daily_chips c2
                   WHERE c2.stock_id = w.stock_id
                     AND c2.foreign_buy IS NOT NULL
               )
            WHERE w.user_id = :uid
        """),
        {"uid": user_id}
    ).fetchall()

    return [
        {
            "stock_id": r.stock_id,
            "name": r.name,
            "foreign_buy": float(r.foreign_buy or 0) if r.foreign_buy is not None else 0,
            "trust_buy":   float(r.trust_buy   or 0) if r.trust_buy   is not None else 0,
            "dealer_buy":  float(r.dealer_buy  or 0) if r.dealer_buy  is not None else 0,
            "date": str(r.date) if r.date else None,
        }
        for r in rows
    ]


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
