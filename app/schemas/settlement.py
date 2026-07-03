"""Settlement Pydantic schemas."""
from __future__ import annotations

from pydantic import Field

from app.schemas.base import BaseSchema


# --- Response Schemas ---


class SettlementResponse(BaseSchema):
    """Settlement data response."""

    id: str
    tx_id: str
    nomba_transfer_id: str | None
    amount_kobo: int
    fee_kobo: int
    status: str
    attempts: int
    last_attempt_at: str | None
    settled_at: str | None
    error_code: str | None
    error_message: str | None
    created_at: str


class SettlementListResponse(BaseSchema):
    """Paginated settlement list."""

    items: list[SettlementResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class SettlementProcessResponse(BaseSchema):
    """Response from processing a settlement."""

    tx_id: str
    success: bool
    nomba_reference: str | None
    status: str
    message: str | None
