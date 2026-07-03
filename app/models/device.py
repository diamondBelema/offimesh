"""Device model."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class Device(Base):
    """
    Device model for user devices.

    Stores the device's public key for signature verification
    and attestation data for trust level determination.
    """

    __tablename__ = "devices"

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
    device_fingerprint: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
        index=True,
    )
    device_public_key: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    attestation_token: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    attestation_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    trust_level: Mapped[str] = mapped_column(
        String(20),
        default="untrusted",
        nullable=False,
    )
    device_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    device_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="devices")

    __table_args__ = (
        Index("ix_devices_user_trust", "user_id", "trust_level"),
    )

    def __repr__(self) -> str:
        return f"<Device {self.id}>"
