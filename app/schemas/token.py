"""Offline token Pydantic schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.base import BaseSchema


# --- Request Schemas ---


class ProvisionTokenRequest(BaseSchema):
    """Offline token provisioning request."""

    requested_limit_kobo: int = Field(
        ge=1000,
        le=500000,
        description="Requested spending limit in kobo",
    )
    device_id: str | None = Field(
        default=None,
        description="Specific device to bind token to",
    )


# --- Response Schemas ---


class OfflineTokenResponse(BaseSchema):
    """Offline token data response."""

    token_id: str
    spending_limit_kobo: int
    amount_used_kobo: int
    remaining_kobo: int
    status: str
    expires_at: str
    server_signature: str


class ActiveTokenResponse(BaseSchema):
    """Active offline token response."""

    token_id: str
    spending_limit_kobo: int
    remaining_kobo: int
    expires_at: str
    status: str
    device_id: str


class TokenListResponse(BaseSchema):
    """List of user tokens."""

    tokens: list[OfflineTokenResponse]
    total: int
