"""Settlement model."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Settlement(Base):
    """
    Settlement model for tracking payment settlements via Nomba.
    """

    __tablename__ = "settlements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tx_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("transactions.tx_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    nomba_transfer_id: Mapped[str | None] = mapped_column(
        String(128),
        unique=True,
        nullable=True,
    )
    amount_kobo: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    fee_kobo: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    settled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    error_code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    bank_code: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )
    account_number: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )
    account_name: Mapped[str | None] = mapped_column(
        String(255),
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
        # Index for finding pending settlements
        # UniqueConstraint("nomba_transfer_id", name="uq_settlements_nomba_transfer_id"),
    )

    def __repr__(self) -> str:
        return f"<Settlement {self.id} for {self.tx_id}>"
