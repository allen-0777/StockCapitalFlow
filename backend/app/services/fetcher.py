import asyncio
import logging
import math
import ssl
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

import aiohttp
import certifi
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models.database import SessionLocal

TWSE_BASE = "https://www.twse.com.tw/rwd/zh"
TAIFEX_BASE = "https://openapi.taifex.com.tw/v1"

# Python 3.14 的嚴格檢查拒絕 TWSE 缺 Subject Key Identifier 的憑證。
# 僅關閉 VERIFY_X509_STRICT，保留 CA 驗證與主機名稱檢查。
_ssl_ctx = ssl.create_default_context(cafile=certifi.where())
_ssl_ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
_logger = logging.getLogger(__name__)


def _valid_rows(rows, numeric_indices=(), numeric_keys=(), target_date=None):
    rejected = 0
    for row in rows:
        try:
            if target_date and row.get("Date") != target_date:
                raise ValueError("mismatched date")
            for index in numeric_indices:
                if _parse_num(row[index]) is None:
                    raise ValueError("invalid number")
            for key in numeric_keys:
                if _parse_num(row.get(key)) is None:
                    raise ValueError("invalid number")
            yield row
        except (ValueError, IndexError, KeyError, TypeError, AttributeError):
            rejected += 1
    if rejected:
        _logger.warning("Rejected %d malformed rows", rejected)


def _taipei_today():
    return datetime.now(ZoneInfo("Asia/Taipei")).date()


async def _get_json(url: str) -> dict:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; LiquidChip/1.0)"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30), ssl=_ssl_ctx) as resp:
            resp.raise_for_status()
            return await resp.json(content_type=None)


async def _get_taifex_openapi(path: str) -> list:
    """打期交所 OpenAPI v1，回傳 list[dict]。
    注意：實測 OpenAPI 於「次一日清晨約 06:30」才更新（Last-Modified），
    17:30 排程時常仍是前一交易日資料，因此僅作為官網 CSV 的備援。
    """
    headers = {"User-Agent": "Mozilla/5.0 (compatible; LiquidChip/1.0)"}
    url = f"{TAIFEX_BASE}{path}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            resp.raise_for_status()
            return await resp.json(content_type=None)


# 官網「三大法人」CSV 下載（約 15:00 後公布當日資料，且支援日期區間查詢，可用於補歷史）
# 欄位依序對應到 OpenAPI 的 key，讓下游解析邏輯不必改。
TAIFEX_WEB_BASE = "https://www.taifex.com.tw/cht/3"
TAIFEX_WEB_SOURCES = {
    "/MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate": (
        "futContractsDateDown", {"commodityId": ""},
        {0: "Date", 1: "ContractCode", 2: "Item",
         9: "OpenInterest(Long)", 11: "OpenInterest(Short)"},
    ),
    "/MarketDataOfMajorInstitutionalTradersDetailsOfCallsAndPutsBytheDate": (
        "callsAndPutsDateDown", {"commodityId": "TXO"},
        {0: "Date", 1: "ContractCode", 2: "CallPut", 3: "Item",
         11: "ContractValueofOpenInterest(Long)(Thousands)",
         13: "ContractValueofOpenInterest(Short)(Thousands)"},
    ),
}
TAIFEX_WEB_LOOKBACK_DAYS = 10


def _parse_taifex_csv(raw: bytes, columns: dict) -> list:
    """解析官網 CSV（MS950 編碼）。查無資料時官網回 HTML，視為空結果。"""
    body = raw.decode("cp950", errors="replace")
    if body.lstrip().startswith("<"):
        return []
    rows = []
    for line in body.splitlines()[1:]:
        cells = [c.strip() for c in line.split(",")]
        if len(cells) <= max(columns):
            continue
        row = {key: cells[i] for i, key in columns.items()}
        row["Date"] = row["Date"].replace("/", "")
        rows.append(row)
    return rows


async def _get_taifex_web(path: str, day: date) -> list:
    """查官網單日 CSV。注意：查詢區間只要包含尚未公布的日期，官網就整批回 HTML（查無資料），
    所以只能逐日查。"""
    page, extra, columns = TAIFEX_WEB_SOURCES[path]
    form = {"queryStartDate": day.strftime("%Y/%m/%d"),
            "queryEndDate": day.strftime("%Y/%m/%d"), **extra}
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                             "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"}
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{TAIFEX_WEB_BASE}/{page}", data=form, headers=headers,
                                timeout=aiohttp.ClientTimeout(total=30), ssl=_ssl_ctx) as resp:
            resp.raise_for_status()
            return _parse_taifex_csv(await resp.read(), columns)


