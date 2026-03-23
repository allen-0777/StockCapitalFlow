import asyncio
import ssl
import time
import aiohttp
from datetime import date, datetime
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models.database import SessionLocal

TWSE_BASE = "https://www.twse.com.tw/rwd/zh"

# Python 3.14 對 TWSE 憑證（缺 Subject Key Identifier）驗證失敗，略過憑證驗證
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE


async def _get_json(url: str) -> dict:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; LiquidChip/1.0)"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30), ssl=_ssl_ctx) as resp:
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
    t0 = time.monotonic()
    try:
        data = await _get_json_with_retry(f"{TWSE_BASE}/fund/BFI82U?response=json")
        trading_date = _parse_twse_date(data)

        if data.get("stat") != "OK":
            raise RuntimeError(f"TWSE BFI82U stat={data.get('stat')}")

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

        elapsed = round(time.monotonic() - t0, 1)
        print(f"[fetcher][institutional_market] done in {elapsed}s ({trading_date})")
        return trading_date
    except Exception:
        elapsed = round(time.monotonic() - t0, 1)
        print(f"[fetcher][institutional_market] ERROR in {elapsed}s")
        raise


async def fetch_institutional_stocks():
    """抓個股三大法人買賣超（bulk upsert，避免逐筆 SQL）"""
    t0 = time.monotonic()
    try:
        data = await _get_json_with_retry(f"{TWSE_BASE}/fund/T86?response=json&selectType=ALL")
        trading_date = _parse_twse_date(data)

        if data.get("stat") != "OK":
            raise RuntimeError(f"TWSE T86 stat={data.get('stat')}")

        rows_data = data.get("data", [])
        stock_params = []
        chip_params = []

        for row in rows_data:
            stock_id = row[0].strip()
            if not stock_id:
                continue
            try:
                stock_params.append({"s": stock_id, "n": row[1].strip()})
                chip_params.append({
                    "date": trading_date, "stock_id": stock_id,
                    "foreign_buy": round(_parse_num(row[4]) / 1000, 4),
                    "trust_buy":   round(_parse_num(row[10]) / 1000, 4),
                    "dealer_buy":  round(_parse_num(row[11]) / 1000, 4),
                })
            except IndexError:
                continue

        with SessionLocal() as db:
            if stock_params:
                db.execute(
                    text("INSERT INTO stocks (stock_id, name) VALUES (:s, :n) "
                         "ON CONFLICT (stock_id) DO UPDATE SET name = EXCLUDED.name"),
                    stock_params
                )
            if chip_params:
                db.execute(
                    text("INSERT INTO daily_chips (date, stock_id, foreign_buy, trust_buy, dealer_buy) "
                         "VALUES (:date, :stock_id, :foreign_buy, :trust_buy, :dealer_buy) "
                         "ON CONFLICT (date, stock_id) DO UPDATE SET "
                         "foreign_buy = EXCLUDED.foreign_buy, "
                         "trust_buy   = EXCLUDED.trust_buy, "
                         "dealer_buy  = EXCLUDED.dealer_buy"),
                    chip_params
                )
            db.commit()

        elapsed = round(time.monotonic() - t0, 1)
        print(f"[fetcher][institutional_stocks] {len(rows_data):,} 筆 in {elapsed}s ({trading_date})")
        return trading_date
    except Exception:
        elapsed = round(time.monotonic() - t0, 1)
        print(f"[fetcher][institutional_stocks] ERROR in {elapsed}s")
        raise


