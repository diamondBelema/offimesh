"""Wallet Pydantic schemas."""
from __future__ import annotations

from pydantic import Field

from app.schemas.base import BaseSchema


# --- Request Schemas ---


class FundWalletRequest(BaseSchema):
    """Request to create a virtual account for wallet funding."""

    expected_amount_kobo: int | None = Field(
        default=None,
        ge=10000,  # Minimum 100 Naira
        le=100000000,  # Maximum 1,000,000 Naira
        description="Expected funding amount (optional, for reference)",
    )


# --- Response Schemas ---


class VirtualAccountResponse(BaseSchema):
    """Virtual account details for funding."""

    id: str
    nuban: str = Field(description="10-digit NUBAN account number")
    account_name: str
    bank_name: str = "Nomba"
    expected_amount_kobo: int | None
    status: str
    created_at: str
    expires_at: str | None


class WalletBalanceResponse(BaseSchema):
    """Wallet balance response."""

    balance_kobo: int
    pending_kobo: int = Field(description="Pending settlements")
    available_kobo: int = Field(description="Available for offline spending")
    last_updated: str


class FundingStatusResponse(BaseSchema):
    """Status of wallet funding account."""

    account_id: str
    nuban: str
    status: str
    expected_amount_kobo: int | None
    received_amount_kobo: int | None
    created_at: str
