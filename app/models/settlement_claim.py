"""Settlement claims model - merchant claims against offline tokens."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SettlementClaim(Base):
    """
    Settlement claim submitted by merchant against an offline token.

    The UNIQUE constraint on settlement_serial is the anti-double-spend mechanism.
    First claim to commit wins - subsequent claims are rejected.
    """
    __tablename__ = "settlement_claims"
    __table_args__ = (
        UniqueConstraint("settlement_serial", name="uq_settlement_claims_serial"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    settlement_serial: Mapped[str] = mapped_column(
        String(32),  # ULID format
        nullable=False,
        index=True,
    )
    token_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("offline_tokens.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    token_serial: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    merchant_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    customer_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    amount_kobo: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        nullable=False,
        index=True,
    )
    token_nonce: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    customer_signature: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    merchant_signature: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    payload_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    claimed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
        nullable=False,
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    fraud_score: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    flagged_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<SettlementClaim {self.settlement_serial} {self.amount_kobo}kobo>"
