"""
FastAPI backend for AI Day Trader dashboard.
Provides REST API and WebSocket endpoints for real-time monitoring.
"""
import sys
from pathlib import Path
import asyncio
from contextlib import asynccontextmanager
from typing import Optional
import structlog

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import get_settings
from api.routers import settings_router, positions, orders, strategies, risk, system
from api.websocket.manager import websocket_endpoint

logger = structlog.get_logger()
settings = get_settings()

# Global trading engine reference (set by system router)
trading_engine = None


def get_api_key_header(request: Request) -> Optional[str]:
    """Extract API key from header if configured"""
    if not settings.dashboard.api_key:
        return None

    api_key = request.headers.get("X-API-Key")
    if api_key != settings.dashboard.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown"""
    logger.info("dashboard_api_starting", port=settings.dashboard.port)

    # Start WebSocket heartbeat task
    from api.websocket.manager import start_heartbeat
    heartbeat_task = asyncio.create_task(start_heartbeat())

    yield

    # Cleanup
    heartbeat_task.cancel()
    logger.info("dashboard_api_stopped")


app = FastAPI(
    title="AI Day Trader API",
    description="Real-time trading dashboard API",
    version="2.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.dashboard.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(settings_router.router, prefix="/api/settings", tags=["Settings"])
app.include_router(positions.router, prefix="/api/positions", tags=["Positions"])
app.include_router(orders.router, prefix="/api/orders", tags=["Orders"])
app.include_router(strategies.router, prefix="/api/strategies", tags=["Strategies"])
app.include_router(risk.router, prefix="/api/risk", tags=["Risk"])
app.include_router(system.router, prefix="/api/system", tags=["System"])

# WebSocket - must use websocket_route, not api_route
app.add_api_websocket_route("/ws", websocket_endpoint)


@app.get("/")
async def root():
    return {
        "name": "AI Day Trader API",
        "version": "2.0.0",
        "status": "running"
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("api_error", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=settings.dashboard.host,
        port=settings.dashboard.port,
        reload=True
    )
