"""Authentication-related Pydantic schemas."""
from __future__ import annotations

from pydantic import Field, field_validator

from app.schemas.base import BaseSchema


# --- Request Schemas ---


class RegisterRequest(BaseSchema):
    """User registration request."""

    phone: str = Field(
        min_length=10,
        max_length=15,
        description="Phone number in format 234XXXXXXXXXX",
    )
    name: str | None = Field(default=None, max_length=255)
    role: str = Field(default="customer", pattern="^(customer|merchant)$")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not v.startswith("234"):
            raise ValueError("Phone must start with 234 country code")
        if not v[3:].isdigit():
            raise ValueError("Phone must contain only digits after country code")
        return v


class VerifyOTPRequest(BaseSchema):
    """OTP verification request."""

    user_id: str = Field(description="User UUID")
    otp: str = Field(min_length=6, max_length=6, description="6-digit OTP")


class LoginRequest(BaseSchema):
    """Login request."""

    phone: str = Field(
        min_length=10,
        max_length=15,
        description="Phone number in format 234XXXXXXXXXX",
    )

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not v.startswith("234"):
            raise ValueError("Phone must start with 234 country code")
        return v


class RefreshTokenRequest(BaseSchema):
    """Token refresh request."""

    refresh_token: str = Field(description="Refresh token")


class CreatePINRequest(BaseSchema):
    """PIN creation request."""

    pin: str = Field(min_length=4, max_length=6, description="4-6 digit PIN")

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("PIN must contain only digits")
        return v


class VerifyPINRequest(BaseSchema):
    """PIN verification request."""

    pin: str = Field(min_length=4, max_length=6, description="4-6 digit PIN")


# --- Response Schemas ---


class RegisterResponse(BaseSchema):
    """Registration response."""

    user_id: str
    otp_sent: bool
    message: str = "OTP sent to your phone"


class TokenResponse(BaseSchema):
    """Token response."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int


class UserResponse(BaseSchema):
    """User data response."""

    id: str
    name: str | None
    phone: str | None  # Masked
    email: str | None
    role: str
    trust_level: str
    status: str
    bvn_verified: bool
    created_at: str


class UserBalanceResponse(BaseSchema):
    """User balance response."""

    balance_kobo: int
    available_kobo: int
    pending_kobo: int


class UserLimitsResponse(BaseSchema):
    """User transaction limits response."""

    daily_limit_kobo: int
    monthly_limit_kobo: int
    per_transaction_limit_kobo: int
    offline_token_max_limit_kobo: int
