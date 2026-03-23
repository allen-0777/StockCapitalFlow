import pytest
from unittest.mock import AsyncMock, patch, MagicMock, call
from datetime import date
import os

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123456")


def _mock_telegram_session(status=200):
    """Helper: mock aiohttp.ClientSession for Telegram POST."""
    mock_resp = MagicMock()
    mock_resp.status = status
    mock_resp.text = AsyncMock(return_value="ok")
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


@pytest.mark.asyncio
async def test_send_message_posts_to_telegram():
    """send_message should POST to Telegram sendMessage API."""
    from app.services.notification import send_message

    mock_session = _mock_telegram_session()
    with patch("aiohttp.ClientSession", return_value=mock_session):
        await send_message("hello")

    mock_session.post.assert_called_once()
    url = mock_session.post.call_args[0][0]
    assert "sendMessage" in url
    assert "test-token" in url


@pytest.mark.asyncio
async def test_send_message_truncates_at_4096():
    """send_message must truncate text to 4096 chars before sending."""
    from app.services.notification import send_message

    captured = []

    async def fake_post(url, **kwargs):
        captured.append(kwargs["json"]["text"])
        resp = MagicMock()
        resp.status = 200
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        return resp

    mock_session = MagicMock()
    mock_session.post = fake_post
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        await send_message("x" * 5000)

    assert len(captured) == 1
    assert len(captured[0]) <= 4096


@pytest.mark.asyncio
async def test_send_message_does_not_raise_on_network_error():
    """send_message must swallow exceptions and never raise."""
    from app.services.notification import send_message

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.post = MagicMock(side_effect=Exception("network error"))

    with patch("aiohttp.ClientSession", return_value=mock_session):
        await send_message("hello")  # must not raise


@pytest.mark.asyncio
async def test_send_job_result_success_contains_checkmark():
    """Success result should contain checkmark emoji and job name."""
    from app.services.notification import send_job_result

    sent = []
    with patch("app.services.notification.send_message", new=AsyncMock(side_effect=lambda t: sent.append(t))):
        await send_job_result(
            job="institutional",
            steps=[{
                "fn": "fetch_institutional_market",
                "status": "ok",
                "duration_s": 1.2,
                "rows": None,
                "error": None,
                "date": "2026-03-21",
            }],
            got_date=date(2026, 3, 21),
            expected_date=date(2026, 3, 21),
        )

    assert len(sent) == 1
    assert "✅" in sent[0]
    assert "institutional" in sent[0]


@pytest.mark.asyncio
async def test_send_job_result_partial_error_shows_warning_and_error_text():
    """Partial failure should show warning emoji and the error message."""
    from app.services.notification import send_job_result

    sent = []
    with patch("app.services.notification.send_message", new=AsyncMock(side_effect=lambda t: sent.append(t))):
        await send_job_result(
            job="futures",
            steps=[
                {"fn": "fetch_futures_oi", "status": "ok", "duration_s": 2.1, "rows": None, "error": None, "date": "2026-03-21"},
                {"fn": "fetch_options_data", "status": "error", "duration_s": 1.0, "rows": None, "error": "FinMind 配額已用盡", "date": None},
            ],
            got_date=date(2026, 3, 21),
            expected_date=date(2026, 3, 21),
        )

    assert len(sent) == 1
    assert "⚠️" in sent[0]
    assert "FinMind 配額已用盡" in sent[0]


@pytest.mark.asyncio
async def test_send_daily_digest_queries_db_and_sends_message():
    """send_daily_digest should query daily_chips and send a formatted message."""
    from app.services.notification import send_daily_digest
    from unittest.mock import MagicMock

    mock_db = MagicMock()
    # Simulate daily_chips row: (date, foreign_buy, trust_buy, dealer_buy,
    #   margin_long, margin_short, tx_foreign_long, tx_foreign_short,
    #   trust_tx_long, trust_tx_short)
    mock_db.execute.return_value.fetchone.side_effect = [
        ("2026-03-21", 12.3, -2.1, 0.8, 230000, -1200, 15234, 12100, 500, 300),
        None,  # no options row
    ]

    sent = []
    with patch("app.services.notification.send_message", new=AsyncMock(side_effect=lambda t: sent.append(t))):
        await send_daily_digest(mock_db)

    assert len(sent) == 1
    assert "2026-03-21" in sent[0]
    assert "法人" in sent[0]


@pytest.mark.asyncio
async def test_send_daily_digest_sends_fallback_when_no_data():
    """send_daily_digest should send a fallback message when DB is empty."""
    from app.services.notification import send_daily_digest

    mock_db = MagicMock()
    mock_db.execute.return_value.fetchone.return_value = None

    sent = []
    with patch("app.services.notification.send_message", new=AsyncMock(side_effect=lambda t: sent.append(t))):
        await send_daily_digest(mock_db)

    assert len(sent) == 1
    assert "資料庫尚無資料" in sent[0]
