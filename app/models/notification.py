"""Notification models for user alerts and transaction updates."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Notification(Base):
    """
    Notifications for users - alerts, updates, transaction status changes.

    Pushed to users via Supabase Realtime for instant delivery.
    """
    __tablename__ = "notifications"

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
    notification_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    data: Mapped[dict | None] = mapped_column(
        "data",
        JSONB,
        nullable=True,
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
        nullable=False,
        index=True,
    )

    __table_args__ = (
        Index("ix_notifications_user_created", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Notification {self.notification_type} for {self.user_id}>"


class NotificationPreference(Base):
    """
    User notification preferences - which types they want to receive.
    """
    __tablename__ = "notification_preferences"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    push_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )
    email_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )
    sms_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )
    transaction_notifications: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )
    security_notifications: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )
    promotional_notifications: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
        onupdate="now()",
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<NotificationPreference for {self.user_id}>"