async def fetch_margin():
    """抓大盤融資融券餘額 → stock_id='0000'"""
    t0 = time.monotonic()
    try:
        data = await _get_json_with_retry(f"{TWSE_BASE}/marginTrading/MI_MARGN?response=json&selectType=MS")
        trading_date = _parse_twse_date(data)

        if data.get("stat") != "OK":
            raise RuntimeError(f"TWSE MI_MARGN stat={data.get('stat')}")

        margin_long_kth = 0   # 融資金額增減（千元）
        margin_short = 0      # 融券增減（張）
        for table in data.get("tables", []):
            for row in table.get("data", []):
                if "融資金額" in row[0]:  # 融資金額(仟元)
                    prev = _parse_num(row[4])
                    today_val = _parse_num(row[5])
                    margin_long_kth = int(today_val - prev)   # 千元增減
                elif "融券" in row[0] and "金額" not in row[0]:  # 融券(交易單位)
                    prev = _parse_num(row[4])
                    today_val = _parse_num(row[5])
                    margin_short = int(today_val - prev)      # 張增減

        with SessionLocal() as db:
            _upsert_chip(db, trading_date, "0000",
                         margin_long=margin_long_kth,    # 存千元，API 層轉億元
                         margin_short=margin_short)
            db.commit()

        elapsed = round(time.monotonic() - t0, 1)
        print(f"[fetcher][margin] done in {elapsed}s ({trading_date})")
        return trading_date
    except Exception:
        elapsed = round(time.monotonic() - t0, 1)
        print(f"[fetcher][margin] ERROR in {elapsed}s")
        raise


async def _get_finmind_futures_oi(futures_id: str, trade_date: str) -> dict:
    """用 FinMind 取三大法人期貨未平倉量，回傳 {身份別: {long, short}}"""
    import os
    token = os.getenv("FINMIND_TOKEN", "")
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanFuturesInstitutionalInvestors",
        "data_id": futures_id,
        "start_date": trade_date,
        "token": token,
    }
    result = {}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            body = await resp.json(content_type=None)
            for row in body.get("data", []):
                if row.get("date") == trade_date:
                    name = row["institutional_investors"]
                    result[name] = {
                        "long": row.get("long_open_interest_balance_volume", 0),
                        "short": row.get("short_open_interest_balance_volume", 0),
                    }
    return result


async def fetch_futures_oi():
    """用 FinMind 抓台指期三大法人未平倉（TX + MTX）
    自動往前找最近有數據的交易日（最多 5 日）
    """
    from datetime import timedelta

    t0 = time.monotonic()
    try:
        tx_data: dict = {}
        trade_date: str = ""
        for days_back in range(0, 5):
            d = (date.today() - timedelta(days=days_back)).strftime("%Y-%m-%d")
            tx_data = await _get_finmind_futures_oi("TX", d)
            if tx_data.get("外資", {}).get("long", 0) or tx_data.get("外資", {}).get("short", 0):
                trade_date = d
                break

        if not trade_date:
            raise RuntimeError("FinMind 近 5 日查無期貨OI數據")

        tx_foreign = tx_data.get("外資", {})
        tx_trust   = tx_data.get("投信", {})

        # --- MTX 外資（同一交易日）---
        mtx_data = await _get_finmind_futures_oi("MTX", trade_date)
        mtx_foreign = mtx_data.get("外資", {})

        db_date = datetime.strptime(trade_date, "%Y-%m-%d").date()
        with SessionLocal() as db:
            _upsert_chip(db, db_date, "0000",
                         tx_foreign_long=tx_foreign.get("long", 0),
                         tx_foreign_short=tx_foreign.get("short", 0),
                         mtx_retail_long=mtx_foreign.get("long", 0),
                         mtx_retail_short=mtx_foreign.get("short", 0),
                         trust_tx_long=tx_trust.get("long", 0),
                         trust_tx_short=tx_trust.get("short", 0))
            db.commit()

        elapsed = round(time.monotonic() - t0, 1)
        print(f"[fetcher][futures_oi] done in {elapsed}s ({trade_date})")
        return db_date
    except Exception:
        elapsed = round(time.monotonic() - t0, 1)
        print(f"[fetcher][futures_oi] ERROR in {elapsed}s")
        raise


