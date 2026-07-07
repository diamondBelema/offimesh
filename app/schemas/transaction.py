"""Transaction Pydantic schemas."""
from __future__ import annotations


from pydantic import Field, field_validator

from app.schemas.base import BaseSchema


# --- Request Schemas ---


class TransactionSyncRequest(BaseSchema):
    """Offline transaction sync request."""

    batch_id: str = Field(description="Unique batch identifier")
    device_id: str = Field(description="Device that processed transactions")
    transactions: list[dict] = Field(
        max_length=100,
        description="List of offline transactions (max 100)",
    )
    device_signature: str = Field(description="Ed25519 signature of batch payload")


class SingleTransactionData(BaseSchema):
    """Individual transaction data within a sync batch."""

    tx_id: str = Field(description="ULID transaction ID")
    token_id: str = Field(description="Offline token used")
    payer_user_id: str = Field(description="Payer user UUID")
    payee_user_id: str = Field(description="Payee/Merchant user UUID")
    amount_kobo: int = Field(ge=100, le=5000000, description="Amount in kobo")
    currency: str = Field(default="NGN", min_length=3, max_length=3)
    merchant_reference: str | None = None
    nonce: str = Field(min_length=64, max_length=64)
    sequence_number: int = Field(ge=0)
    initiated_at: str = Field(description="ISO 8601 timestamp")
    payer_signature: str = Field(description="Payer's Ed25519 signature")
    merchant_signature: str = Field(description="Merchant's Ed25519 signature")
    payload_hash: str = Field(min_length=64, max_length=64)

    @field_validator("initiated_at")
    @classmethod
    def validate_initiated_at(cls, v: str) -> str:
        # Will be validated as ISO 8601 when parsed
        return v


# --- Response Schemas ---


class TransactionSyncResponse(BaseSchema):
    """Transaction sync result response."""

    batch_id: str
    processed: int
    accepted: int
    rejected: int
    results: list[dict]


class TransactionResult(BaseSchema):
    """Individual transaction sync result."""

    tx_id: str
    status: str = Field(description="accepted, rejected, duplicate")
    reason: str | None = None


class TransactionResponse(BaseSchema):
    """Transaction data response."""

    tx_id: str
    payer_user_id: str
    payee_user_id: str
    amount_kobo: int
    currency: str
    status: str
    offline_token_id: str | None
    merchant_reference: str | None
    nomba_reference: str | None
    fraud_score: int
    initiated_at: str
    synced_at: str | None
    settled_at: str | None
    created_at: str


class TransactionListResponse(BaseSchema):
    """Paginated transaction list."""

    items: list[TransactionResponse]
    total: int
    page: int
    page_size: int
    has_next: bool
