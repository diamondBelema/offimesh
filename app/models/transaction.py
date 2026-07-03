"""Transaction models."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Transaction(Base):
    """
    Transaction model for both offline and online payments.

    All monetary values in kobo (integer).
    Uses ULID for transaction IDs (lexicographically sortable).
    """

    __tablename__ = "transactions"

    tx_id: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
    )
    payer_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    payee_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    amount_kobo: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        default="NGN",
        nullable=False,
    )
    offline_token_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("offline_tokens.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    merchant_reference: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )
    nomba_reference: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )
    payer_signature: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    merchant_signature: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    signed_payload_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    fraud_score: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    nonce: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
    )
    sequence_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    initiated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    settled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_transactions_status_created", "status", "created_at"),
        Index("ix_transactions_payer_status", "payer_user_id", "status"),
        Index("ix_transactions_payee_status", "payee_user_id", "status"),
    )


class TransactionEvent(Base):
    """
    Transaction event log for state machine tracking.
    Immutable append-only event store.
    """

    __tablename__ = "transaction_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tx_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("transactions.tx_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_tx_events_tx_id_created", "tx_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<TransactionEvent {self.event_type} for {self.tx_id}>"
