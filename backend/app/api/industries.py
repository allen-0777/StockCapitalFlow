from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.database import get_db, cache_get, cache_set
from app.services.industry_sync import INDUSTRY_PROXY_STOCKS
from app.services.rotation import build_chart_pack

router = APIRouter()


@router.get("/api/v1/industries")
def list_industries(db: Session = Depends(get_db)):
    """產業 proxy 列表 + DB 內實際有資料的 series"""
    rows = db.execute(
        text(
            """
            SELECT DISTINCT series_id, name, series_type
            FROM market_series_daily
            WHERE series_id LIKE 'IND:%' OR series_id LIKE 'IDX:%'
            ORDER BY series_id
            """
        )
    ).fetchall()
    from_db = [
        {"series_id": r[0], "name": r[1], "series_type": r[2]}
        for r in rows
    ]
    proxies = [
        {
            "series_id": f"IND:{name}",
            "industry_name": name,
            "proxy_stock": stock,
            "note": "走勢為代表股收盤，非官方產業指數",
        }
        for name, stock in INDUSTRY_PROXY_STOCKS
    ]
    return {"proxies_config": proxies, "series_in_db": from_db}


@router.get("/api/v1/industries/series")
def get_series(
    series_id: str = Query(..., description="例如 IDX:TAIEX 或 IND:半導體業"),
    days: int = Query(180, ge=30, le=800),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text(
            """
            SELECT date, close, volume, name, series_type
            FROM market_series_daily
            WHERE series_id = :sid
            ORDER BY date DESC
            LIMIT :lim
            """
        ),
        {"sid": series_id, "lim": days},
    ).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail=f"無此序列: {series_id}")
    meta = {"name": rows[0][3], "series_type": rows[0][4]}
    pts = [
        {
            "date": str(r[0])[:10],
            "close": float(r[1]),
            "volume": int(r[2]) if r[2] is not None else None,
        }
        for r in reversed(rows)
    ]
    return {"series_id": series_id, **meta, "points": pts}


@router.get("/api/v1/industries/chart-pack")
def industries_chart_pack(
    days: int = Query(180, ge=30, le=800),
    db: Session = Depends(get_db),
):
    cache_key = f"industries_chart_pack:{days}"
    cached = cache_get(cache_key, ttl_seconds=1800)
    if cached is not None:
        return cached
    pack = build_chart_pack(db, days=days)
    if not pack.get("benchmark"):
        pack["note"] = (
            "尚無大盤序列資料，請執行產業同步：POST /api/v1/admin/trigger/industry（需 TRIGGER_SECRET）"
        )
    cache_set(cache_key, pack)
    return pack
