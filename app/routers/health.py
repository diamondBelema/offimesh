"""Health check API routes."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app.core.config import settings
from app.schemas import ok_response

router = APIRouter(tags=["Health"])


@router.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "description": "Offline-first payment infrastructure for Africa",
    }


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/v1/health")
async def health_check_v1():
    """Health check endpoint (v1)."""
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
