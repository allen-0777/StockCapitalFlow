from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv()
import asyncio
import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.models.database import init_db
from app.api import health, market, stocks, watchlist, institutional, broker, concentration, admin, industries
from app.services.finmind_client import close_shared_session


_logger = logging.getLogger(__name__)


async def _init_db_with_retry(attempts: int | None = None, delay_s: float | None = None) -> bool:
    """啟動時 DB 暫時連不上（例如 Supabase 剛從 paused 恢復）不要讓 uvicorn 以 exit 3 結束；
    重試數次後仍失敗則照常啟動，由 /api/v1/health 回報錯誤，之後請求再連線。"""
    attempts = attempts or int(os.getenv("DB_INIT_ATTEMPTS", "5"))
    delay_s = float(os.getenv("DB_INIT_DELAY_S", "10")) if delay_s is None else delay_s
    for i in range(1, attempts + 1):
        try:
            await asyncio.to_thread(init_db)
            return True
        except Exception as exc:  # noqa: BLE001 — 任何 DB 錯誤都不應讓服務起不來
            _logger.warning("init_db failed (attempt %d/%d): %s", i, attempts, exc)
            if i < attempts:
                await asyncio.sleep(delay_s)
    _logger.error("init_db failed after %d attempts; starting without schema check", attempts)
    return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _init_db_with_retry()
    # APScheduler：本機或付費雲端主機才啟動（免費 Render 靠 GitHub Actions 觸發）
    scheduler = None
    if os.getenv("ENABLE_SCHEDULER", "false").lower() == "true":
        from app.services.scheduler import start_scheduler
        scheduler = start_scheduler()
    yield
    if scheduler:
        scheduler.shutdown()
    await close_shared_session()


app = FastAPI(title="LiquidChip API", lifespan=lifespan)

# CORS：本機 + 生產環境 Vercel 網域
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173")
allowed_origins = [o.strip() for o in _raw_origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(market.router)
app.include_router(stocks.router)
app.include_router(watchlist.router)
app.include_router(institutional.router)
app.include_router(broker.router)
app.include_router(concentration.router)
app.include_router(admin.router)
app.include_router(industries.router)
