"""Device activity log for trust scoring and anomaly detection."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DeviceActivityLog(Base):
    """
    Log of device activity for trust scoring and anomaly detection.

    Used to detect impossible travel patterns and suspicious behavior.
    """
    __tablename__ = "device_activity_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
    )
    gps_lat: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    gps_lng: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    play_integrity_verdict: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    device_trust_score: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    activity_metadata: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
        nullable=False,
        index=True,
    )

    __table_args__ = (
        Index("ix_device_activity_device_created", "device_id", "created_at"),
        Index("ix_device_activity_user_created", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<DeviceActivityLog {self.action} device={self.device_id}>"
