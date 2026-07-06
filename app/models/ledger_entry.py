"""Ledger entries model - immutable audit trail."""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EntryType(str, Enum):
    """Ledger entry types."""
    credit = "credit"
    debit = "debit"


class ReferenceType(str, Enum):
    """Reference types for ledger entries."""
    wallet_topup = "wallet_topup"
    offline_token_issue = "offline_token_issue"
    offline_token_refund = "offline_token_refund"
    p2p_settlement = "p2p_settlement"
    withdrawal = "withdrawal"
    settlement_credit = "settlement_credit"
    settlement_debit = "settlement_debit"


class LedgerEntry(Base):
    """
    Immutable append-only ledger entry.

    Every balance change writes a row here.
    Balance should always be re-derivable by summing entries.

    ENFORCE APPEND-ONLY AT DB LEVEL (no UPDATE/DELETE rules).
    """
    __tablename__ = "ledger_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    entry_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    amount_kobo: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    reference_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    reference_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )
    balance_after_kobo: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    entry_metadata: Mapped[dict | None] = mapped_column(
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
        Index("ix_ledger_entries_user_created", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<LedgerEntry {self.entry_type} {self.amount_kobo} for {self.user_id}>"
