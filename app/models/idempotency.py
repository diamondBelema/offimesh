"""Idempotency key model."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class IdempotencyKey(Base):
    """
    Idempotency key model for preventing duplicate operations.

    Stores the request hash and cached response for replay.
    """

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(
        String(128),
        primary_key=True,
    )
    request_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    response: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        Index("ix_idempotency_expires", "expires_at"),
    )

    def __repr__(self) -> str:
        return f"<IdempotencyKey {self.key}>"
