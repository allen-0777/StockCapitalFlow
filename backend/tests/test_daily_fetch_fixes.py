from datetime import date, datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.services import fetcher
from app.services import finmind_client as fm


def test_parse_roc_date():
    assert fetcher._parse_roc_date("115/10/20") == date(2026, 10, 20)
    with pytest.raises(ValueError):
        fetcher._parse_roc_date("bad")


@pytest.mark.asyncio
async def test_turnover_uses_row_date_not_query_date():
    body = {"stat": "OK", "date": "20261021", "data": [
        ["115/10/19", "1", "700,000,000,000", "1"], ["115/10/20", "1", "802,947,000,000", "1"]]}
    with patch.object(fetcher, "_get_json_with_retry", AsyncMock(return_value=body)), \
         patch.object(fetcher, "SessionLocal"), patch.object(fetcher, "_upsert_chip") as upsert:
        assert await fetcher.fetch_turnover() == date(2026, 10, 20)
    assert upsert.call_args.args[1] == date(2026, 10, 20)


@pytest.mark.asyncio
async def test_exchange_rate_from_finmind_upserts_range():
    engine = create_engine("sqlite://")
    with engine.begin() as db:
        db.execute(text("CREATE TABLE daily_exchange_rate (date DATE PRIMARY KEY, usd_buy NUMERIC, usd_sell NUMERIC)"))
        db.execute(text("INSERT INTO daily_exchange_rate VALUES ('2026-10-19', 1, 1)"))
    rows = [{"date": "2026-10-19", "cash_buy": 32.045, "cash_sell": 32.715},
            {"date": "2026-10-20", "cash_buy": 32.1, "cash_sell": 32.77},
            {"date": "2026-10-20x", "cash_buy": "bad", "cash_sell": 1}]
    get = AsyncMock(return_value=rows)
    with patch.object(fm, "finmind_get", get), patch.object(fm, "get_shared_session", AsyncMock()), \
         patch.object(fetcher, "SessionLocal", side_effect=lambda: Session(engine)):
        assert await fetcher.fetch_exchange_rate(start=date(2026, 10, 19)) == date(2026, 10, 20)
    assert get.call_args.args[1:4] == ("TaiwanExchangeRate", "USD", "2026-10-19")
    with engine.connect() as db:
        got = db.execute(text("SELECT date, usd_buy FROM daily_exchange_rate ORDER BY date")).fetchall()
    assert [(str(d), float(b)) for d, b in got] == [("2026-10-19", 32.045), ("2026-10-20", 32.1)]


@pytest.mark.asyncio
@pytest.mark.parametrize("hour,expected_arg", [(10, date(2026, 10, 20)), (17, date(2026, 10, 21))])
async def test_freshness_expects_previous_day_before_data_ready(hour, expected_arg):
    from scripts import fetch_daily
    fake_now = datetime(2026, 10, 21, hour, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    ltd = lambda d: d  # noqa: E731
    with patch.object(fetch_daily, "datetime") as dt, \
         patch.object(fetch_daily, "is_trading_day", return_value=True), \
         patch.object(fetch_daily, "latest_trading_day", side_effect=ltd) as ltd_mock, \
         patch.dict(fetch_daily.JOBS, {"t": ["fetch_margin"]}, clear=True), \
         patch.object(fetcher, "fetch_margin", AsyncMock(return_value=expected_arg)), \
         patch.object(fm, "close_shared_session", AsyncMock()):
        dt.now.return_value = fake_now
        assert await fetch_daily.run(["t"]) == 0
    ltd_mock.assert_called_once_with(expected_arg)


@pytest.mark.asyncio
async def test_twse_retries_non_json_throttle_page():
    import json
    calls = AsyncMock(side_effect=[json.JSONDecodeError("x", "<html>", 0), {"stat": "OK"}])
    with patch.object(fetcher, "_get_json", calls), patch.object(fetcher.asyncio, "sleep", AsyncMock()) as sl:
        assert await fetcher._get_json_with_retry("u") == {"stat": "OK"}
    sl.assert_awaited_once_with(5)
