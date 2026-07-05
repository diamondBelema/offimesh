"""Virtual account model for wallet funding."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class VirtualAccount(Base):
    """
    Virtual account model for Nomba bank transfer funding.

    When a user wants to fund their wallet, we create a virtual
    NUBAN account that they can transfer to from any Nigerian bank.
    """

    __tablename__ = "virtual_accounts"

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
    nomba_account_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )
    account_ref: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
    )
    nuban: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        index=True,
    )
    account_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    bank_name: Mapped[str] = mapped_column(
        String(100),
        default="Nomba",
        nullable=False,
    )
    expected_amount_kobo: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    received_amount_kobo: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
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

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="virtual_accounts")

    __table_args__ = (
        Index("ix_virtual_accounts_user_status", "user_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<VirtualAccount {self.nuban}>"
