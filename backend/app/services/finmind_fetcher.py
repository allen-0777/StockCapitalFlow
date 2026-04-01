from datetime import date, timedelta
from sqlalchemy import text
from app.models.database import SessionLocal
from app.services.finmind_client import FinMindQuotaError, finmind_get, get_shared_session


async def _get_finmind(dataset: str, data_id: str, start_date: str, end_date: str = "") -> list:
    session = await get_shared_session()
    try:
        return await finmind_get(
            session, dataset, data_id, start_date, end_date, timeout=60.0
        )
    except FinMindQuotaError:
        raise RuntimeError("FinMind API 配額已用盡，請明日再試或升級方案")


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
