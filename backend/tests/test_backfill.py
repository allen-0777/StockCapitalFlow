from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from app.services import fetcher
from app.services import finmind_client as fm


def test_backfill_days_skips_weekends_and_holidays():
    from scripts import fetch_daily
    holiday = date(2026, 4, 3)
    with patch.object(fetch_daily, "is_trading_day", side_effect=lambda d: d.weekday() < 5 and d != holiday):
        assert fetch_daily.backfill_days(date(2026, 4, 2), date(2026, 4, 7)) == [date(2026, 4, 2), date(2026, 4, 6), date(2026, 4, 7)]


@pytest.mark.asyncio
async def test_backfill_calls_twse_per_day_and_market_series_once():
    from scripts import fetch_daily
    days = [date(2026, 4, 7), date(2026, 4, 8)]
    mocks = {n: AsyncMock(side_effect=lambda target: target) for n in fetch_daily.BACKFILL_TWSE_FNS}
    series = AsyncMock(return_value=date(2026, 4, 8))
    fx = AsyncMock(return_value=date(2026, 4, 8))
    with patch.object(fetch_daily, "backfill_days", return_value=days), \
         patch.multiple(fetcher, **mocks), patch.object(fetcher, "sync_market_series_daily", series), \
         patch.object(fetcher, "fetch_exchange_rate", fx), \
         patch.object(fetch_daily, "_taipei_today", return_value=date(2026, 4, 10)), \
         patch.object(fm, "close_shared_session", AsyncMock()):
        assert await fetch_daily.backfill(days[0], days[-1], interval_s=0) == 0
    for m in mocks.values():
        assert [c.kwargs["target"] for c in m.call_args_list] == days
    series.assert_awaited_once_with(days=4)
    fx.assert_awaited_once_with(start=days[0])


@pytest.mark.asyncio
async def test_backfill_counts_date_mismatch_as_failure():
    from scripts import fetch_daily
    d = date(2026, 4, 7)
    mocks = {n: AsyncMock(return_value=date(2026, 4, 6)) for n in fetch_daily.BACKFILL_TWSE_FNS}
    with patch.object(fetch_daily, "backfill_days", return_value=[d]), patch.multiple(fetcher, **mocks), \
         patch.object(fetcher, "sync_market_series_daily", AsyncMock()), \
         patch.object(fetcher, "fetch_exchange_rate", AsyncMock()), \
         patch.object(fm, "close_shared_session", AsyncMock()):
        assert await fetch_daily.backfill(d, d, interval_s=0) == len(fetch_daily.BACKFILL_TWSE_FNS)


@pytest.mark.asyncio
async def test_twse_fetchers_pass_target_date():
    calls = []

    async def fake(url, *a, **k):
        calls.append(url)
        return {"stat": "NO"}

    with patch.object(fetcher, "_get_json_with_retry", side_effect=fake):
        for fn in (fetcher.fetch_institutional_market, fetcher.fetch_institutional_stocks, fetcher.fetch_margin):
            with pytest.raises(Exception):
                await fn(target=date(2026, 4, 15))
    assert "dayDate=20260415" in calls[0]
    assert "date=20260415" in calls[1] and "date=20260415" in calls[2]


@pytest.mark.asyncio
async def test_turnover_picks_target_row():
    body = {"stat": "OK", "date": "20260401", "data": [["115/04/01", "1", "652,608,970,719", "1"], ["115/04/02", "1", "702,608,705,100", "1"]]}
    with patch.object(fetcher, "_get_json_with_retry", AsyncMock(return_value=body)), \
         patch.object(fetcher, "SessionLocal"), patch.object(fetcher, "_upsert_chip") as upsert:
        assert await fetcher.fetch_turnover(target=date(2026, 4, 1)) == date(2026, 4, 1)
    assert upsert.call_args.args[1] == date(2026, 4, 1)
    assert upsert.call_args.kwargs["market_volume"] == 6526.09
    with patch.object(fetcher, "_get_json_with_retry", AsyncMock(return_value=body)), \
         patch.object(fetcher, "SessionLocal"), patch.object(fetcher, "_upsert_chip"):
        with pytest.raises(ValueError):
            await fetcher.fetch_turnover(target=date(2026, 4, 3))
