"""
共用 FinMind v4 HTTP：單一 aiohttp ClientSession（程序內重用）與統一錯誤處理。
腳本與 FastAPI 共用；應用關閉時請 await close_shared_session()。
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

import aiohttp

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"


class FinMindQuotaError(Exception):
    """FinMind 回傳 HTTP 402（配額用盡）。"""


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
    - 邏輯 status != 200 時回傳 []（與 concentration 行為一致）。
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
    async with sess.get(FINMIND_URL, params=params, headers=headers, timeout=to) as resp:
        if resp.status == 402:
            raise FinMindQuotaError()
        resp.raise_for_status()
        body = await resp.json(content_type=None)
        if body.get("status") != 200:
            return []
        return body.get("data", [])
