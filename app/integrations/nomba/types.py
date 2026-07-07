"""
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

    Matches the actual CreateVirtualAccountResponse / VirtualAccountObject
    schema returned by:
      POST /v1/accounts/virtual/{subAccountId}
      GET  /v1/accounts/virtual/{identifier}
      POST /v1/accounts/virtual/list  (per-item shape)

    IMPORTANT: Nomba does NOT return an "accountId" field for virtual
    accounts -- only "accountHolderId". A previous version of this model
    required "accountId", which does not exist in the real response and
    caused every parse to raise a ValidationError. Fixed here.

    There is also no "status" field on virtual account responses --
    only "expired" (bool). `status` below is derived from that for
    backwards compatibility with any calling code that reads `.status`.
    """

    model_config = ConfigDict(extra="ignore", strict=False, populate_by_name=True)

    account_holder_id: str = Field(
        validation_alias="accountHolderId",
        description="Nomba's account holder ID for this virtual account",
    )
    account_ref: str = Field(
        validation_alias="accountRef",
        description=(
            "Our stable reference. This is the webhook correlation key -- "
            "it appears as data.transaction.aliasAccountReference in "
            "payment_success webhook payloads."
        ),
    )
    account_name: str = Field(validation_alias="accountName", description="Account holder name")
    account_number: str = Field(validation_alias="bankAccountNumber", description="10-digit NUBAN")
    bank_account_name: str = Field(
        default="", validation_alias="bankAccountName", description="Bank account holder name"
    )
    bank_name: str = Field(default="", validation_alias="bankName", description="Bank name (e.g. 'Nombank MFB')")
    currency: str = Field(default="NGN", validation_alias="currency")
    bvn: str = Field(default="", validation_alias="bvn")
    expired: bool = Field(default=False, validation_alias="expired", description="Whether the account has expired")
    callback_url: str = Field(default="", validation_alias="callbackUrl")
    created_at: str = Field(default="", validation_alias="createdAt")

    @property
    def status(self) -> str:
        """Derived status ('active'/'expired') since Nomba has no status field for virtual accounts."""
        return "expired" if self.expired else "active"


class NombaBankLookupResponse(BaseModel):
    """Bank account lookup response.

    Real Nomba response is ONLY { "accountNumber": ..., "accountName": ... }
    -- no bank_code or bank_name are echoed back. Those are populated by
    the calling client from what it already knows (the bank_code it
    queried with), not from this response. Previously both were required
    fields with no default, which raised ValidationError on every call.
    """

    model_config = ConfigDict(extra="ignore", strict=False, populate_by_name=True)

    account_name: str = Field(validation_alias="accountName", description="Verified account holder name")
    account_number: str = Field(validation_alias="accountNumber", description="10-digit NUBAN")
    bank_code: str = Field(default="", description="Bank code used for lookup (set by caller, not returned by Nomba)")
    bank_name: str = Field(default="", description="Bank name (not returned by this endpoint; use fetch-bank-codes if needed)")


# Alias for backwards compatibility
NombiTransferLookupResponse = NombaBankLookupResponse


class NombaTransferResponse(BaseModel):
    """Nomba transfer response.

    Real immediate response (per docs) is minimal:
      { "successful": true, "status": "SUCCESS",
        "data": { "id": "API-TRANSFER-...", "status": "SUCCESS" } }

    Previously this model required transfer_id, reference, amount, fee,
    and created_at with extra="forbid" -- none of those exist in the
    real payload, so every real transfer response raised a
    ValidationError immediately after the HTTP call succeeded.

    reference (your merchantTxRef) and amount are not echoed back by
    Nomba -- the calling client already knows both values (it sent
    them), so it should attach them itself after parsing rather than
    expect Nomba to return them.
    """

    model_config = ConfigDict(extra="ignore", strict=False, populate_by_name=True)

    transfer_id: str = Field(validation_alias="id", description="Nomba's transfer ID (data.id) -- save this for requery")
    status: str = Field(description="Transfer status: SUCCESS, PENDING_BILLING, or NEW")
    reference: str = Field(default="", description="Your merchantTxRef -- not returned by Nomba, set by caller")
    amount: int = Field(default=0, description="Transfer amount in kobo -- not returned by Nomba, set by caller")
    fee: int = Field(default=0, description="Transfer fee in kobo, if known")
    created_at: str = Field(default="", description="ISO timestamp, if known")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Normalize status to uppercase to match Nomba's SUCCESS/PENDING_BILLING/NEW values."""
        return v.upper()


