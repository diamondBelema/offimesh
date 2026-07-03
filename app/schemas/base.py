"""Base Pydantic schemas and common models."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class BaseSchema(BaseModel):
    """Base schema with strict validation."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        populate_by_name=True,
    )


class ResponseMeta(BaseSchema):
    """Metadata for API responses."""

    request_id: str = Field(description="Unique request identifier")
    timestamp: str = Field(description="ISO 8601 timestamp")
    version: str = Field(default="1.0", description="API version")


class ErrorDetail(BaseSchema):
    """Error details for failed requests."""

    code: str = Field(description="Machine-readable error code")
    message: str = Field(description="Human-readable error message")
    field: str | None = Field(default=None, description="Field that caused the error")


class ApiResponse(BaseSchema, Generic[T]):
    """Standard API response envelope."""

    success: bool
    data: T | None = None
    error: ErrorDetail | None = None
    meta: ResponseMeta


class PaginatedResponse(BaseSchema, Generic[T]):
    """Paginated response structure."""

    items: list[T]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    has_next: bool


def ok_response(data: Any, request_id: str) -> dict:
    """Build a successful response."""
    return {
        "success": True,
        "data": data,
        "error": None,
        "meta": {
            "request_id": request_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "version": "1.0",
        },
    }


def error_response(
    code: str,
    message: str,
    request_id: str,
    field: str | None = None,
) -> dict:
    """Build an error response."""
    return {
        "success": False,
        "data": None,
        "error": {
            "code": code,
            "message": message,
            "field": field,
        },
        "meta": {
            "request_id": request_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "version": "1.0",
        },
    }
