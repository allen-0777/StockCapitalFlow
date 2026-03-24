from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models.database import get_db

router = APIRouter()


@router.get("/api/v1/health")
def health(db: Session = Depends(get_db)):
    # 僅看大盤彙總列，避免個股日期干擾「最後更新」
    last_any = db.execute(
        text("SELECT MAX(date) FROM daily_chips WHERE stock_id = '0000'")
    ).scalar()
    last_inst = db.execute(
        text("""
            SELECT MAX(date) FROM daily_chips
            WHERE stock_id = '0000' AND foreign_buy IS NOT NULL
        """)
    ).scalar()
    last_margin = db.execute(
        text("""
            SELECT MAX(date) FROM daily_chips
            WHERE stock_id = '0000' AND margin_long IS NOT NULL
        """)
    ).scalar()
    return {
        "status": "healthy",
        "last_update": str(last_any) if last_any else None,
        "last_institutional": str(last_inst) if last_inst else None,
        "last_margin": str(last_margin) if last_margin else None,
    }
