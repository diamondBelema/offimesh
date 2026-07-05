"""OffiMesh FastAPI Application Entry Point."""
from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import close_database
from app.core.exceptions import OffiMeshError
from app.core.logging import setup_logging
from app.core.redis import close_redis, get_redis
from app.middleware.correlation_id import CorrelationIDMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.routers import (
    auth_router,
    devices_router,
    health_router,
    identity_router,
    settlements_router,
    tokens_router,
    transactions_router,
    users_router,
    wallet_router,
    webhooks_router,
)

# Setup logging
setup_logging()
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info(
        "starting_up",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )

    # Initialize Redis connection
    await get_redis()
    logger.info("redis_connected")

    yield

    # Cleanup
    logger.info("shutting_down")
    await close_redis()
    await close_database()
    logger.info("shutdown_complete")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    description="Offline-first payment infrastructure for Africa. Settles transactions through Nomba payment API.",
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add correlation ID middleware
app.add_middleware(CorrelationIDMiddleware)

# Add rate limiting middleware (disabled in debug mode)
if not settings.debug:
    app.add_middleware(RateLimitMiddleware, requests_per_minute=settings.rate_limit_requests)


# Exception handlers
@app.exception_handler(OffiMeshError)
async def offimesh_error_handler(request: Request, exc: OffiMeshError):
    """Handle OffiMesh-specific errors."""
    request_id = getattr(request.state, "correlation_id", "")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "data": None,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "field": exc.field,
            },
            "meta": {
                "request_id": request_id,
                "timestamp": "",
                "version": "1.0",
            },
        },
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    """Handle unexpected errors."""
    request_id = getattr(request.state, "correlation_id", "")
    logger.exception("unhandled_exception", error=str(exc))
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "data": None,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "field": None,
            },
            "meta": {
                "request_id": request_id,
                "timestamp": "",
                "version": "1.0",
            },
        },
    )


# Include routers
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(devices_router)
app.include_router(tokens_router)
app.include_router(transactions_router)
app.include_router(settlements_router)
app.include_router(wallet_router)
app.include_router(webhooks_router)
app.include_router(identity_router)


def run() -> None:
    """Run the application with uvicorn."""
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_config=None,  # Use structlog
    )


if __name__ == "__main__":
    run()
