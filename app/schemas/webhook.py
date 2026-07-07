"""Webhook Pydantic schemas."""
from __future__ import annotations


from pydantic import Field

from app.schemas.base import BaseSchema


# --- Webhook Event Schemas (from Nomba) ---


class NombaWebhookPayload(BaseSchema):
    """Nomba webhook event payload."""

    request_id: str = Field(description="Unique request identifier from Nomba")
    event: str = Field(description="Event type")
    data: dict = Field(description="Event payload")
    timestamp: str | None = None


class VirtualAccountFundedData(BaseSchema):
    """Data for virtual_account.funded event."""

    account_id: str
    account_ref: str
    amount_expected: int | None
    amount_received: int
    currency: str = "NGN"
    sender_name: str | None = None
    transaction_reference: str


class TransferSuccessData(BaseSchema):
    """Data for transfer.success event."""

    transfer_id: str
    merchant_tx_ref: str
    amount: int
    status: str
    completed_at: str


class TransferFailedData(BaseSchema):
    """Data for transfer.failed event."""

    transfer_id: str
    merchant_tx_ref: str
    amount: int
    status: str
    error_code: str | None
    error_message: str | None


# --- Response Schemas ---


class WebhookEventResponse(BaseSchema):
    """Webhook event processing response."""

    request_id: str
    event_type: str
    processed: bool
    processed_at: str | None
    created_at: str
