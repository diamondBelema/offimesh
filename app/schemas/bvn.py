"""BVN verification Pydantic schemas."""
from __future__ import annotations

from pydantic import Field, field_validator

from app.schemas.base import BaseSchema


# --- Request Schemas ---


class InitiateBVNRequest(BaseSchema):
    """Request to initiate BVN verification."""

    bvn: str = Field(min_length=11, max_length=11, description="11-digit BVN")

    @field_validator("bvn")
    @classmethod
    def validate_bvn(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("BVN must contain only digits")
        return v


class ConfirmBVNRequest(BaseSchema):
    """Request to confirm BVN with OTP."""

    otp: str = Field(min_length=6, max_length=6, description="6-digit OTP from BVN verification")


# --- Response Schemas ---


class BVNInitiateResponse(BaseSchema):
    """Response from BVN initiation."""

    reference: str
    message: str
    requires_otp: bool = True


class BVNStatusResponse(BaseSchema):
    """BVN verification status."""

    verified: bool
    status: str = Field(description="pending, verified, failed")
    verified_at: str | None
