#!/usr/bin/env python3
"""
正二雷達推播腳本（僅讀 DB，不抓外部 API）。
供 GitHub Actions zheng2-radar.yml 呼叫，與資料抓取分開排程。

用法：
  python backend/scripts/zheng2_push.py
需要環境變數：DATABASE_URL、TELEGRAM_BOT_TOKEN、TELEGRAM_CHAT_ID
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from app.models.database import SessionLocal, init_db
from app.services.zheng2_radar import run_zheng2_radar


async def main() -> None:
    init_db()
    with SessionLocal() as db:
        await run_zheng2_radar(db)


if __name__ == "__main__":
    asyncio.run(main())
