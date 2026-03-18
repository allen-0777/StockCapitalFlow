import aiohttp
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models.database import SessionLocal

TWSE_BASE = "https://www.twse.com.tw/rwd/zh"


async def _get_json(url: str) -> dict:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; LiquidChip/1.0)"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            resp.raise_for_status()
            return await resp.json(content_type=None)


def _upsert_chip(db: Session, today: date, stock_id: str, **kwargs):
    existing = db.execute(
        text("SELECT stock_id FROM daily_chips WHERE date=:d AND stock_id=:s"),
        {"d": today, "s": stock_id}
    ).fetchone()
    if existing:
        sets = ", ".join(f"{k}=:{k}" for k in kwargs)
        db.execute(
            text(f"UPDATE daily_chips SET {sets} WHERE date=:date AND stock_id=:stock_id"),
            {"date": today, "stock_id": stock_id, **kwargs}
        )
    else:
        cols = ", ".join(["date", "stock_id"] + list(kwargs.keys()))
        vals = ", ".join([":date", ":stock_id"] + [f":{k}" for k in kwargs])
        db.execute(
            text(f"INSERT INTO daily_chips ({cols}) VALUES ({vals})"),
            {"date": today, "stock_id": stock_id, **kwargs}
        )


def _parse_num(s: str) -> float:
    try:
        return float(s.replace(",", "").replace(" ", ""))
    except (ValueError, AttributeError):
        return 0.0


async def fetch_institutional_market():
    """抓大盤三大法人買賣超 → stock_id='0000'"""
    data = await _get_json(f"{TWSE_BASE}/fund/BFI82U?response=json")
    today = date.today()

    if data.get("stat") != "OK":
        print(f"[fetcher] BFI82U stat={data.get('stat')}, skipping")
        return

    foreign_buy = trust_buy = dealer_buy = 0.0
    for row in data.get("data", []):
        name = row[0]
        net = _parse_num(row[3]) / 1e8  # 元 → 億
        if "外資及陸資" in name:
            foreign_buy += net
        elif "投信" in name:
            trust_buy = net
        elif "自營商" in name:
            dealer_buy += net

    with SessionLocal() as db:
        _upsert_chip(db, today, "0000",
                     foreign_buy=round(foreign_buy, 2),
                     trust_buy=round(trust_buy, 2),
                     dealer_buy=round(dealer_buy, 2))
        db.commit()

    print(f"[fetcher] 大盤法人 done: 外資={foreign_buy:.2f}億 投信={trust_buy:.2f}億 自營={dealer_buy:.2f}億")


async def fetch_institutional_stocks():
    """抓個股三大法人買賣超"""
    data = await _get_json(f"{TWSE_BASE}/fund/T86?response=json&selectType=ALL")
    today = date.today()

    if data.get("stat") != "OK":
        print(f"[fetcher] T86 stat={data.get('stat')}, skipping")
        return

    # fields: 證券代號, 證券名稱, 外陸資買進, 外陸資賣出, 外陸資買賣超, 外資自營買進, 外資自營賣出, 外資自營買賣超,
    #         投信買進, 投信賣出, 投信買賣超, 自營買賣超, 自營買進, 自營賣出, 三大法人買賣超
    rows_data = data.get("data", [])
    with SessionLocal() as db:
        for row in rows_data:
            stock_id = row[0].strip()
            if not stock_id:
                continue
            try:
                stock_name = row[1].strip()
                foreign_net = _parse_num(row[4]) / 1000
                trust_net = _parse_num(row[10]) / 1000
                dealer_net = _parse_num(row[11]) / 1000
            except IndexError:
                continue
            # upsert 股票名稱
            exists = db.execute(text("SELECT stock_id FROM stocks WHERE stock_id=:s"), {"s": stock_id}).fetchone()
            if exists:
                db.execute(text("UPDATE stocks SET name=:n WHERE stock_id=:s"), {"n": stock_name, "s": stock_id})
            else:
                db.execute(text("INSERT INTO stocks (stock_id, name) VALUES (:s, :n)"), {"s": stock_id, "n": stock_name})
            _upsert_chip(db, today, stock_id,
                         foreign_buy=round(foreign_net, 4),
                         trust_buy=round(trust_net, 4),
                         dealer_buy=round(dealer_net, 4))
        db.commit()

    print(f"[fetcher] 個股法人 done: {len(rows_data)} 筆")


async def fetch_margin():
    """抓大盤融資融券餘額 → stock_id='0000'"""
    data = await _get_json(f"{TWSE_BASE}/marginTrading/MI_MARGN?response=json&selectType=MS")
    today = date.today()

    if data.get("stat") != "OK":
        print(f"[fetcher] MI_MARGN stat={data.get('stat')}, skipping")
        return

    margin_long = margin_short = 0
    for table in data.get("tables", []):
        for row in table.get("data", []):
            if "融資" in row[0] and "金額" not in row[0]:
                prev = _parse_num(row[4])
                today_val = _parse_num(row[5])
                margin_long = int(today_val - prev)   # 今日增減（正=增加=多頭）
            elif "融券" in row[0]:
                prev = _parse_num(row[4])
                today_val = _parse_num(row[5])
                margin_short = int(today_val - prev)  # 今日增減（正=增加=空頭）

    with SessionLocal() as db:
        _upsert_chip(db, today, "0000",
                     margin_long=margin_long,
                     margin_short=margin_short)
        db.commit()

    print(f"[fetcher] 融資券 done: 融資={margin_long} 融券={margin_short}")
