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
    ttl = int(row.trust_tx_long or 0)
    tts = int(row.trust_tx_short or 0)
    tx_total  = tfl + tfs
    mtx_total = mrl + mrs
    trust_total = ttl + tts
    return {
        "tx_foreign_long":   tfl,
        "tx_foreign_short":  tfs,
        "tx_foreign_bull_pct": round(tfl / tx_total * 100, 2) if tx_total else None,
        "mtx_retail_long":   mrl,
        "mtx_retail_short":  mrs,
        "mtx_retail_bull_pct": round(mrl / mtx_total * 100, 2) if mtx_total else None,
        "trust_tx_long":     ttl,
        "trust_tx_short":    tts,
        "trust_tx_bull_pct": round(ttl / trust_total * 100, 2) if trust_total else None,
    }


@router.get("/api/v1/market/summary")
def market_summary(db: Session = Depends(get_db)):
    cached = cache_get("market_summary", ttl_seconds=3600)
    if cached is not None:
        return cached

    # 法人資料：取有 foreign_buy 的最新一筆
    inst_row = db.execute(
        text("""
            SELECT date, foreign_buy, trust_buy, dealer_buy, market_volume
            FROM daily_chips
            WHERE stock_id = '0000'
              AND foreign_buy IS NOT NULL
            ORDER BY date DESC
            LIMIT 1
        """)
    ).fetchone()

    # 融資券：優先與「法人列」同日（避免畫面上法人日與融資券日差一天）；
    # 若該日尚無融資券欄位，再退回「有 margin 的最新一筆」（證交所兩支 API 的 date 常不同步）
    margin_row = None
    if inst_row:
        margin_row = db.execute(
            text("""
                SELECT date, margin_long, margin_short
                FROM daily_chips
                WHERE stock_id = '0000'
                  AND date = :d
                  AND margin_long IS NOT NULL
                LIMIT 1
            """),
            {"d": inst_row.date},
        ).fetchone()
    if margin_row is None:
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

    # 期貨未平倉資料：取最近 5 日（含歷史，用於 Sparkline + 趨勢）
    futures_rows = db.execute(
        text("""
            SELECT date, tx_foreign_long, tx_foreign_short,
                   mtx_retail_long, mtx_retail_short,
                   trust_tx_long, trust_tx_short
            FROM daily_chips
            WHERE stock_id = '0000'
              AND tx_foreign_long IS NOT NULL
              AND (tx_foreign_long > 0 OR tx_foreign_short > 0)
            ORDER BY date DESC
            LIMIT 5
        """)
    ).fetchall()
    futures_row = futures_rows[0] if futures_rows else None

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
            # margin_long 存的是千元，÷ 100000 轉億元（float）
            "long_yi":   round(float(margin_row.margin_long  or 0) / 100000, 2) if margin_row else 0,
            # margin_short 存的是張
            "short_zhang": int(margin_row.margin_short or 0) if margin_row else 0,
        },
        "margin_date": str(margin_row.date) if margin_row else None,
        "futures_oi": _build_futures_oi(futures_row),
        "futures_oi_date": str(futures_row.date) if futures_row else None,
        "futures_oi_history": [
            {
                "date": str(r.date),
                **(_build_futures_oi(r) or {}),
            }
            for r in reversed(futures_rows)   # 舊→新，方便前端畫趨勢線
        ],
    }

    opt_row = db.execute(
        text("SELECT date FROM daily_options ORDER BY date DESC LIMIT 1")
    ).fetchone()
    result["options_date"] = str(opt_row.date) if opt_row else None

    # 大盤成交量
    result["volume_yi"] = round(float(inst_row.market_volume), 2) if inst_row and inst_row.market_volume else None

    # 近 20 日成交量歷史（用於 bar chart）
    vol_rows = db.execute(
        text("""
            SELECT date, market_volume FROM daily_chips
            WHERE stock_id = '0000' AND market_volume IS NOT NULL
            ORDER BY date DESC LIMIT 20
        """)
    ).fetchall()
    result["volume_history"] = [
        {"date": str(r.date), "volume_yi": round(float(r.market_volume), 2)}
        for r in reversed(vol_rows)
    ]

    # 匯率
    fx_row = db.execute(
        text("SELECT date, usd_buy, usd_sell FROM daily_exchange_rate ORDER BY date DESC LIMIT 1")
    ).fetchone()
    result["exchange_rate"] = {
        "date": str(fx_row.date),
        "usd_buy": float(fx_row.usd_buy),
        "usd_sell": float(fx_row.usd_sell),
    } if fx_row else None

    cache_set("market_summary", result)
    return result


@router.get("/api/v1/market/options")
def market_options(db: Session = Depends(get_db)):
    cached = cache_get("market_options", ttl_seconds=3600)
    if cached is not None:
        return cached

    row = db.execute(
        text("""
            SELECT date, pc_ratio, call_max_strike, put_max_strike,
                   call_total_oi, put_total_oi,
                   foreign_call_net_yi, foreign_put_net_yi
            FROM daily_options
            ORDER BY date DESC
            LIMIT 1
        """)
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="尚無選擇權數據")

    result = {
        "date": str(row.date),
        "pc_ratio": float(row.pc_ratio) if row.pc_ratio is not None else None,
        "call_max_strike": float(row.call_max_strike) if row.call_max_strike else None,
        "put_max_strike":  float(row.put_max_strike)  if row.put_max_strike  else None,
        "call_total_oi":   int(row.call_total_oi or 0),
        "put_total_oi":    int(row.put_total_oi  or 0),
        "foreign_call_net_yi": float(row.foreign_call_net_yi) if row.foreign_call_net_yi is not None else None,
        "foreign_put_net_yi":  float(row.foreign_put_net_yi)  if row.foreign_put_net_yi  is not None else None,
    }
    cache_set("market_options", result)
    return result


@router.get("/api/v1/market/exchange-rate")
def exchange_rate_history(
    days: int = 60,
    db: Session = Depends(get_db),
):
    cache_key = f"exchange_rate:{days}"
    cached = cache_get(cache_key, ttl_seconds=3600)
    if cached is not None:
        return cached

    rows = db.execute(
        text("""
            SELECT date, usd_buy, usd_sell FROM daily_exchange_rate
            ORDER BY date DESC LIMIT :days
        """),
        {"days": days},
    ).fetchall()

    result = [
        {"date": str(r.date), "usd_buy": float(r.usd_buy), "usd_sell": float(r.usd_sell)}
        for r in reversed(rows)
    ]
    cache_set(cache_key, result)
    return result