async def fetch_options_data():
    """用 FinMind 抓選擇權三大法人 OI（外資淨金額）+ 各履約價 OI（P/C Ratio、壓力區）"""
    import os
    from datetime import timedelta
    from app.models.database import DailyOption

    t0 = time.monotonic()
    try:
        token = os.getenv("FINMIND_TOKEN", "")
        url = "https://api.finmindtrade.com/api/v4/data"

        # 找最近有數據的交易日
        trade_date = ""
        inst_rows = []
        async with aiohttp.ClientSession() as session:
            for days_back in range(0, 5):
                d = (date.today() - timedelta(days=days_back)).strftime("%Y-%m-%d")
                params = {"dataset": "TaiwanOptionInstitutionalInvestors",
                          "data_id": "TXO", "start_date": d, "token": token}
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=20)) as r:
                    body = await r.json(content_type=None)
                    rows = [row for row in body.get("data", []) if row.get("date") == d]
                    if rows:
                        trade_date = d
                        inst_rows = rows
                        break

        if not trade_date:
            raise RuntimeError("FinMind 近 5 日查無選擇權數據")

        # --- 外資選擇權淨金額（億元）---
        # long_open_interest_balance_amount - short_open_interest_balance_amount = 淨部位金額（千元）
        foreign_call_net_yi = foreign_put_net_yi = 0.0
        for row in inst_rows:
            if row["institutional_investors"] != "外資":
                continue
            net_kth = (row.get("long_open_interest_balance_amount", 0) or 0) - \
                      (row.get("short_open_interest_balance_amount", 0) or 0)
            if row["call_put"] == "買權":
                foreign_call_net_yi = round(net_kth / 100000, 2)
            elif row["call_put"] == "賣權":
                foreign_put_net_yi = round(net_kth / 100000, 2)

        # --- 各履約價 OI（P/C、壓力區）---
        pc_ratio = call_max_strike = put_max_strike = None
        call_total_oi = put_total_oi = 0
        async with aiohttp.ClientSession() as session:
            params = {"dataset": "TaiwanOptionDaily", "data_id": "TXO",
                      "start_date": trade_date, "token": token}
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as r:
                body = await r.json(content_type=None)
                all_rows = body.get("data", [])

        # 近月合約 position session
        contracts = sorted(set(row["contract_date"] for row in all_rows))
        near_month = contracts[0] if contracts else None
        if near_month:
            near = [r for r in all_rows
                    if r["contract_date"] == near_month
                    and r["trading_session"] == "position"
                    and r["open_interest"] > 0
                    and r["date"] == trade_date]
            calls = [r for r in near if r["call_put"] == "call"]
            puts  = [r for r in near if r["call_put"] == "put"]
            call_total_oi = sum(r["open_interest"] for r in calls)
            put_total_oi  = sum(r["open_interest"] for r in puts)
            if call_total_oi:
                pc_ratio = round(put_total_oi / call_total_oi * 100, 1)
            if calls:
                call_max_strike = max(calls, key=lambda x: x["open_interest"])["strike_price"]
            if puts:
                put_max_strike  = max(puts,  key=lambda x: x["open_interest"])["strike_price"]

        db_date = datetime.strptime(trade_date, "%Y-%m-%d").date()
        with SessionLocal() as db:
            existing = db.execute(
                text("SELECT date FROM daily_options WHERE date=:d"), {"d": db_date}
            ).fetchone()
            if existing:
                db.execute(text("""
                    UPDATE daily_options SET
                      pc_ratio=:pc, call_max_strike=:cs, put_max_strike=:ps,
                      call_total_oi=:co, put_total_oi=:po,
                      foreign_call_net_yi=:fcn, foreign_put_net_yi=:fpn
                    WHERE date=:d
                """), {"pc": pc_ratio, "cs": call_max_strike, "ps": put_max_strike,
                       "co": call_total_oi, "po": put_total_oi,
                       "fcn": foreign_call_net_yi, "fpn": foreign_put_net_yi,
                       "d": db_date})
            else:
                db.execute(text("""
                    INSERT INTO daily_options
                      (date, pc_ratio, call_max_strike, put_max_strike,
                       call_total_oi, put_total_oi, foreign_call_net_yi, foreign_put_net_yi)
                    VALUES (:d, :pc, :cs, :ps, :co, :po, :fcn, :fpn)
                """), {"d": db_date, "pc": pc_ratio, "cs": call_max_strike, "ps": put_max_strike,
                       "co": call_total_oi, "po": put_total_oi,
                       "fcn": foreign_call_net_yi, "fpn": foreign_put_net_yi})
            db.commit()

        elapsed = round(time.monotonic() - t0, 1)
        print(f"[fetcher][options_data] done in {elapsed}s ({trade_date})")
        return db_date
    except Exception:
        elapsed = round(time.monotonic() - t0, 1)
        print(f"[fetcher][options_data] ERROR in {elapsed}s")
        raise
