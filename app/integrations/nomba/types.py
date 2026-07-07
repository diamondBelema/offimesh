"""Nomba API types and data models.

All responses use extra="ignore" to tolerate undocumented response fields.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NombaAuthResponse(BaseModel):
    """Nomba authentication response.

    Nomba returns: businessId, access_token, refresh_token, expiresAt
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
    """Nomba virtual account response."""

    model_config = ConfigDict(extra="ignore", strict=False, populate_by_name=True)

    account_id: str = Field(default="", validation_alias="accountId", description="Nomba's internal account ID (may be absent in sub-account-scoped creation)")
    account_holder_id: str = Field(default="", validation_alias="accountHolderId", description="Account holder ID (used for webhook registration)")
    account_ref: str = Field(validation_alias="accountRef", description="Our stable reference")
    account_name: str = Field(validation_alias="accountName", description="Account holder name")
    account_number: str = Field(validation_alias="bankAccountNumber", description="10-digit NUBAN")
    bank_name: str = Field(validation_alias="bankName", description="Bank name (typically 'Nombank MFB')")
    status: str = Field(default="active", validation_alias="status", description="Account status")


class NombaBankLookupResponse(BaseModel):
    """Bank account name lookup response.

    Nomba returns: accountNumber, accountName (camelCase).
    """

    model_config = ConfigDict(extra="ignore", strict=False, populate_by_name=True)

    account_name: str = Field(validation_alias="accountName", description="Verified account holder name")
    account_number: str = Field(validation_alias="accountNumber", description="10-digit NUBAN")


class NombaTransferResponse(BaseModel):
    """Nomba transfer response.

    Parses both BankAccountTransferResult (POST /v2/transfers/bank)
    and TransactionResult (GET /v1/transactions/accounts/single).
    """

    model_config = ConfigDict(extra="ignore", strict=False, populate_by_name=True)

    transfer_id: str = Field(validation_alias="id", description="Nomba's transfer/transaction ID")
    reference: str = Field(default="", validation_alias="merchantTxRef", description="Our merchant transaction reference")
    status: str = Field(default="", description="Transfer status")
    amount: float = Field(default=0.0, description="Transfer amount in Naira")
    fee: float = Field(default=0.0, description="Transfer fee in Naira")
    created_at: str = Field(default="", validation_alias="timeCreated", description="ISO timestamp")

    @field_validator("status")
    @classmethod
    def normalize_status(cls, v: str) -> str:
        """Normalize status to lowercase."""
        return v.lower()


class NombaTransactionResponse(BaseModel):
    """Nomba transaction response.

    Maps from TransactionResult returned by Nomba's transaction endpoints.
    """

    model_config = ConfigDict(extra="ignore", strict=False, populate_by_name=True)

    transaction_id: str = Field(validation_alias="id", description="Nomba's transaction ID")
    reference: str = Field(default="", validation_alias="merchantTxRef", description="Merchant transaction reference")
    type: str = Field(default="", description="Transaction type")
    status: str = Field(default="", description="Transaction status")
    amount: float = Field(default=0.0, description="Transaction amount")
    gateway_message: str = Field(default="", validation_alias="gatewayMessage", description="Gateway message")
    source: str = Field(default="", description="Transaction source (api, pos, web, etc.)")
    created_at: str = Field(default="", validation_alias="timeCreated", description="ISO timestamp")


class NombaTransactionListResponse(BaseModel):
    """Nomba transaction list response (cursor-based pagination)."""

    model_config = ConfigDict(extra="ignore", strict=False)

    results: list[NombaTransactionResponse] = Field(default_factory=list, description="Transaction results")
    cursor: str | None = Field(default=None, description="Pagination cursor for next page")


class NombaWebhookEvent(BaseModel):
    """Nomba webhook event structure."""

    model_config = ConfigDict(extra="forbid", strict=True)

    request_id: str = Field(description="Unique event ID for idempotency")
    event: str = Field(description="Event type (e.g., 'virtual_account_funded')")
    data: dict = Field(description="Event payload")
    timestamp: str | None = Field(default=None, description="Event timestamp")


class NombaSubAccountResponse(BaseModel):
    """Nomba sub-account response."""

    model_config = ConfigDict(extra="ignore", strict=False, populate_by_name=True)

    account_id: str = Field(validation_alias="accountId", description="Nomba's sub-account ID")
    account_ref: str = Field(default="", validation_alias="accountRef", description="Our stable reference")
    account_name: str = Field(validation_alias="accountName", description="Sub-account name")
    parent_account_id: str | None = Field(default=None, validation_alias="parentAccountId", description="Parent account ID")
    status: str = Field(default="active", validation_alias="status", description="Sub-account status")
    created_at: str | None = Field(default=None, validation_alias="timeCreated", description="Creation timestamp")


# Backwards compatibility alias
NombiTransferLookupResponse = NombaBankLookupResponse


class NombaBalanceResponse(BaseModel):
    """Nomba balance response."""

    model_config = ConfigDict(extra="ignore", strict=False, populate_by_name=True)

    balance: float = Field(default=0.0, description="Balance")
    currency: str = Field(default="NGN", description="Currency code")
    available_balance: float | None = Field(default=None, validation_alias="availableBalance", description="Available balance")
    ledger_balance: float | None = Field(default=None, validation_alias="ledgerBalance", description="Ledger balance")
