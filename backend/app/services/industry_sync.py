"""
產業對照與市場序列同步（FinMind）。
- stock_industry：來自 TaiwanStockInfo（上市櫃產業分類）
- market_series_daily：加權／櫃買報酬指數 + 各產業代表股收盤（作為產業走勢 proxy）

寫入使用 bulk INSERT ... ON CONFLICT，並以 asyncio.to_thread 執行同步 Session，
避免阻塞 asyncio event loop（Admin polling / 其他 API）。
HTTP 請求以 asyncio.gather 並行發出。
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text

from app.models.database import SessionLocal
from app.services.finmind_client import FinMindQuotaError, finmind_get, get_shared_session

_MARKET_UPSERT_SQL = text(
    """
    INSERT INTO market_series_daily (date, series_id, name, series_type, close, volume)
    VALUES (:d, :sid, :n, :t, :c, :v)
    ON CONFLICT (date, series_id) DO UPDATE SET
        name = EXCLUDED.name,
        series_type = EXCLUDED.series_type,
        close = EXCLUDED.close,
        volume = EXCLUDED.volume
    """
)

_STOCK_INDUSTRY_UPSERT_SQL = text(
    """
    INSERT INTO stock_industry (stock_id, industry_name) VALUES (:s, :n)
    ON CONFLICT (stock_id) DO UPDATE SET industry_name = EXCLUDED.industry_name
    """
)

# 產業名稱需與 FinMind TaiwanStockInfo 的 industry_category 一致（代表股僅作走勢 proxy）
INDUSTRY_PROXY_STOCKS: list[tuple[str, str]] = [
    ("半導體業", "2330"),
    ("金融保險業", "2884"),
    ("電子零組件業", "2317"),
    ("航運業", "2603"),
    ("鋼鐵工業", "2002"),
    ("水泥工業", "1101"),
    ("塑膠工業", "1303"),
    ("光電業", "3481"),
]

GENERIC_INDUSTRY_BUCKETS = frozenset({"電子工業", "其他", "其他電子業"})


async def _get_finmind(
    session,
    dataset: str,
    data_id: str,
    start_date: str,
    end_date: str = "",
) -> list[dict[str, Any]]:
    try:
        return await finmind_get(
            session, dataset, data_id, start_date, end_date, timeout=120.0
        )
    except FinMindQuotaError:
        raise RuntimeError("FinMind API 配額已用盡")


def _pick_industry_category(rows: list[dict[str, Any]]) -> str:
    cats = {str(r.get("industry_category") or "").strip() for r in rows if r.get("industry_category")}
    if not cats:
        return ""
    if len(cats) == 1:
        return next(iter(cats))
    non_generic = cats - GENERIC_INDUSTRY_BUCKETS
    if non_generic:
        return sorted(non_generic)[0]
    return sorted(cats)[0]


def _auto_market_series_days() -> int:
    """同步查詢：僅供 to_thread 呼叫。"""
    with SessionLocal() as db:
        row = db.execute(
            text(
                "SELECT date FROM market_series_daily WHERE series_id='IDX:TAIEX' "
                "ORDER BY date DESC LIMIT 1"
            )
        ).fetchone()
    return 10 if row else 180


def _bulk_upsert(sql, rows: list[dict]) -> None:
    if not rows:
        return
    with SessionLocal() as db:
        db.execute(sql, rows)
        db.commit()


def _track_latest(d: str, current: date | None) -> date | None:
    try:
        ld = date.fromisoformat(d)
        return ld if current is None or ld > current else current
    except ValueError:
        return current


async def sync_stock_industries() -> date | None:
    """TaiwanStockInfo → stock_industry（單次約三千筆）"""
    start = (date.today() - timedelta(days=5)).strftime("%Y-%m-%d")
    session = await get_shared_session()
    rows = await _get_finmind(session, "TaiwanStockInfo", "", start)
    if not rows:
        print("[industry] TaiwanStockInfo 無資料")
        return None

    by_stock: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        sid = str(r.get("stock_id") or "").strip()
        if sid:
            by_stock[sid].append(r)

    stock_params: list[dict[str, Any]] = []
    for sid, group in by_stock.items():
        cat = _pick_industry_category(group)
        if cat:
            stock_params.append({"s": sid, "n": cat})

    await asyncio.to_thread(_bulk_upsert, _STOCK_INDUSTRY_UPSERT_SQL, stock_params)

    print(f"[industry] stock_industry 同步完成: {len(by_stock)} 檔")
    return date.today()


async def sync_market_series_daily(days: int = 0) -> date | None:
    """
    TaiwanStockTotalReturnIndex：TAIEX、TPEx；
    TaiwanStockPrice：各產業代表股 → series_id IND:產業名稱。
    days=0 時自動判斷：DB 已有資料則抓 10 天增量，否則抓 180 天初始化。
    """
    if days == 0:
        days = await asyncio.to_thread(_auto_market_series_days)
        print(f"[industry] auto days={days}")
    start = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    latest: date | None = None

    # 並行發出全部 10 個 HTTP 請求（2 指數 + 8 代理股），共用 Session
    session = await get_shared_session()
    index_labels = [("TAIEX", "加權報酬指數"), ("TPEx", "櫃買報酬指數")]
    results = await asyncio.gather(
        *[_get_finmind(session, "TaiwanStockTotalReturnIndex", idx_id, start)
          for idx_id, _ in index_labels],
        *[_get_finmind(session, "TaiwanStockPrice", stock_id, start)
          for _, stock_id in INDUSTRY_PROXY_STOCKS],
    )
    index_results = list(zip(index_labels, results[:2]))
    proxy_results = list(zip(INDUSTRY_PROXY_STOCKS, results[2:]))

    for (idx_id, label), rows in index_results:
        print(f"[industry] IDX:{idx_id} 取得 {len(rows)} 筆")
    for (ind_name, stock_id), rows in proxy_results:
        print(f"[industry] proxy {stock_id} ({ind_name}) 取得 {len(rows)} 筆")

    rows_to_upsert: list[dict[str, Any]] = []

    for (idx_id, label), rows in index_results:
        for r in rows:
            d = str(r.get("date", ""))[:10]
            price = float(r.get("price") or 0)
            if not d or price <= 0:
                continue
            rows_to_upsert.append({"d": d, "sid": f"IDX:{idx_id}", "n": label, "t": "index", "c": price, "v": None})
            latest = _track_latest(d, latest)

    for (ind_name, stock_id), rows in proxy_results:
        sid = f"IND:{ind_name}"
        for r in rows:
            d = str(r.get("date", ""))[:10]
            close = float(r.get("close") or 0)
            vol = int(r.get("Trading_Volume") or 0)
            if not d or close <= 0:
                continue
            rows_to_upsert.append({"d": d, "sid": sid, "n": f"{ind_name}（{stock_id}）", "t": "proxy", "c": close, "v": vol})
            latest = _track_latest(d, latest)

    await asyncio.to_thread(_bulk_upsert, _MARKET_UPSERT_SQL, rows_to_upsert)

    return latest
