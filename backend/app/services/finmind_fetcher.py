import os
import aiohttp
from datetime import date, timedelta
from sqlalchemy import text
from app.models.database import SessionLocal

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"


def _token() -> str:
    return os.getenv("FINMIND_TOKEN", "")


async def _get_finmind(dataset: str, data_id: str, start_date: str, end_date: str = "") -> list:
    params = {
        "dataset":    dataset,
        "data_id":    data_id,
        "start_date": start_date,
    }
    if end_date:
        params["end_date"] = end_date

    headers = {
        "User-Agent":    "Mozilla/5.0 (compatible; LiquidChip/1.0)",
        "Authorization": f"Bearer {_token()}",
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(
            FINMIND_URL, params=params, headers=headers,
            timeout=aiohttp.ClientTimeout(total=60)
        ) as resp:
            if resp.status == 402:
                raise RuntimeError("FinMind API 配額已用盡，請明日再試或升級方案")
            resp.raise_for_status()
            body = await resp.json(content_type=None)
            return body.get("data", [])


async def fetch_broker_daily(stock_id: str, days: int = 90) -> int:
    """抓 FinMind TaiwanStockTradingDailyReport → broker_daily"""
    start_date = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = await _get_finmind("TaiwanStockTradingDailyReport", stock_id, start_date)

    if not rows:
        print(f"[finmind] TaiwanStockTradingDailyReport stock={stock_id} 無資料")
        return 0

    with SessionLocal() as db:
        for row in rows:
            d           = str(row.get("date", ""))[:10]
            branch_id   = str(row.get("securities_trader_id", "")).strip()
            branch_name = str(row.get("securities_trader", "")).strip()
            buy_shares  = int(row.get("buy",  0) or 0)
            sell_shares = int(row.get("sell", 0) or 0)
            if not branch_id or not d:
                continue
            existing = db.execute(
                text("SELECT branch_id FROM broker_daily WHERE date=:d AND stock_id=:s AND branch_id=:b"),
                {"d": d, "s": stock_id, "b": branch_id}
            ).fetchone()
            if existing:
                db.execute(
                    text("""UPDATE broker_daily
                            SET branch_name=:n, buy_shares=:buy, sell_shares=:sell
                            WHERE date=:d AND stock_id=:s AND branch_id=:b"""),
                    {"n": branch_name, "buy": buy_shares, "sell": sell_shares,
                     "d": d, "s": stock_id, "b": branch_id}
                )
            else:
                db.execute(
                    text("""INSERT INTO broker_daily
                            (date, stock_id, branch_id, branch_name, buy_shares, sell_shares)
                            VALUES (:d, :s, :b, :n, :buy, :sell)"""),
                    {"d": d, "s": stock_id, "b": branch_id, "n": branch_name,
                     "buy": buy_shares, "sell": sell_shares}
                )
        db.commit()

    print(f"[finmind] broker_daily stock={stock_id} done: {len(rows)} 筆")
    return len(rows)


async def fetch_stock_price(stock_id: str, days: int = 100) -> int:
    """抓 FinMind TaiwanStockPrice → stock_prices（供回測用）"""
    start_date = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = await _get_finmind("TaiwanStockPrice", stock_id, start_date)

    if not rows:
        print(f"[finmind] TaiwanStockPrice stock={stock_id} 無資料")
        return 0

    with SessionLocal() as db:
        for row in rows:
            d      = str(row.get("date", ""))[:10]
            close  = float(row.get("close",           0) or 0)
            volume = int(row.get("Trading_Volume",    0) or 0)
            if not d:
                continue
            existing = db.execute(
                text("SELECT stock_id FROM stock_prices WHERE date=:d AND stock_id=:s"),
                {"d": d, "s": stock_id}
            ).fetchone()
            if existing:
                db.execute(
                    text("UPDATE stock_prices SET close=:c, volume=:v WHERE date=:d AND stock_id=:s"),
                    {"c": close, "v": volume, "d": d, "s": stock_id}
                )
            else:
                db.execute(
                    text("INSERT INTO stock_prices (date, stock_id, close, volume) VALUES (:d, :s, :c, :v)"),
                    {"d": d, "s": stock_id, "c": close, "v": volume}
                )
        db.commit()

    print(f"[finmind] stock_prices stock={stock_id} done: {len(rows)} 筆")
    return len(rows)
