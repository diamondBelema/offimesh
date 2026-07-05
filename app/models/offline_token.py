"""Offline token model with two-clock expiry."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.device import Device


class OfflineToken(Base):
    """
    Offline spending token.

    Two-clock expiry system:
    - customer_spend_cutoff: Customer device must stop generating new spends
    - expires_at: Token is dead, refund remaining balance to user

    Anti-double-spend: Each token has unique serial, tracked via settlement_claims.
    """
    __tablename__ = "offline_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    token_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    serial: Mapped[str] = mapped_column(
        String(32),  # ULID - immutable unique identifier
        unique=True,
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    device_fingerprint_hash: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )
    amount_kobo: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    amount_used_kobo: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )
    nonce: Mapped[str] = mapped_column(
        String(64),  # Server-generated 32-byte random nonce
        unique=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        nullable=False,
        index=True,
    )
    server_signature: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    customer_spend_cutoff: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    refunded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="tokens")
    device: Mapped["Device"] = relationship("Device")

    __table_args__ = (
        Index("ix_tokens_token_id_status", "token_id", "status"),
        Index("ix_tokens_user_status", "user_id", "status"),
        Index("ix_tokens_serial_status", "serial", "status"),
        Index("ix_tokens_expires_status", "expires_at", "status"),
    )

    @property
    def remaining_kobo(self) -> int:
        """Calculate remaining spending amount."""
        return max(0, self.amount_kobo - self.amount_used_kobo)

    @property
    def is_exhausted(self) -> bool:
        """Check if token spending limit is exhausted."""
        return self.amount_used_kobo >= self.amount_kobo

    @property
    def is_expired(self) -> bool:
        """Check if token has expired."""
        return datetime.utcnow() >= self.expires_at

    @property
    def is_spend_locked(self) -> bool:
        """Check if customer can no longer generate new spends."""
        return datetime.utcnow() >= self.customer_spend_cutoff

    def __repr__(self) -> str:
        return f"<OfflineToken {self.token_id} serial={self.serial}>"
