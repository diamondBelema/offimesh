"""Nomba sub-account model for internal treasury bookkeeping."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class NombaSubAccount(Base):
    """
    Nomba sub-account for internal treasury operations.

    IMPORTANT: Only ONE sub-account for the whole OffiMesh operation.
    This is NOT per-user. Used for balance tracking and reconciliation.

    Virtual accounts are NEVER scoped to this sub-account - see
    app/integrations/nomba/sub_accounts.py for the architectural reason.
    """
    __tablename__ = "nomba_sub_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    nomba_sub_account_id: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
        index=True,
    )
    account_ref: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
        index=True,
    )
    account_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    purpose: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="operational_treasury",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<NombaSubAccount {self.account_ref}>"


class SubAccountBalanceSnapshot(Base):
    """
    Daily snapshot of sub-account balance for reconciliation.

    Used to compare our internal ledger_balances sum against
    what Nomba reports for the treasury bucket, to catch any drift.
    """
    __tablename__ = "sub_account_balance_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    sub_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nomba_sub_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    balance_kobo: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
        nullable=False,
        index=True,
    )
    ledger_total_kobo: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    discrepancy_kobo: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    __table_args__ = (
        Index("ix_balance_snapshots_sub_account_captured", "sub_account_id", "captured_at"),
    )

    def __repr__(self) -> str:
        return f"<SubAccountBalanceSnapshot {self.balance_kobo} at {self.captured_at}>"
