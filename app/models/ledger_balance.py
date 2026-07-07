"""Ledger balances model - internal account balances."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LedgerBalance(Base):
    """
    Double-entry ledger balance for users.

    All money in OffiMesh is tracked here, not in Nomba accounts directly.
    Real money only moves at boundaries: deposit (virtual account) and withdrawal.
    """
    __tablename__ = "ledger_balances"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    available_balance_kobo: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )
    locked_in_offline_tokens_kobo: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
        onupdate="now()",
        nullable=False,
    )

    @property
    def total_balance_kobo(self) -> int:
        """Total balance including locked offline tokens."""
        return self.available_balance_kobo + self.locked_in_offline_tokens_kobo

    def __repr__(self) -> str:
        return f"<LedgerBalance user={self.user_id} available={self.available_balance_kobo}>"
