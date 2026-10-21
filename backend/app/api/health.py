from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models.database import get_db

router = APIRouter()


@router.get("/api/v1/health")
def health(db: Session = Depends(get_db)):
    # 大盤彙總表；單次查詢（MAX + CASE）相容 SQLite / PostgreSQL
    row = db.execute(
        text("""
            SELECT
                MAX(date) AS last_any,
                MAX(CASE WHEN foreign_buy IS NOT NULL THEN date END) AS last_inst,
                MAX(CASE WHEN margin_long IS NOT NULL THEN date END) AS last_margin
            FROM market_daily
        """)
    ).one()
    last_any, last_inst, last_margin = row[0], row[1], row[2]
    return {
        "status": "healthy",
        "last_update": str(last_any) if last_any else None,
        "last_institutional": str(last_inst) if last_inst else None,
        "last_margin": str(last_margin) if last_margin else None,
    }
