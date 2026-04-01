from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv()
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.models.database import init_db
from app.api import health, market, stocks, watchlist, institutional, broker, concentration, admin, industries
from app.services.finmind_client import close_shared_session


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
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
