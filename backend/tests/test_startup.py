from unittest.mock import patch

import pytest

from app import main


@pytest.mark.asyncio
async def test_init_db_retry_recovers():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("db restoring")

    with patch.object(main, "init_db", side_effect=flaky):
        assert await main._init_db_with_retry(attempts=5, delay_s=0) is True
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_init_db_failure_does_not_crash_startup():
    with patch.object(main, "init_db", side_effect=RuntimeError("down")) as m:
        assert await main._init_db_with_retry(attempts=2, delay_s=0) is False
    assert m.call_count == 2
