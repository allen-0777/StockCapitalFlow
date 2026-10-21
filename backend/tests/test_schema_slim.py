"""schema 001：daily_chips 存股數（integer）、大盤列搬到 market_daily。"""
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.api import institutional, stocks, watchlist
from app.models import database
from app.models.database import Base, get_db
from app.services import fetcher


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=__import__("sqlalchemy.pool", fromlist=["StaticPool"]).StaticPool)
    Base.metadata.create_all(eng)
    with eng.begin() as db:
        db.execute(text("INSERT INTO users (id, username) VALUES (1, 'default')"))
    yield eng
    eng.dispose()


def _client(engine):
    app = FastAPI()
    for r in (institutional.router, stocks.router, watchlist.router):
        app.include_router(r)
    local = sessionmaker(bind=engine)

    def _db():
        with local() as s:
            yield s
    app.dependency_overrides[get_db] = _db
    database.cache_clear()
    return TestClient(app)


@pytest.mark.asyncio
async def test_t86_written_as_shares_and_served_as_lots(engine):
    t86 = {"stat": "OK", "date": "20261020", "data": [
        ["2330", "台積電", "0", "0", "32,813,179", "0", "0", "0", "0", "0", "-1,500", "389,888,022"],
        ["00632R", "元大台灣50反1", "0", "0", "-7", "0", "0", "0", "0", "0", "0", "0"],
    ]}
    with patch.object(fetcher, "_get_json_with_retry", AsyncMock(return_value=t86)), \
         patch.object(fetcher, "SessionLocal", side_effect=lambda: Session(engine)):
        assert await fetcher.fetch_institutional_stocks() == date(2026, 10, 20)
        await fetcher.fetch_institutional_stocks()  # 重跑：值相同不應改變結果
    with engine.connect() as db:
        rows = db.execute(text("SELECT stock_id, foreign_buy, trust_buy, dealer_buy FROM daily_chips ORDER BY stock_id")).all()
    assert [tuple(r) for r in rows] == [("00632R", -7, 0, 0), ("2330", 32813179, -1500, 389888022)]

    with engine.begin() as db:
        db.execute(text("INSERT INTO watchlists (user_id, stock_id) VALUES (1, '2330')"))
    c = _client(engine)
    chips = c.get("/api/v1/stocks/2330/chips").json()
    assert chips == [{"date": "2026-10-20", "foreign_buy": 32813.179, "trust_buy": -1.5,
                      "dealer_buy": 389888.022, "margin_long": 0, "margin_short": 0}]
    rank = c.get("/api/v1/institutional/ranking?type=foreign&order=buy&limit=5").json()
    assert rank[0]["stock_id"] == "2330" and rank[0]["foreign_buy"] == 32813.18
    assert rank[0]["total"] == round((32813179 - 1500 + 389888022) / 1000, 2)
    wl = c.get("/api/v1/users/1/watchlist").json()
    assert wl[0]["foreign_buy"] == 32813.179 and wl[0]["date"] == "2026-10-20"


@pytest.mark.asyncio
async def test_t86_skips_rows_outside_int4(engine, capsys):
    t86 = {"stat": "OK", "date": "20261020", "data": [
        ["9999", "huge", "0", "0", "3,000,000,000", "0", "0", "0", "0", "0", "0", "0"],
        ["2330", "台積電", "0", "0", "1", "0", "0", "0", "0", "0", "0", "0"],
    ]}
    with patch.object(fetcher, "_get_json_with_retry", AsyncMock(return_value=t86)), \
         patch.object(fetcher, "SessionLocal", side_effect=lambda: Session(engine)):
        await fetcher.fetch_institutional_stocks()
    with engine.connect() as db:
        assert db.execute(text("SELECT stock_id FROM daily_chips")).scalars().all() == ["2330"]
    assert "outside int4 range" in capsys.readouterr().out


def test_market_rows_go_to_market_daily(engine):
    with Session(engine) as db:
        fetcher._upsert_chip(db, date(2026, 10, 20), "0000", foreign_buy=-121.87)
        fetcher._upsert_chip(db, date(2026, 10, 20), "0000", margin_long=-3231132)
        db.commit()
        row = db.execute(text("SELECT foreign_buy, margin_long FROM market_daily")).one()
        assert float(row[0]) == -121.87 and row[1] == -3231132
        assert db.execute(text("SELECT COUNT(*) FROM daily_chips")).scalar() == 0
        with pytest.raises(ValueError):
            fetcher._upsert_chip(db, date(2026, 10, 20), "2330", foreign_buy=1)
        with pytest.raises(ValueError):
            fetcher._upsert_chip(db, date(2026, 10, 20), "0000", not_a_column=1)


def test_schema_guard_rejects_unmigrated_db():
    eng = create_engine("sqlite://")
    with eng.begin() as db:
        db.execute(text("CREATE TABLE daily_chips (date DATE, stock_id TEXT, foreign_buy NUMERIC, margin_long INTEGER)"))
    with pytest.raises(database.SchemaNotMigratedError):
        database.assert_schema_current(eng)
    database.assert_schema_current(create_engine("sqlite://"))  # 新 DB：通過


def test_latest_chip_date_falls_back_to_full_scan(engine):
    with engine.begin() as db:
        db.execute(text("INSERT INTO daily_chips (date, foreign_buy, trust_buy, dealer_buy, stock_id) "
                        "VALUES ('2020-01-02', 1, 1, 1, '2330')"))
    with Session(engine) as db:
        assert str(database.latest_chip_date(db)) == "2020-01-02"
