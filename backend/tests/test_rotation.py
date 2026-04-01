"""產業輪動：DB 查詢批次化與 compute_rotation 基本行為。"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.models.database import Base
from app.services.industry_sync import INDUSTRY_PROXY_STOCKS
from app.services.rotation import BENCHMARK_ID, compute_rotation


def _insert_series_row(db, d: str, series_id: str, close: float, name: str = "n", st: str = "index"):
    db.execute(
        text(
            """
            INSERT INTO market_series_daily (date, series_id, name, series_type, close, volume)
            VALUES (:d, :sid, :n, :t, :c, NULL)
            """
        ),
        {"d": d, "sid": series_id, "n": name, "t": st, "c": close},
    )


@pytest.fixture
def memory_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    yield db
    db.close()


def test_compute_rotation_insufficient_benchmark(memory_db):
    db = memory_db
    for i in range(10):
        d = (date(2025, 1, 1) + timedelta(days=i)).isoformat()
        _insert_series_row(db, d, BENCHMARK_ID, 100.0 + i * 0.1)
    db.commit()

    out = compute_rotation(db, lookback=120)
    assert out["industries"] == []
    assert "尚無足夠大盤序列" in (out.get("note") or "")


def test_compute_rotation_returns_industries_when_aligned(memory_db):
    db = memory_db
    ind_sid = f"IND:{INDUSTRY_PROXY_STOCKS[0][0]}"
    base = date(2025, 1, 2)
    for i in range(40):
        d = (base + timedelta(days=i)).isoformat()
        m = 18000.0 + i * 5.0
        _insert_series_row(db, d, BENCHMARK_ID, m, "加權", "index")
        _insert_series_row(db, d, ind_sid, m * 1.001, "半導體", "proxy")
    db.commit()

    out = compute_rotation(db, lookback=120)
    assert out.get("as_of") is not None
    assert len(out["industries"]) >= 1
    first = next(x for x in out["industries"] if x["series_id"] == ind_sid)
    assert first["proxy_stock"] == INDUSTRY_PROXY_STOCKS[0][1]
    assert first.get("rank") is not None
