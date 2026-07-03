"""Device-related Pydantic schemas."""
from __future__ import annotations

from pydantic import Field

from app.schemas.base import BaseSchema


# --- Request Schemas ---


class DeviceRegisterRequest(BaseSchema):
    """Device registration request."""

    device_fingerprint: str = Field(
        min_length=16,
        max_length=128,
        description="Unique device identifier from attestation",
    )
    device_public_key: str = Field(
        min_length=64,
        description="Ed25519 public key in hex format",
    )
    attestation_token: str | None = Field(
        default=None,
        description="Platform attestation token (Apple/Android)",
    )
    device_name: str | None = Field(default=None, max_length=255)
    device_type: str | None = Field(default=None, pattern="^(ios|android|web)$")


# --- Response Schemas ---


class DeviceResponse(BaseSchema):
    """Device data response."""

    id: str
    device_name: str | None
    device_type: str | None
    trust_level: str
    last_seen_at: str | None
    registered_at: str


class DeviceListResponse(BaseSchema):
    """List of user devices."""

    devices: list[DeviceResponse]
    total: int
