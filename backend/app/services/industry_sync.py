"""
產業對照與市場序列同步（FinMind）。
- stock_industry：來自 TaiwanStockInfo（上市櫃產業分類）
- market_series_daily：加權／櫃買報酬指數 + 各產業代表股收盤（作為產業走勢 proxy）
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

import aiohttp
from sqlalchemy import text

from app.models.database import SessionLocal

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"

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


def _token() -> str:
    return os.getenv("FINMIND_TOKEN", "")


async def _get_finmind(
    dataset: str,
    data_id: str,
    start_date: str,
    end_date: str = "",
) -> list[dict[str, Any]]:
    params: dict[str, str] = {
        "dataset": dataset,
        "data_id": data_id,
        "start_date": start_date,
    }
    if end_date:
        params["end_date"] = end_date
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; LiquidChip/1.0)",
        "Authorization": f"Bearer {_token()}",
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(
            FINMIND_URL,
            params=params,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=120),
        ) as resp:
            if resp.status == 402:
                raise RuntimeError("FinMind API 配額已用盡")
            resp.raise_for_status()
            body = await resp.json(content_type=None)
            return body.get("data", [])


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


def _upsert_stock_industry(db, stock_id: str, industry_name: str) -> None:
    if not stock_id or not industry_name:
        return
    row = db.execute(
        text("SELECT stock_id FROM stock_industry WHERE stock_id = :s"),
        {"s": stock_id},
    ).fetchone()
    if row:
        db.execute(
            text("UPDATE stock_industry SET industry_name = :n WHERE stock_id = :s"),
            {"n": industry_name, "s": stock_id},
        )
    else:
        db.execute(
            text("INSERT INTO stock_industry (stock_id, industry_name) VALUES (:s, :n)"),
            {"s": stock_id, "n": industry_name},
        )


def _upsert_market_series(
    db,
    d: str,
    series_id: str,
    name: str,
    series_type: str,
    close: float,
    volume: int | None,
) -> None:
    existing = db.execute(
        text("SELECT series_id FROM market_series_daily WHERE date = :d AND series_id = :sid"),
        {"d": d, "sid": series_id},
    ).fetchone()
    if existing:
        db.execute(
            text(
                """UPDATE market_series_daily SET name=:n, series_type=:t,
                   close=:c, volume=:v WHERE date=:d AND series_id=:sid"""
            ),
            {"n": name, "t": series_type, "c": close, "v": volume, "d": d, "sid": series_id},
        )
    else:
        db.execute(
            text(
                """INSERT INTO market_series_daily
                   (date, series_id, name, series_type, close, volume)
                   VALUES (:d, :sid, :n, :t, :c, :v)"""
            ),
            {"d": d, "sid": series_id, "n": name, "t": series_type, "c": close, "v": volume},
        )


async def sync_stock_industries() -> date | None:
    """TaiwanStockInfo → stock_industry（單次約三千筆）"""
    start = (date.today() - timedelta(days=5)).strftime("%Y-%m-%d")
    rows = await _get_finmind("TaiwanStockInfo", "", start)
    if not rows:
        print("[industry] TaiwanStockInfo 無資料")
        return None

    by_stock: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        sid = str(r.get("stock_id") or "").strip()
        if sid:
            by_stock[sid].append(r)

    with SessionLocal() as db:
        for sid, group in by_stock.items():
            cat = _pick_industry_category(group)
            if cat:
                _upsert_stock_industry(db, sid, cat)
        db.commit()

    print(f"[industry] stock_industry 同步完成: {len(by_stock)} 檔")
    return date.today()


async def sync_market_series_daily(days: int = 400) -> date | None:
    """
    TaiwanStockTotalReturnIndex：TAIEX、TPEx；
    TaiwanStockPrice：各產業代表股 → series_id IND:產業名稱。
    """
    start = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    latest: date | None = None

    index_rows: list[tuple[str, str, list[dict[str, Any]]]] = []
    for idx_id, label in (("TAIEX", "加權報酬指數"), ("TPEx", "櫃買報酬指數")):
        rows = await _get_finmind("TaiwanStockTotalReturnIndex", idx_id, start)
        index_rows.append((idx_id, label, rows))
        print(f"[industry] IDX:{idx_id} 取得 {len(rows)} 筆")

    proxy_rows: list[tuple[str, str, list[dict[str, Any]]]] = []
    for ind_name, stock_id in INDUSTRY_PROXY_STOCKS:
        rows = await _get_finmind("TaiwanStockPrice", stock_id, start)
        proxy_rows.append((ind_name, stock_id, rows))
        print(f"[industry] proxy {stock_id} ({ind_name}) 取得 {len(rows)} 筆")

    with SessionLocal() as db:
        for idx_id, label, rows in index_rows:
            for r in rows:
                d = str(r.get("date", ""))[:10]
                price = float(r.get("price") or 0)
                if not d or price <= 0:
                    continue
                _upsert_market_series(db, d, f"IDX:{idx_id}", label, "index", price, None)
                try:
                    ld = date.fromisoformat(d)
                    if latest is None or ld > latest:
                        latest = ld
                except ValueError:
                    pass

        for ind_name, stock_id, rows in proxy_rows:
            sid = f"IND:{ind_name}"
            for r in rows:
                d = str(r.get("date", ""))[:10]
                close = float(r.get("close") or 0)
                vol = int(r.get("Trading_Volume") or 0)
                if not d or close <= 0:
                    continue
                _upsert_market_series(db, d, sid, f"{ind_name}（{stock_id}）", "proxy", close, vol)
                try:
                    ld = date.fromisoformat(d)
                    if latest is None or ld > latest:
                        latest = ld
                except ValueError:
                    pass

        db.commit()

    return latest
