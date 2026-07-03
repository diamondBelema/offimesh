"""Nomba API types and data models."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class NombaAuthResponse(BaseModel):
    """Nomba authentication response."""

    model_config = ConfigDict(extra="forbid", strict=True)

    access_token: str
    expires_in: int = 3600
    token_type: str = "Bearer"


class NombaVirtualAccountResponse(BaseModel):
    """Nomba virtual account response."""

    model_config = ConfigDict(extra="forbid", strict=True)

    account_id: str
    account_ref: str
    account_name: str
    account_number: str = Field(description="10-digit NUBAN")
    bank_name: str
    bank_code: str
    status: str


class NombiTransferLookupResponse(BaseModel):
    """Bank account lookup response."""

    model_config = ConfigDict(extra="forbid", strict=True)

    account_name: str
    account_number: str
    bank_code: str
    bank_name: str


class NombaTransferResponse(BaseModel):
    """Nomba transfer response."""

    model_config = ConfigDict(extra="forbid", strict=True)

    transfer_id: str
    reference: str = Field(description="Our merchantTxRef")
    status: str
    amount: int
    fee: int
    created_at: str


class NombaTransactionResponse(BaseModel):
    """Nomba transaction response."""

    model_config = ConfigDict(extra="forbid", strict=True)

    transaction_id: str
    reference: str
    type: str
    status: str
    amount: int
    currency: str
    created_at: str


class NombaWebhookEvent(BaseModel):
    """Nomba webhook event structure."""

    model_config = ConfigDict(extra="forbid", strict=True)

    request_id: str
    event: str
    data: dict
    timestamp: str | None = None
