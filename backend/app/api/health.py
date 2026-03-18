from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models.database import get_db

router = APIRouter()


@router.get("/api/v1/health")
def health(db: Session = Depends(get_db)):
    row = db.execute(
        text("SELECT MAX(date) FROM daily_chips")
    ).scalar()
    last_update = str(row) if row else None
    return {"status": "healthy", "last_update": last_update}
