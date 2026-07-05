"""User model."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import engine
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.device import Device
    from app.models.token import OfflineToken
    from app.models.virtual_account import VirtualAccount


class User(Base):
    """
    User model representing both customers and merchants.

    Phone numbers are stored as scrypt hashes with per-user salt.
    Actual phone (for support lookup) is stored encrypted.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    phone_hash: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
        index=True,
    )
    phone_salt: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    phone_encrypted: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
    )
    bvn: Mapped[str | None] = mapped_column(
        String(255),  # Encrypted
        nullable=True,
    )
    bvn_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )
    bvn_verification_reference: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    nin_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )
    nin_verification_reference: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    face_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )
    pin_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    role: Mapped[str] = mapped_column(
        String(20),
        default="customer",
        nullable=False,
    )
    trust_level: Mapped[str] = mapped_column(
        String(20),
        default="standard",
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending_verification",
        nullable=False,
    )
    nomba_virtual_account_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    balance_kobo: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
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

    # Relationships
    devices: Mapped[list["Device"]] = relationship(
        "Device",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    tokens: Mapped[list["OfflineToken"]] = relationship(
        "OfflineToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    virtual_accounts: Mapped[list["VirtualAccount"]] = relationship(
        "VirtualAccount",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_users_phone_hash", "phone_hash"),
        Index("ix_users_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<User {self.id}>"
