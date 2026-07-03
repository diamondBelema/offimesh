"""Webhook event model."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WebhookEvent(Base):
    """
    Webhook event model for Nomba webhook processing.

    Stores all received webhooks for idempotency and audit.
    request_id is the unique idempotency key from Nomba.
    """

    __tablename__ = "webhook_events"

    __table_args__ = (
        UniqueConstraint("request_id", name="uq_webhook_events_request_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    request_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )
    raw_body: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    signature_valid: Mapped[bool] = mapped_column(
        default=False,
    )
    processed: Mapped[bool] = mapped_column(
        default=False,
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    processing_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<WebhookEvent {self.event_type} {self.request_id}>"
