"""Blacklisted devices model."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class BlacklistedDevice(Base):
    """
    Blacklisted devices that are blocked from all sensitive operations.

    Auto-populated by fraud detection Celery tasks.
    """
    __tablename__ = "blacklisted_devices"

    device_fingerprint_hash: Mapped[str] = mapped_column(
        String(128),
        primary_key=True,
    )
    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    auto_blacklisted: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )
    blacklisted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
        nullable=False,
    )
    blacklisted_by: Mapped[str | None] = mapped_column(
        String(128),  # User ID if manual, "system" if auto
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<BlacklistedDevice {self.device_fingerprint_hash[:16]}...>"