async def _get_taifex_web_latest(path: str) -> list:
    """由今天往回逐日查官網 CSV，回傳最新一個有資料的交易日。"""
    from datetime import timedelta

    today = _taipei_today()
    for back in range(TAIFEX_WEB_LOOKBACK_DAYS):
        day = today - timedelta(days=back)
        if day.weekday() >= 5:
            continue
        rows = await _get_taifex_web(path, day)
        if rows:
            return rows
    return []


async def _get_taifex_json(path: str) -> list:
    """回傳期交所「最新交易日」的資料（OpenAPI 格式的 list[dict]，只含單一日期）。
    先打官網 CSV（當日約 15:00 後即有），失敗或較舊時改用 OpenAPI，取兩者較新的日期。
    """
    web_rows: list = []
    if path in TAIFEX_WEB_SOURCES:
        try:
            web_rows = await _get_taifex_web_latest(path)
        except Exception as e:  # 官網偶有擋爬或維護，退回 OpenAPI
            _logger.warning("TAIFEX web CSV failed for %s: %s", path, e)
    api_rows: list = []
    try:
        api_rows = await _get_taifex_openapi(path)
    except Exception as e:
        if not web_rows:
            raise
        _logger.warning("TAIFEX OpenAPI failed for %s: %s", path, e)

    web_latest = max((r["Date"] for r in web_rows), default="")
    api_latest = api_rows[0]["Date"] if api_rows else ""
    if web_latest and web_latest >= api_latest:
        print(f"[fetcher][taifex] web CSV {web_latest} (OpenAPI={api_latest or 'n/a'})")
        return [r for r in web_rows if r["Date"] == web_latest]
    return api_rows


async def _get_json_with_retry(url: str, max_retries: int = 3) -> dict:
    for attempt in range(max_retries):
        try:
            return await _get_json(url)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
            # ValueError：TWSE 限流時回 HTML 而非 JSON（JSONDecodeError），稍等再試
            if attempt == max_retries - 1:
                raise
            wait = 5 * 2 ** attempt
            print(f"[fetcher] retry {attempt + 1}/{max_retries - 1} after {wait}s: {e}")
            await asyncio.sleep(wait)


def _parse_twse_date(data: dict) -> date:
    """解析實際交易日；無效日期拒絕寫入。"""
    raw = data.get("date") or data.get("Date")
    try:
        if len(str(raw)) != 8:
            raise ValueError("Expected YYYYMMDD")
        return datetime.strptime(str(raw), "%Y%m%d").date()
    except ValueError:
        _logger.warning("Rejected payload with invalid TWSE date: %r", raw)
        raise ValueError(f"Invalid TWSE date: {raw!r}") from None


def _parse_roc_date(raw) -> date:
    """民國日期 '115/10/20' → date(2026, 10, 20)；無效則拒絕。"""
    try:
        y, m, d = (int(x) for x in str(raw).strip().split("/"))
        return date(y + 1911, m, d)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid ROC date: {raw!r}") from None


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


def _parse_num(s) -> float | None:
    if s is None:
        return None
    if str(s).strip() in ("", "--", "-", "---"):
        return 0.0  # 官方空白欄位表示無交易／無餘額
    try:
        value = float(str(s).replace(",", "").replace(" ", ""))
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


