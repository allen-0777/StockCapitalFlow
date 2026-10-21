from sqlalchemy import (create_engine, Column, String, Date, Numeric, Integer, ForeignKey,
                        PrimaryKeyConstraint, inspect, text)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from datetime import datetime
import json
import os
import time

# ---------------------------------------------------------------------------
# TTL cache：預設程序內記憶體；若設定 REDIS_URL 且已安裝 redis 則跨程序共用
# ---------------------------------------------------------------------------
_cache: dict = {}
_redis_client = None
_redis_init_failed = False


def _redis_conn():
    global _redis_client, _redis_init_failed
    url = (os.getenv("REDIS_URL") or "").strip()
    if not url or _redis_init_failed:
        return None
    if _redis_client is None:
        try:
            import redis as redis_mod

            _redis_client = redis_mod.from_url(url, decode_responses=True)
        except Exception:
            _redis_init_failed = True
            return None
    return _redis_client


def cache_get(key: str, ttl_seconds: int):
    r = _redis_conn()
    if r is not None:
        try:
            raw = r.get(f"lc:{key}")
            if raw:
                obj = json.loads(raw)
                if time.time() - float(obj["ts"]) < ttl_seconds:
                    return obj["data"]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            pass
        return None
    if key in _cache:
        value, ts = _cache[key]
        if (datetime.now() - ts).total_seconds() < ttl_seconds:
            return value
    return None


def cache_set(key: str, value):
    r = _redis_conn()
    if r is not None:
        try:
            r.set(
                f"lc:{key}",
                json.dumps({"ts": time.time(), "data": value}, default=str),
            )
        except (TypeError, ValueError):
            pass
        return
    _cache[key] = (value, datetime.now())


def cache_clear():
    _cache.clear()
    r = _redis_conn()
    if r is not None:
        try:
            for k in r.scan_iter(match="lc:*"):
                r.delete(k)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Database connection — SQLite (local dev) or PostgreSQL (production)
# ---------------------------------------------------------------------------
def normalize_db_url(url: str) -> str:
    """Render / Supabase 可能給 postgres:// 舊格式；SQLAlchemy 2.1 起 postgresql:// 預設驅動
    改為 psycopg (v3)，本專案安裝的是 psycopg2-binary，因此明確指定 +psycopg2。"""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


_db_url = os.getenv("DATABASE_URL")
if _db_url:
    DATABASE_URL = normalize_db_url(_db_url)
    engine = create_engine(
        DATABASE_URL,
        pool_size=2,
        max_overflow=1,
        pool_pre_ping=True,   # 自動偵測並回收殭屍連線
        pool_recycle=300,     # 5 分鐘強制回收，避免 Supabase 踢掉閒置連線
        # text() 的批次 upsert（T86 約 2 萬列）預設由 psycopg2 逐列送出，GitHub runner（美國）
        # 到 Supabase（ap-south-1）每列一次往返 → 數小時；改用 execute_batch 每 500 列一次往返
        executemany_mode="values_plus_batch",
        executemany_batch_page_size=500,
    )
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'data.db')}"
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, nullable=False)
    notify_token = Column(String, nullable=True)


class Watchlist(Base):
    __tablename__ = "watchlists"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    stock_id = Column(String, nullable=False)


class Stock(Base):
    __tablename__ = "stocks"
    stock_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)


class DailyChip(Base):
    """個股每日三大法人買賣超（T86）。單位：股（API 回傳時 ÷1000 轉成張）。
    欄位順序刻意讓定長整數在前、varchar 在後，避免 alignment padding（每列 heap 約 52 bytes）。
    PK 為 (stock_id, date) 供個股歷史查詢；依日期的查詢走 BRIN(date)。
    """
    __tablename__ = "daily_chips"
    __table_args__ = (PrimaryKeyConstraint("stock_id", "date", name="daily_chips_pkey"),)
    date = Column(Date, nullable=False)
    foreign_buy = Column(Integer, nullable=False)   # 外資買賣超（股）
    trust_buy = Column(Integer, nullable=False)     # 投信買賣超（股）
    dealer_buy = Column(Integer, nullable=False)    # 自營商買賣超（股）
    stock_id = Column(String, nullable=False)


class MarketDaily(Base):
    """大盤每日彙總（原 daily_chips 的 stock_id='0000' 列）"""
    __tablename__ = "market_daily"
    date = Column(Date, primary_key=True)
    foreign_buy = Column(Numeric, nullable=True)       # 外資買賣超（億元）
    trust_buy = Column(Numeric, nullable=True)         # 投信買賣超（億元）
    dealer_buy = Column(Numeric, nullable=True)        # 自營商買賣超（億元）
    margin_long = Column(Integer, nullable=True)       # 融資金額增減（千元）
    margin_short = Column(Integer, nullable=True)      # 融券增減（張）
    tx_foreign_long = Column(Integer, nullable=True)   # 台指期外資多方未平倉口數
    tx_foreign_short = Column(Integer, nullable=True)  # 台指期外資空方未平倉口數
    mtx_retail_long = Column(Integer, nullable=True)   # 小台外資多方未平倉口數
    mtx_retail_short = Column(Integer, nullable=True)  # 小台外資空方未平倉口數
    trust_tx_long = Column(Integer, nullable=True)     # 台指期投信多方未平倉口數
    trust_tx_short = Column(Integer, nullable=True)    # 台指期投信空方未平倉口數
    mtx_trust_long = Column(Integer, nullable=True)    # 舊欄位（保留歷史資料）
    mtx_trust_short = Column(Integer, nullable=True)
    mtx_dealer_long = Column(Integer, nullable=True)
    mtx_dealer_short = Column(Integer, nullable=True)
    market_volume = Column(Numeric, nullable=True)     # 大盤成交金額（億元）


