"""
Kalpi Portfolio Execution Engine — FastAPI Application Entry Point
"""
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import init_db
from app.api import api_router
from app.api.notifications import router as notification_router
from app.core.seed import seed as seed_db

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    logger.info("startup.begin", app=settings.APP_NAME, version=settings.APP_VERSION)
    await init_db()
    await seed_db()
    logger.info("startup.complete", paper_trading=settings.PAPER_TRADING)
    yield
    logger.info("shutdown.complete")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
## Kalpi Portfolio Execution Engine

An end-to-end portfolio trade execution engine that:
- **Connects** to 5 major Indian brokers (Zerodha, Fyers, AngelOne, Upstox, Groww)
- **Computes** the delta between current holdings and target portfolio
- **Executes** all necessary trades in a single click
- **Notifies** via WebSocket, Webhook, and Console log

### Paper Trading Mode
All orders are simulated by default. Set `PAPER_TRADING=false` with real API keys for live trading.

### Authentication
All endpoints (except `/auth/login` and `/auth/register`) require a Bearer JWT token.
Get one via `POST /api/v1/auth/login`.
    """,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ─── Middleware ────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# ─── Routes ───────────────────────────────────────────────────────────────
app.include_router(api_router)
app.include_router(notification_router)  # WebSocket + webhook receiver


# ─── Health Check ─────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health_check():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "paper_trading": settings.PAPER_TRADING,
    }


@app.get("/", tags=["System"])
async def root():
    return {
        "message": "Kalpi Portfolio Execution Engine",
        "docs": "/docs",
        "health": "/health",
        "websocket": "ws://localhost:8000/ws/{user_id}",
    }


# ─── Global Exception Handler ─────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error("unhandled_exception", path=str(request.url), error=str(exc), exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)},
    )


