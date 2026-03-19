import asyncio
import aiohttp
from datetime import date, datetime
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models.database import SessionLocal

TWSE_BASE = "https://www.twse.com.tw/rwd/zh"
TAIFEX_BASE = "https://www.taifex.com.tw/cht/3"


async def _get_taifex_csv(url: str) -> str:
    """抓 TAIFEX CSV（big5 編碼）"""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; LiquidChip/1.0)"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            resp.raise_for_status()
            raw = await resp.read()
            return raw.decode("cp950", errors="replace")


def _parse_taifex_oi(text: str) -> dict:
    """
    解析 TAIFEX 期貨未平倉 CSV → {身份別: {long: int, short: int}}
    欄位順序（0-indexed）：
      0:日期, 1:商品, 2:身份別,
      3:多方交易口數, 4:多方金額, 5:空方交易口數, 6:空方金額,
      7:淨額口數, 8:淨額金額,
      9:多方未平倉口數, 10:多方未平倉金額,
      11:空方未平倉口數, 12:空方未平倉金額,
      13:淨額未平倉口數, 14:淨額未平倉金額
    """
    result = {}
    for line in text.splitlines():
        parts = [p.strip().strip('"') for p in line.split(",")]
        if len(parts) < 12:
            continue
        # 資料列：第一欄含 "/"（日期格式 yyyy/mm/dd）
        if "/" not in parts[0]:
            continue
        identity = parts[2]
        if not identity:
            continue
        try:
            long_oi = int(parts[9].replace(",", "") or "0")
            short_oi = int(parts[11].replace(",", "") or "0")
            result[identity] = {"long": long_oi, "short": short_oi}
        except (ValueError, IndexError):
            continue
    return result


async def _fetch_taifex_oi(commodity_id: str, query_type: int = 1) -> dict:
    url = (
        f"{TAIFEX_BASE}/futContractsDateDown"
        f"?queryType={query_type}&marketCode=0&dateaddcnt=0"
        f"&commodity_id={commodity_id}&seqno=&dutch=1"
    )
    text = await _get_taifex_csv(url)
    return _parse_taifex_oi(text)


async def _get_json(url: str) -> dict:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; LiquidChip/1.0)"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            resp.raise_for_status()
            return await resp.json(content_type=None)


async def _get_json_with_retry(url: str, max_retries: int = 3) -> dict:
    for attempt in range(max_retries):
        try:
            return await _get_json(url)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt
            print(f"[fetcher] retry {attempt + 1}/{max_retries - 1} after {wait}s: {e}")
            await asyncio.sleep(wait)


def _parse_twse_date(data: dict) -> date:
    """從 TWSE API 回應中解析實際交易日期（格式：YYYYMMDD），fallback 為今日"""
    raw = data.get("date") or data.get("Date")
    if raw:
        try:
            return datetime.strptime(str(raw), "%Y%m%d").date()
        except ValueError:
            pass
    return date.today()


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
    data = await _get_json_with_retry(f"{TWSE_BASE}/fund/BFI82U?response=json")
    trading_date = _parse_twse_date(data)

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
        _upsert_chip(db, trading_date, "0000",
                     foreign_buy=round(foreign_buy, 2),
                     trust_buy=round(trust_buy, 2),
                     dealer_buy=round(dealer_buy, 2))
        db.commit()

    print(f"[fetcher] 大盤法人 done ({trading_date}): 外資={foreign_buy:.2f}億 投信={trust_buy:.2f}億 自營={dealer_buy:.2f}億")


async def fetch_institutional_stocks():
    """抓個股三大法人買賣超"""
    data = await _get_json_with_retry(f"{TWSE_BASE}/fund/T86?response=json&selectType=ALL")
    trading_date = _parse_twse_date(data)

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
            _upsert_chip(db, trading_date, stock_id,
                         foreign_buy=round(foreign_net, 4),
                         trust_buy=round(trust_net, 4),
                         dealer_buy=round(dealer_net, 4))
        db.commit()

    print(f"[fetcher] 個股法人 done ({trading_date}): {len(rows_data)} 筆")


async def fetch_margin():
    """抓大盤融資融券餘額 → stock_id='0000'"""
    data = await _get_json_with_retry(f"{TWSE_BASE}/marginTrading/MI_MARGN?response=json&selectType=MS")
    trading_date = _parse_twse_date(data)

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
        _upsert_chip(db, trading_date, "0000",
                     margin_long=margin_long,
                     margin_short=margin_short)
        db.commit()

    print(f"[fetcher] 融資券 done ({trading_date}): 融資={margin_long} 融券={margin_short}")


async def fetch_futures_oi():
    """抓台指期(TX)外資未平倉多空 & 小台(MTX)散戶未平倉多空"""
    today = date.today()

    # --- TX 外資 ---
    tx_data = await _fetch_taifex_oi("TX", query_type=1)
    foreign_key = next((k for k in tx_data if "外資" in k), None)
    tx_foreign_long = tx_data[foreign_key]["long"] if foreign_key else 0
    tx_foreign_short = tx_data[foreign_key]["short"] if foreign_key else 0

    # --- MTX 散戶 = 全市場 - 三大法人 ---
    # queryType=1 → 三大法人明細（可能含「合計」列）
    mtx_inst = await _fetch_taifex_oi("MTX", query_type=1)

    # 嘗試從 queryType=2 取全市場（自然人專屬 CSV）
    mtx_natural = await _fetch_taifex_oi("MTX", query_type=2)
    natural_key = next((k for k in mtx_natural if "自然人" in k or "散戶" in k), None)

    if natural_key:
        # TAIFEX 直接提供自然人資料
        mtx_retail_long = mtx_natural[natural_key]["long"]
        mtx_retail_short = mtx_natural[natural_key]["short"]
    else:
        # Fallback：用「合計」減法人，估算散戶
        total_key = next((k for k in mtx_inst if "合計" in k or "全市場" in k), None)
        if total_key:
            total_long = mtx_inst[total_key]["long"]
            total_short = mtx_inst[total_key]["short"]
            inst_long = sum(
                mtx_inst.get(k, {}).get("long", 0)
                for k in ["自營商", "投信"] + ([foreign_key] if foreign_key else [])
                if k in mtx_inst
            )
            inst_short = sum(
                mtx_inst.get(k, {}).get("short", 0)
                for k in ["自營商", "投信"] + ([foreign_key] if foreign_key else [])
                if k in mtx_inst
            )
            mtx_retail_long = max(0, total_long - inst_long)
            mtx_retail_short = max(0, total_short - inst_short)
        else:
            mtx_retail_long = mtx_retail_short = 0

    with SessionLocal() as db:
        _upsert_chip(db, today, "0000",
                     tx_foreign_long=tx_foreign_long,
                     tx_foreign_short=tx_foreign_short,
                     mtx_retail_long=mtx_retail_long,
                     mtx_retail_short=mtx_retail_short)
        db.commit()

    print(
        f"[fetcher] 期貨OI done: "
        f"外資TX 多{tx_foreign_long}/空{tx_foreign_short}, "
        f"散戶MTX 多{mtx_retail_long}/空{mtx_retail_short}"
    )