INT32_MAX = 2**31 - 1


def shares_to_lots(value):
    """daily_chips 存股數；API 一律回傳張（與遷移前 numeric 欄位相同的數值）。"""
    return None if value is None else float(value) / 1000


def latest_chip_date(db: Session):
    """daily_chips 最新日期。只有 BRIN(date) 索引，全表 MAX 會掃全表；
    先限定近 30 天（BRIN 可跳過舊區塊），沒有才退回全表。"""
    from datetime import date as _date, timedelta

    cutoff = _date.today() - timedelta(days=30)
    recent = db.execute(
        text("SELECT MAX(date) FROM daily_chips WHERE date >= :cutoff"), {"cutoff": cutoff}
    ).scalar()
    if recent is not None:
        return recent
    return db.execute(text("SELECT MAX(date) FROM daily_chips")).scalar()


class SchemaNotMigratedError(RuntimeError):
    pass


def assert_schema_current(bind=None) -> None:
    """新程式碼以「股」寫入整數欄位；若 DB 還是舊 schema（daily_chips 仍有大盤欄位），
    直接拒絕啟動，避免把股數寫進以「張」為單位的舊表。"""
    insp = inspect(bind or engine)
    if not insp.has_table("daily_chips"):
        return
    cols = {c["name"] for c in insp.get_columns("daily_chips")}
    if "margin_long" in cols:
        raise SchemaNotMigratedError(
            "daily_chips 仍是舊 schema；請先執行 backend/migrations/001_slim_daily_chips.sql"
        )


class DailyExchangeRate(Base):
    """每日台幣匯率（台銀牌告）"""
    __tablename__ = "daily_exchange_rate"
    date = Column(Date, primary_key=True)
    usd_buy = Column(Numeric, nullable=True)    # 美金現金買入
    usd_sell = Column(Numeric, nullable=True)   # 美金現金賣出


class DailyOption(Base):
    """選擇權每日籌碼摘要"""
    __tablename__ = "daily_options"
    date = Column(Date, primary_key=True)
    pc_ratio = Column(Numeric, nullable=True)           # Put/Call 未平倉比率（近月，%）
    call_max_strike = Column(Numeric, nullable=True)    # Call 最大 OI 履約價（天花板）
    put_max_strike = Column(Numeric, nullable=True)     # Put 最大 OI 履約價（地板）
    call_total_oi = Column(Integer, nullable=True)      # 近月 Call 總未平倉
    put_total_oi = Column(Integer, nullable=True)       # 近月 Put 總未平倉
    foreign_call_net_yi = Column(Numeric, nullable=True)  # 外資 Call 淨部位（億元，多-空）
    foreign_put_net_yi = Column(Numeric, nullable=True)   # 外資 Put 淨部位（億元，多-空）


class BrokerDaily(Base):
    __tablename__ = "broker_daily"
    date = Column(String, primary_key=True)
    stock_id = Column(String, primary_key=True)
    branch_id = Column(String, primary_key=True)
    branch_name = Column(String, nullable=True)
    buy_shares = Column(Integer, default=0)
    sell_shares = Column(Integer, default=0)


class StockPrice(Base):
    __tablename__ = "stock_prices"
    date = Column(String, primary_key=True)
    stock_id = Column(String, primary_key=True)
    close = Column(Numeric, nullable=True)
    volume = Column(Integer, nullable=True)


class StockIndustry(Base):
    """上市櫃股票 → FinMind TaiwanStockInfo 產業分類"""
    __tablename__ = "stock_industry"
    stock_id = Column(String, primary_key=True)
    industry_name = Column(String, nullable=False)


class MarketSeriesDaily(Base):
    """大盤／櫃買報酬指數與產業代表股收盤（proxy）日線"""
    __tablename__ = "market_series_daily"
    date = Column(String, primary_key=True)
    series_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    series_type = Column(String, nullable=False)  # index | proxy
    close = Column(Numeric, nullable=False)
    volume = Column(Integer, nullable=True)


def init_db():
    assert_schema_current()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        existing = db.execute(text("SELECT COUNT(*) FROM users")).scalar()
        if existing == 0:
            db.execute(text("INSERT INTO users (id, username) VALUES (1, 'default')"))
            db.commit()
        # 補 Index（IF NOT EXISTS 避免重複）
        # daily_chips 依日期查詢改用 BRIN（遷移後已移除 idx_chips_stock_date，勿再建）
        if engine.dialect.name == "postgresql":
            db.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_chips_date_brin ON daily_chips "
                "USING brin (date) WITH (pages_per_range = 32)"
            ))
        else:
            db.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_chips_date ON daily_chips(date)"
            ))
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_watchlists_user ON watchlists(user_id)"
        ))
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_broker_stock_date ON broker_daily(stock_id, date DESC)"
        ))
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_options_date ON daily_options(date DESC)"
        ))
        db.commit()
        try:
            db.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_market_series_sid_date "
                "ON market_series_daily(series_id, date DESC)"
            ))
            db.commit()
        except Exception:
            db.rollback()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
