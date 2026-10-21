"""
共用 FinMind v4 HTTP：單一 aiohttp ClientSession（程序內重用）與統一錯誤處理。
腳本與 FastAPI 共用；應用關閉時請 await close_shared_session()。
"""
from __future__ import annotations

import asyncio
import os
import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import aiohttp

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"


class FinMindAPIError(Exception):
    def __init__(self, status, msg="", retry_after=0):
        self.status = status
        self.msg = msg
        self.retry_after = retry_after
        super().__init__(f"FinMind status={status}: {msg}")


class FinMindQuotaError(FinMindAPIError):
    """FinMind 配額用盡，不重試。"""

    def __init__(self, status=402, msg="Quota exhausted"):
        super().__init__(status, msg)


_semaphore = asyncio.Semaphore(max(1, int(os.getenv("FINMIND_MAX_CONCURRENCY", "2"))))
_rate_lock = asyncio.Lock()
_min_interval = max(0.0, float(os.getenv("FINMIND_MIN_INTERVAL_S", "0.5")))
_last_request = 0.0
_sleep = asyncio.sleep


def _retry_after(value):
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        try:
            return max(0.0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return 0.0


_shared_session: aiohttp.ClientSession | None = None
_session_lock = asyncio.Lock()


async def get_shared_session() -> aiohttp.ClientSession:
    global _shared_session
    async with _session_lock:
        if _shared_session is None or _shared_session.closed:
            _shared_session = aiohttp.ClientSession(
                headers={"User-Agent": "Mozilla/5.0 (compatible; LiquidChip/1.0)"},
            )
        return _shared_session


async def close_shared_session() -> None:
    global _shared_session
    async with _session_lock:
        if _shared_session is not None and not _shared_session.closed:
            await _shared_session.close()
        _shared_session = None


async def finmind_get(
    session: aiohttp.ClientSession | None,
    dataset: str,
    data_id: str,
    start_date: str,
    end_date: str = "",
    *,
    timeout: float = 60.0,
    token_in_query: bool = False,
) -> list[dict[str, Any]]:
    """
    GET FinMind /api/v4/data。
    - token_in_query=True：參數帶 token（與舊版選擇權抓取一致）；否則使用 Authorization Bearer。
    - 非 200 狀態拋 FinMindAPIError；暫時性錯誤最多嘗試三次。
    - 402 時拋 FinMindQuotaError。
    """
    token = os.getenv("FINMIND_TOKEN", "")
    params: dict[str, str] = {
        "dataset": dataset,
        "data_id": data_id,
        "start_date": start_date,
    }
    if end_date:
        params["end_date"] = end_date

    headers: dict[str, str] = {"User-Agent": "Mozilla/5.0 (compatible; LiquidChip/1.0)"}
    if token_in_query:
        params["token"] = token
    else:
        headers["Authorization"] = f"Bearer {token}"

    sess = session if session is not None else await get_shared_session()
    to = aiohttp.ClientTimeout(total=timeout)
    global _last_request
    for attempt in range(3):
        try:
            async with _semaphore:
                async with _rate_lock:
                    delay = _min_interval - (time.monotonic() - _last_request)
                    if delay > 0:
                        await _sleep(delay)
                    _last_request = time.monotonic()
                async with sess.get(FINMIND_URL, params=params, headers=headers, timeout=to) as resp:
                    retry_after = _retry_after(resp.headers.get("Retry-After"))
                    if resp.status == 402:
                        raise FinMindQuotaError(402, "Quota exhausted")
                    if resp.status != 200:
                        raise FinMindAPIError(resp.status, "HTTP error", retry_after)
                    body = await resp.json(content_type=None)
                    status = body.get("status")
                    if status == 402:
                        raise FinMindQuotaError(status, body.get("msg", ""))
                    if status != 200:
                        raise FinMindAPIError(status, body.get("msg", ""), retry_after)
                    return body.get("data") or []
        except FinMindQuotaError:
            raise
        except (FinMindAPIError, aiohttp.ClientError, asyncio.TimeoutError) as exc:
            if isinstance(exc, FinMindAPIError) and not (
                exc.status == 429 or isinstance(exc.status, int) and 500 <= exc.status < 600
            ):
                raise
            if attempt == 2:
                raise
            await _sleep(max(getattr(exc, "retry_after", 0), 2 ** attempt + random.uniform(0, 0.5)))
