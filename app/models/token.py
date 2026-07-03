"""Offline token model."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.device import Device


class OfflineToken(Base):
    """
    Offline spending token model.

    Pre-authorized tokens that allow offline payments up to a limit.
    Signed by the server and have a limited TTL.
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
    spending_limit_kobo: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    amount_used_kobo: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        nullable=False,
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

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="tokens")
    device: Mapped["Device"] = relationship("Device")

    __table_args__ = (
        Index("ix_tokens_token_id_status", "token_id", "status"),
        Index("ix_tokens_user_status", "user_id", "status"),
    )

    @property
    def remaining_kobo(self) -> int:
        """Calculate remaining spending amount."""
        return max(0, self.spending_limit_kobo - self.amount_used_kobo)

    @property
    def is_exhausted(self) -> bool:
        """Check if token spending limit is exhausted."""
        return self.amount_used_kobo >= self.spending_limit_kobo

    @property
    def is_expired(self) -> bool:
        """Check if token has expired."""
        return datetime.utcnow() >= self.expires_at

    def __repr__(self) -> str:
        return f"<OfflineToken {self.token_id}>"