async def fetch_institutional_market():
    """抓大盤三大法人買賣超 → stock_id='0000'"""
    t0 = time.monotonic()
    try:
        data = await _get_json_with_retry(f"{TWSE_BASE}/fund/BFI82U?response=json")
        trading_date = _parse_twse_date(data)

        if data.get("stat") != "OK":
            raise RuntimeError(f"TWSE BFI82U stat={data.get('stat')}")

        foreign_buy = trust_buy = dealer_buy = None
        for row in _valid_rows(data.get("data", []), (3,)):
            name = row[0]
            net = _parse_num(row[3]) / 1e8  # 元 → 億
            if "外資及陸資" in name:
                foreign_buy = (foreign_buy or 0.0) + net
            elif "投信" in name:
                trust_buy = net
            elif "自營商" in name:
                dealer_buy = (dealer_buy or 0.0) + net

        values = {key: round(value, 2) for key, value in {
            "foreign_buy": foreign_buy, "trust_buy": trust_buy, "dealer_buy": dealer_buy,
        }.items() if value is not None}
        if not values:
            raise ValueError("No valid institutional market rows")
        with SessionLocal() as db:
            _upsert_chip(db, trading_date, "0000", **values)
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

        for row in _valid_rows(rows_data, (4, 10, 11)):
            stock_id = str(row[0]).strip()
            if not stock_id:
                continue
            try:
                stock_params.append({"s": stock_id, "n": str(row[1]).strip()})
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

        margin_long_kth = None   # 融資金額增減（千元）
        margin_short = None      # 融券增減（張）
        for table in data.get("tables", []):
            for row in _valid_rows(table.get("data", []), (4, 5)):
                if "融資金額" in row[0]:  # 融資金額(仟元)
                    prev = _parse_num(row[4])
                    today_val = _parse_num(row[5])
                    margin_long_kth = int(today_val - prev)   # 千元增減
                elif "融券" in row[0] and "金額" not in row[0]:  # 融券(交易單位)
                    prev = _parse_num(row[4])
                    today_val = _parse_num(row[5])
                    margin_short = int(today_val - prev)      # 張增減

        values = {key: value for key, value in {
            "margin_long": margin_long_kth, "margin_short": margin_short,
        }.items() if value is not None}
        if not values:
            raise ValueError("No valid margin rows")
        with SessionLocal() as db:
            _upsert_chip(db, trading_date, "0000", **values)
            db.commit()

        elapsed = round(time.monotonic() - t0, 1)
        print(f"[fetcher][margin] done in {elapsed}s ({trading_date})")
        return trading_date
    except Exception:
        elapsed = round(time.monotonic() - t0, 1)
        print(f"[fetcher][margin] ERROR in {elapsed}s")
        raise


async def fetch_futures_oi():
    """用 TAIFEX OpenAPI 抓台指期/小台期三大法人未平倉（當日盤後即有，無需 token）
    ContractCode: 臺股期貨=TX, 小型臺指期貨=MTX
    Item: 外資及陸資, 投信, 自營商
    """
    t0 = time.monotonic()
    try:
        rows = await _get_taifex_json("/MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate")
        if not rows:
            raise RuntimeError("TAIFEX 期貨三大法人 API 回傳空資料")

        trade_date_str = rows[0]["Date"]  # "YYYYMMDD"
        db_date = datetime.strptime(trade_date_str, "%Y%m%d").date()

        tx_foreign = tx_trust = mtx_foreign = None
        for row in _valid_rows(
            rows, numeric_keys=("OpenInterest(Long)", "OpenInterest(Short)"),
            target_date=trade_date_str,
        ):
            code = row["ContractCode"]
            item = row["Item"]
            if code == "臺股期貨" and item == "外資及陸資":
                tx_foreign = row
            elif code == "臺股期貨" and item == "投信":
                tx_trust = row
            elif code == "小型臺指期貨" and item == "外資及陸資":
                mtx_foreign = row

        if not tx_foreign:
            raise RuntimeError(f"TAIFEX 找不到臺股期貨外資資料 (date={trade_date_str})")

        def _oi(row, side):
            return int(_parse_num(row[f"OpenInterest({side})"])) if row else None

        values = {
            "tx_foreign_long": _oi(tx_foreign, "Long"),
            "tx_foreign_short": _oi(tx_foreign, "Short"),
            "mtx_retail_long": _oi(mtx_foreign, "Long"),
            "mtx_retail_short": _oi(mtx_foreign, "Short"),
            "trust_tx_long": _oi(tx_trust, "Long"),
            "trust_tx_short": _oi(tx_trust, "Short"),
        }
        with SessionLocal() as db:
            _upsert_chip(db, db_date, "0000",
                         **{key: value for key, value in values.items() if value is not None})
            db.commit()

        elapsed = round(time.monotonic() - t0, 1)
        print(f"[fetcher][futures_oi] done in {elapsed}s ({db_date})")
        return db_date
    except Exception:
        elapsed = round(time.monotonic() - t0, 1)
        print(f"[fetcher][futures_oi] ERROR in {elapsed}s")
        raise


