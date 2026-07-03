"""Health check Pydantic schemas."""
from __future__ import annotations

from pydantic import Field

from app.schemas.base import BaseSchema


class HealthResponse(BaseSchema):
    """Health check response."""

    status: str = Field(description="Health status: ok, degraded, unhealthy")
    app: str
    version: str
    database: str = Field(description="Database connection status")
    redis: str = Field(description="Redis connection status")
    timestamp: str


class DetailedHealthResponse(BaseSchema):
    """Detailed health check response."""

    status: str
    app: str
    version: str
    environment: str
    checks: dict


class RootResponse(BaseSchema):
    """Root endpoint response."""

    app: str
    version: str
    docs: str
    description: str | None = None
