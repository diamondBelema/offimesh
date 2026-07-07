"""Nomba API types and data models.

All responses are strictly typed using Pydantic models with
extra="forbid" to catch unexpected fields and strict=True
for precise type validation.
"""
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator


class NombaAuthResponse(BaseModel):
    """Nomba authentication response.

    Nomba returns: businessId, access_token, refresh_token, expiresAt
    We map camelCase to snake_case and ignore extra fields gracefully.
    """

    model_config = ConfigDict(extra="ignore", strict=False)

    access_token: str = Field(description="Bearer access token (redacted in logs)")
    refresh_token: str = Field(default="", description="Token used to refresh an expired access_token")
    expires_at: str = Field(default="", validation_alias="expiresAt", description="ISO 8601 expiry timestamp")
    business_id: str = Field(default="", validation_alias="businessId", description="Nomba account ID")

    @property
    def expires_in(self) -> int:
        """Derive seconds-until-expiry from expires_at timestamp."""
        if not self.expires_at:
            return 3600
        try:
            from datetime import datetime, timezone
            exp = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            remaining = int((exp - datetime.now(timezone.utc)).total_seconds())
            return max(remaining, 60)
        except Exception:
            return 3600


class NombaVirtualAccountResponse(BaseModel):
    """Nomba virtual account response.

    Nomba returns camelCase fields. We alias to snake_case and
    ignore extra fields so the parser doesn't break on spec changes.
    """

    model_config = ConfigDict(extra="ignore", strict=False, populate_by_name=True)

    account_id: str = Field(validation_alias="accountId", description="Nomba's internal account ID")
    account_ref: str = Field(validation_alias="accountRef", description="Our stable reference")
    account_name: str = Field(validation_alias="accountName", description="Account holder name")
    account_number: str = Field(validation_alias="bankAccountNumber", description="10-digit NUBAN")
    bank_name: str = Field(validation_alias="bankName", description="Bank name (typically 'Nombank MFB')")
    status: str = Field(default="active", validation_alias="status", description="Account status")


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
