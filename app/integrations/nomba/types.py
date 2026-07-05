"""Nomba API types and data models.

All responses are strictly typed using Pydantic models with
extra="forbid" to catch unexpected fields and strict=True
for precise type validation.
"""
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator


class NombaAuthResponse(BaseModel):
    """Nomba authentication response."""

    model_config = ConfigDict(extra="forbid", strict=True)

    access_token: str = Field(description="Bearer access token (redacted in logs)")
    expires_in: int = Field(default=3600, description="Token TTL in seconds")
    token_type: str = Field(default="Bearer", description="Token type")


class NombaVirtualAccountResponse(BaseModel):
    """Nomba virtual account response."""

    model_config = ConfigDict(extra="forbid", strict=True)

    account_id: str = Field(description="Nomba's internal account ID")
    account_ref: str = Field(description="Our stable reference")
    account_name: str = Field(description="Account holder name")
    account_number: str = Field(description="10-digit NUBAN")
    bank_name: str = Field(description="Bank name (typically 'Nomba')")
    bank_code: str = Field(description="Bank code")
    status: str = Field(description="Account status")


class NombaBankLookupResponse(BaseModel):
    """Bank account lookup response."""

    model_config = ConfigDict(extra="forbid", strict=True)

    account_name: str = Field(description="Verified account holder name")
    account_number: str = Field(description="10-digit NUBAN")
    bank_code: str = Field(description="Bank code used for lookup")
    bank_name: str = Field(description="Bank name")


# Alias for backwards compatibility
NombiTransferLookupResponse = NombaBankLookupResponse


class NombaTransferResponse(BaseModel):
    """Nomba transfer response."""

    model_config = ConfigDict(extra="forbid", strict=True)

    transfer_id: str = Field(description="Nomba's transfer ID")
    reference: str = Field(description="Our merchantTxRef")
    status: str = Field(description="Transfer status (pending, success, failed)")
    amount: int = Field(description="Transfer amount in kobo")
    fee: int = Field(default=0, description="Transfer fee in kobo")
    created_at: str = Field(description="ISO timestamp")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Normalize status to lowercase."""
        return v.lower()


class NombaTransactionResponse(BaseModel):
    """Nomba transaction response."""

    model_config = ConfigDict(extra="forbid", strict=True)

    transaction_id: str = Field(description="Nomba's transaction ID")
    reference: str = Field(description="Transaction reference")
    type: str = Field(description="Transaction type")
    status: str = Field(description="Transaction status")
    amount: int = Field(description="Amount in kobo")
    currency: str = Field(default="NGN", description="Currency code")
    created_at: str = Field(description="ISO timestamp")


class NombaWebhookEvent(BaseModel):
    """Nomba webhook event structure."""

    model_config = ConfigDict(extra="forbid", strict=True)

    request_id: str = Field(description="Unique event ID for idempotency")
    event: str = Field(description="Event type (e.g., 'virtual_account_funded')")
    data: dict = Field(description="Event payload")
    timestamp: str | None = Field(default=None, description="Event timestamp")


class NombaSubAccountResponse(BaseModel):
    """Nomba sub-account response."""

    model_config = ConfigDict(extra="forbid", strict=True)

    account_id: str = Field(description="Nomba's sub-account ID")
    account_ref: str = Field(description="Our stable reference")
    account_name: str = Field(description="Sub-account name")
    parent_account_id: str | None = Field(default=None, description="Parent account ID")
    status: str = Field(default="active", description="Sub-account status")
    created_at: str | None = Field(default=None, description="Creation timestamp")


class NombaBalanceResponse(BaseModel):
    """Nomba balance response."""

    model_config = ConfigDict(extra="forbid", strict=True)

    balance: int = Field(default=0, description="Balance in kobo")
    currency: str = Field(default="NGN", description="Currency code")
    available_balance: int | None = Field(default=None, description="Available balance in kobo")
    ledger_balance: int | None = Field(default=None, description="Ledger balance in kobo")


class NombaTransactionListResponse(BaseModel):
    """Nomba transaction list response."""

    model_config = ConfigDict(extra="forbid", strict=True)

    transactions: list[NombaTransactionResponse] = Field(default_factory=list)
    total: int | None = Field(default=None, description="Total count")
    page: int | None = Field(default=None, description="Current page")
    page_size: int | None = Field(default=None, description="Page size")