class NombaTransactionResponse(BaseModel):
    """Nomba transaction response.

    Matches the real shape from /v1/transactions/accounts and
    /v1/transactions/accounts/single, confirmed from Nomba's docs
    example:
      { "id": "POS-WITHDRAW-...", "status": "PAYMENT_FAILED",
        "amount": 4000, "fixedCharge": 123, "source": "pos",
        "type": "withdrawal", "gatewayMessage": "Insufficient funds",
        "timeCreated": "2023-09-08T19:26:34.657000Z",
        "terminalId": "2KUD4AKB", "rrn": "230908202632",
        "userId": "...", "merchantTxRef": "c90d-4b25-ad0f" }

    Previously this required transaction_id, reference, currency, and
    created_at with extra="forbid" -- none of those field names exist
    in the real payload ("id" not "transaction_id", "merchantTxRef" not
    "reference", no "currency" at all, "timeCreated" not "created_at"),
    so every real transaction response raised a ValidationError.
    """

    model_config = ConfigDict(extra="ignore", strict=False, populate_by_name=True)

    transaction_id: str = Field(validation_alias="id", description="Nomba's transaction ID/reference")
    merchant_tx_ref: str = Field(default="", validation_alias="merchantTxRef", description="Our reference, if this transaction was initiated by us")
    status: str = Field(description="Transaction status, e.g. SUCCESS, PAYMENT_FAILED")
    amount: int = Field(default=0, description="Transaction amount -- confirm units (kobo vs Naira) against a known sandbox transaction before relying on this for reconciliation math")
    fixed_charge: int = Field(default=0, validation_alias="fixedCharge")
    source: str = Field(default="", description="e.g. 'pos', 'api', 'checkout'")
    type: str = Field(default="", description="Transaction type, e.g. 'withdrawal'")
    gateway_message: str = Field(default="", validation_alias="gatewayMessage")
    terminal_id: str = Field(default="", validation_alias="terminalId")
    rrn: str = Field(default="", description="Retrieval Reference Number")
    user_id: str = Field(default="", validation_alias="userId")
    time_created: str = Field(default="", validation_alias="timeCreated", description="ISO timestamp")
    currency: str = Field(default="NGN", description="Not actually returned by Nomba; defaulted for compatibility with existing calling code")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Normalize status to uppercase to match Nomba's real values (SUCCESS, PAYMENT_FAILED, etc.)."""
        return v.upper()


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


class NombaSubAccountBalanceResponse(BaseModel):
    """
    Response from GET /v1/accounts/{subAccountId}/balance.

    Real response shape: amount is a STRING (e.g. "281946.0"), not an
    int in kobo -- convert explicitly if kobo is needed downstream.
    """

    model_config = ConfigDict(extra="ignore", strict=False)

    amount: str = Field(default="0", description="Balance as a decimal string, in Naira")
    currency: str = Field(default="NGN", description="Currency code")
    time_created: str = Field(default="", validation_alias="timeCreated", description="Timestamp of this balance snapshot")

    @property
    def amount_kobo(self) -> int:
        """Convert the Naira decimal string balance to kobo."""
        try:
            return int(round(float(self.amount) * 100))
        except (TypeError, ValueError):
            return 0


class NombaSubAccountDetailsResponse(BaseModel):
    """
    Response from GET /v1/accounts/sub-account-details.

    Matches the account resource shape confirmed from Nomba's docs
    (same shape used for parent account details):
    accountId, accountHolderId, accountRef, phoneNumber, email, bvn,
    status, type, accountName, currency, callbackUrl, expiryDate,
    createdAt.
    """

    model_config = ConfigDict(extra="ignore", strict=False, populate_by_name=True)

    account_id: str = Field(default="", validation_alias="accountId")
    account_holder_id: str = Field(default="", validation_alias="accountHolderId")
    account_ref: str = Field(default="", validation_alias="accountRef")
    account_name: str = Field(default="", validation_alias="accountName")
    phone_number: str = Field(default="", validation_alias="phoneNumber")
    email: str = Field(default="", validation_alias="email")
    bvn: str = Field(default="", validation_alias="bvn")
    status: str = Field(default="", validation_alias="status")
    type: str = Field(default="", validation_alias="type")
    currency: str = Field(default="NGN", validation_alias="currency")
    callback_url: str = Field(default="", validation_alias="callbackUrl")
    created_at: str = Field(default="", validation_alias="createdAt")


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
