from datetime import date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text


def get_recent_flow(db: Session, stock_id: str, days: int = 30) -> list:
    """近 N 日各分點買賣超彙整，依淨買超絕對值排序取前20"""
    start_date = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = db.execute(
        text("""
            SELECT branch_id, branch_name,
                   SUM(buy_shares)  AS total_buy,
                   SUM(sell_shares) AS total_sell,
                   SUM(buy_shares - sell_shares) AS net_shares
            FROM broker_daily
            WHERE stock_id = :s AND date >= :d
            GROUP BY branch_id, branch_name
            ORDER BY ABS(SUM(buy_shares - sell_shares)) DESC
            LIMIT 20
        """),
        {"s": stock_id, "d": start_date}
    ).fetchall()

    return [
        {
            "branch_id":   r.branch_id,
            "branch_name": r.branch_name or r.branch_id,
            "buy_shares":  int(r.total_buy or 0),
            "sell_shares": int(r.total_sell or 0),
            "net_shares":  int(r.net_shares or 0),
        }
        for r in rows
    ]


def get_key_branches(db: Session, stock_id: str, lookforward: int = 5, days: int = 90) -> list:
    """
    回測邏輯：
    1. 找出 broker_daily 中淨買超 > 0 的所有（date, branch）記錄
    2. 對每筆買超日，找 lookforward 個交易日後的收盤價
    3. 計算報酬率，按分點分組統計勝率和平均報酬
    4. 排序：win_rate * avg_return（複合分數）
    """
    start_date = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")

    # 取所有買超記錄
    buy_rows = db.execute(
        text("""
            SELECT date, branch_id, branch_name,
                   SUM(buy_shares - sell_shares) AS net
            FROM broker_daily
            WHERE stock_id = :s AND date >= :d
            GROUP BY date, branch_id, branch_name
            HAVING net > 0
        """),
        {"s": stock_id, "d": start_date}
    ).fetchall()

    if not buy_rows:
        return []

    # 取所有股價（按日期排序供查找）
    price_rows = db.execute(
        text("""
            SELECT date, close FROM stock_prices
            WHERE stock_id = :s AND date >= :d
            ORDER BY date ASC
        """),
        {"s": stock_id, "d": start_date}
    ).fetchall()

    # 建 sorted date list + price map
    price_dates = [r.date for r in price_rows]
    price_map = {r.date: float(r.close) for r in price_rows if r.close}

    def get_future_price(buy_date: str) -> float | None:
        """找 buy_date 之後第 lookforward 個交易日的收盤價"""
        try:
            idx = price_dates.index(buy_date)
        except ValueError:
            return None
        future_idx = idx + lookforward
        if future_idx < len(price_dates):
            return price_map.get(price_dates[future_idx])
        return None

    # 統計各分點
    branch_stats: dict[str, dict] = {}
    for row in buy_rows:
        buy_date = row.date
        buy_price = price_map.get(buy_date)
        future_price = get_future_price(buy_date)

        if not buy_price or not future_price:
            continue

        ret = (future_price - buy_price) / buy_price
        bid = row.branch_id
        if bid not in branch_stats:
            branch_stats[bid] = {
                "branch_id":   bid,
                "branch_name": row.branch_name or bid,
                "returns": [],
            }
        branch_stats[bid]["returns"].append(ret)

    # 計算各分點近期淨買超（最近30日）
    recent_start = (date.today() - timedelta(days=30)).strftime("%Y-%m-%d")
    recent_rows = db.execute(
        text("""
            SELECT branch_id, SUM(buy_shares - sell_shares) AS net
            FROM broker_daily
            WHERE stock_id = :s AND date >= :d
            GROUP BY branch_id
        """),
        {"s": stock_id, "d": recent_start}
    ).fetchall()
    recent_net_map = {r.branch_id: int(r.net or 0) for r in recent_rows}

    result = []
    for bid, stats in branch_stats.items():
        returns = stats["returns"]
        if len(returns) < 2:
            continue
        win_rate = sum(1 for r in returns if r > 0) / len(returns)
        avg_return = sum(returns) / len(returns)
        score = round(win_rate * avg_return * 100, 2)  # 分數：勝率 × 平均報酬 × 100
        result.append({
            "branch_id":   bid,
            "branch_name": stats["branch_name"],
            "buy_count":   len(returns),
            "win_rate":    round(win_rate, 4),
            "avg_return":  round(avg_return, 4),
            "score":       score,
            "recent_net":  recent_net_map.get(bid, 0),
        })

    result.sort(key=lambda x: x["score"], reverse=True)
    return result[:20]
