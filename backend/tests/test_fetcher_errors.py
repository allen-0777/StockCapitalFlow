import pytest
from unittest.mock import AsyncMock, patch, MagicMock


def _mock_twse_get(json_body: dict):
    """Mock aiohttp.ClientSession for a TWSE GET response."""
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value=json_body)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


def _mock_finmind_get(json_body: dict):
    """Mock aiohttp.ClientSession for a FinMind GET response (empty data)."""
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=json_body)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


@pytest.mark.asyncio
async def test_fetch_institutional_market_raises_on_closed_stat():
    from app.services.fetcher import fetch_institutional_market
    body = {"stat": "CLOSED", "date": "20260321", "data": []}
    with patch("aiohttp.ClientSession", return_value=_mock_twse_get(body)):
        with pytest.raises(RuntimeError, match="TWSE BFI82U stat=CLOSED"):
            await fetch_institutional_market()


@pytest.mark.asyncio
async def test_fetch_institutional_stocks_raises_on_closed_stat():
    from app.services.fetcher import fetch_institutional_stocks
    body = {"stat": "CLOSED", "date": "20260321", "data": []}
    with patch("aiohttp.ClientSession", return_value=_mock_twse_get(body)):
        with pytest.raises(RuntimeError, match="TWSE T86 stat=CLOSED"):
            await fetch_institutional_stocks()


@pytest.mark.asyncio
async def test_fetch_margin_raises_on_closed_stat():
    from app.services.fetcher import fetch_margin
    body = {"stat": "CLOSED", "date": "20260321", "tables": []}
    with patch("aiohttp.ClientSession", return_value=_mock_twse_get(body)):
        with pytest.raises(RuntimeError, match="TWSE MI_MARGN stat=CLOSED"):
            await fetch_margin()


@pytest.mark.asyncio
async def test_fetch_futures_oi_raises_when_taifex_empty():
    from app.services.fetcher import fetch_futures_oi
    with patch("app.services.fetcher._get_taifex_json", new_callable=AsyncMock, return_value=[]):
        with pytest.raises(RuntimeError, match="TAIFEX 期貨三大法人 API 回傳空資料"):
            await fetch_futures_oi()


@pytest.mark.asyncio
async def test_fetch_options_data_raises_when_taifex_empty():
    from app.services.fetcher import fetch_options_data
    with patch("app.services.fetcher._get_taifex_json", new_callable=AsyncMock, return_value=[]):
        with pytest.raises(RuntimeError, match="TAIFEX 選擇權三大法人 API 回傳空資料"):
            await fetch_options_data()