async def fetch_options_data():
    """選擇權資料：
    - 外資 Call/Put 淨部位金額 → TAIFEX OpenAPI（當日盤後即有，與法人買賣超同步）
    - P/C Ratio、壓力區（各履約價 OI） → FinMind TaiwanOptionDaily（可能延遲數日）
    db_date 以 TAIFEX 當日為準，僅填入同日 FinMind 資料。
    """
    from datetime import timedelta

    t0 = time.monotonic()
    try:
        # --- 1. 外資選擇權淨金額 from TAIFEX OpenAPI ---
        opt_rows = await _get_taifex_json("/MarketDataOfMajorInstitutionalTradersDetailsOfCallsAndPutsBytheDate")
        if not opt_rows:
            raise RuntimeError("TAIFEX 選擇權三大法人 API 回傳空資料")

        trade_date_str = opt_rows[0]["Date"]  # "YYYYMMDD"
        db_date = datetime.strptime(trade_date_str, "%Y%m%d").date()

        foreign_call_net_yi = foreign_put_net_yi = None
        for row in _valid_rows(
            opt_rows,
            numeric_keys=("ContractValueofOpenInterest(Long)(Thousands)",
                          "ContractValueofOpenInterest(Short)(Thousands)"),
            target_date=trade_date_str,
        ):
            if row["ContractCode"] != "臺指選擇權" or row["Item"] != "外資及陸資":
                continue
            long_kth  = _parse_num(row.get("ContractValueofOpenInterest(Long)(Thousands)", "0"))
            short_kth = _parse_num(row.get("ContractValueofOpenInterest(Short)(Thousands)", "0"))
            net_kth = long_kth - short_kth
            if row["CallPut"] == "CALL":
                foreign_call_net_yi = round(net_kth / 100000, 2)
            elif row["CallPut"] == "PUT":
                foreign_put_net_yi = round(net_kth / 100000, 2)

        if foreign_call_net_yi is None and foreign_put_net_yi is None:
            raise ValueError("No valid TAIFEX option rows")

        # --- 2. P/C Ratio、壓力區 from FinMind（best-effort，可能落後數日）---
        from app.services.finmind_client import finmind_get, get_shared_session

        pc_ratio = call_max_strike = put_max_strike = None
        call_total_oi = put_total_oi = None
        finmind_date = ""

        # 直接查 TAIFEX 的交易日：過去從「今天」往回找，盤中 FinMind 已有今日
        # （夜盤歸屬次一交易日）資料，會選到今天而與 TAIFEX 日期不符，P/C 永遠被略過。
        session = await get_shared_session()
        d = db_date.isoformat()
        body_rows = await finmind_get(
            session,
            "TaiwanOptionDaily",
            "TXO",
            d,
            timeout=30.0,
            token_in_query=True,
        )
        all_rows = [row for row in body_rows if row.get("date") == d]
        if any(row.get("trading_session") == "position" for row in all_rows):
            finmind_date = d

        if finmind_date and finmind_date != db_date.isoformat():
            _logger.warning("Skipping FinMind options date %s for TAIFEX %s", finmind_date, db_date)

        if finmind_date == db_date.isoformat():
            contracts = sorted(set(row["contract_date"] for row in all_rows))
            near_month = contracts[0] if contracts else None
            if near_month:
                near = [r for r in all_rows
                        if r["contract_date"] == near_month
                        and r["trading_session"] == "position"
                        and r["open_interest"] > 0
                        and r["date"] == finmind_date]
                calls = [r for r in near if r["call_put"] == "call"]
                puts  = [r for r in near if r["call_put"] == "put"]
                call_total_oi = sum(r["open_interest"] for r in calls) if calls else None
                put_total_oi = sum(r["open_interest"] for r in puts) if puts else None
                if call_total_oi and put_total_oi is not None:
                    pc_ratio = round(put_total_oi / call_total_oi * 100, 1)
                if calls:
                    call_max_strike = max(calls, key=lambda x: x["open_interest"])["strike_price"]
                if puts:
                    put_max_strike  = max(puts,  key=lambda x: x["open_interest"])["strike_price"]

        with SessionLocal() as db:
            existing = db.execute(
                text("SELECT date FROM daily_options WHERE date=:d"), {"d": db_date}
            ).fetchone()
            if existing:
                db.execute(text("""
                    UPDATE daily_options SET
                      pc_ratio=COALESCE(:pc, pc_ratio), call_max_strike=COALESCE(:cs, call_max_strike), put_max_strike=COALESCE(:ps, put_max_strike),
                      call_total_oi=COALESCE(:co, call_total_oi), put_total_oi=COALESCE(:po, put_total_oi),
                      foreign_call_net_yi=COALESCE(:fcn, foreign_call_net_yi), foreign_put_net_yi=COALESCE(:fpn, foreign_put_net_yi)
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
        print(f"[fetcher][options_data] TAIFEX={db_date} FinMind_PC={finmind_date or 'n/a'} in {elapsed}s")
        return db_date
    except Exception:
        elapsed = round(time.monotonic() - t0, 1)
        print(f"[fetcher][options_data] ERROR in {elapsed}s")
        raise


async def fetch_turnover():
    """抓大盤成交金額（億元） → stock_id='0000' market_volume 欄位"""
    t0 = time.monotonic()
    try:
        now_str = _taipei_today().strftime("%Y%m%d")
        data = await _get_json_with_retry(
            f"{TWSE_BASE}/afterTrading/FMTQIK?date={now_str}&response=json"
        )
        if data.get("stat") != "OK" or not data.get("data"):
            raise RuntimeError(f"TWSE FMTQIK stat={data.get('stat')}")

        # 取最後一筆（最新交易日）；日期取該列的民國日期（data["date"] 只是查詢日，盤中會是今天）
        last = data["data"][-1]
        valid_rows = list(_valid_rows([last], (2,)))
        if not valid_rows:
            raise ValueError("Invalid turnover")
        trading_date = _parse_roc_date(last[0])
        # 成交金額欄位（元），轉億
        volume = _parse_num(valid_rows[0][2])
        volume_yi = round(volume / 1e8, 2)

        with SessionLocal() as db:
            _upsert_chip(db, trading_date, "0000", market_volume=volume_yi)
            db.commit()

        elapsed = round(time.monotonic() - t0, 1)
        print(f"[fetcher][turnover] {volume_yi}億 in {elapsed}s ({trading_date})")
        return trading_date
    except Exception:
        elapsed = round(time.monotonic() - t0, 1)
        print(f"[fetcher][turnover] ERROR in {elapsed}s")
        raise


async def fetch_exchange_rate(start: date | None = None):
    """台銀美金現金買入/賣出匯率（FinMind TaiwanExchangeRate，資料來源同台銀牌告）。
    台銀網站對 GitHub runner 回傳 WAF 驗證頁，無法直接爬取；FinMind 一次請求可取整段區間，
    預設抓近 10 天（補漏），start 指定時從該日起回補。回傳最新資料日。"""
    from datetime import timedelta
    from app.services.finmind_client import finmind_get, get_shared_session

    t0 = time.monotonic()
    try:
        start = start or (_taipei_today() - timedelta(days=10))
        session = await get_shared_session()
        rows = await finmind_get(session, "TaiwanExchangeRate", "USD", start.isoformat())
        params = []
        for r in rows:
            try:
                d = date.fromisoformat(str(r["date"])[:10])
                buy, sell = float(r["cash_buy"]), float(r["cash_sell"])
            except (KeyError, TypeError, ValueError):
                continue
            if buy > 0 and sell > 0:
                params.append({"d": d, "b": buy, "s": sell})
        if not params:
            raise RuntimeError(f"FinMind TaiwanExchangeRate 無有效資料（start={start}）")

        with SessionLocal() as db:
            db.execute(
                text("INSERT INTO daily_exchange_rate (date, usd_buy, usd_sell) VALUES (:d, :b, :s) "
                     "ON CONFLICT (date) DO UPDATE SET usd_buy = EXCLUDED.usd_buy, usd_sell = EXCLUDED.usd_sell"),
                params,
            )
            db.commit()

        latest = max(p["d"] for p in params)
        last = next(p for p in params if p["d"] == latest)
        elapsed = round(time.monotonic() - t0, 1)
        print(f"[fetcher][exchange_rate] {len(params)} 天，最新 {latest} USD buy={last['b']} sell={last['s']} in {elapsed}s")
        return latest
    except Exception:
        elapsed = round(time.monotonic() - t0, 1)
        print(f"[fetcher][exchange_rate] ERROR in {elapsed}s")
        raise


async def sync_stock_industries():
    from app.services.industry_sync import sync_stock_industries as _sync

    return await _sync()


async def sync_market_series_daily():
    from app.services.industry_sync import sync_market_series_daily as _sync

    return await _sync()
