"""Fraud signals model for risk scoring."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FraudSignal(Base):
    """
    Fraud signals for risk scoring and auto-blacklisting.

    Accumulated signals trigger auto-blacklisting via Celery task.
    """
    __tablename__ = "fraud_signals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    device_fingerprint_hash: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )
    signal_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    score_contribution: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    checkpoint: Mapped[str] = mapped_column(
        String(50),  # 'token_provisioning' or 'settlement_sync'
        nullable=False,
    )
    context: Mapped[dict | None] = mapped_column(
        "context",
        JSONB,
        nullable=True,
    )
    action_taken: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
        nullable=False,
        index=True,
    )

    __table_args__ = (
        Index("ix_fraud_signals_device_created", "device_fingerprint_hash", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<FraudSignal {self.signal_type} +{self.score_contribution}>"
