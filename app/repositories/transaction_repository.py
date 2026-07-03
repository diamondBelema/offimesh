"""Transaction repository - database queries only."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction, TransactionEvent


class TransactionRepository:
    """Repository for Transaction model - database queries only."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, transaction: Transaction) -> Transaction:
        """Create a new transaction."""
        self.db.add(transaction)
        await self.db.flush()
        return transaction

    async def get_by_tx_id(self, tx_id: str) -> Transaction | None:
        """Get transaction by tx_id."""
        result = await self.db.execute(
            select(Transaction).where(Transaction.tx_id == tx_id)
        )
        return result.scalar_one_or_none()

    async def get_by_nonce(self, nonce: str) -> Transaction | None:
        """Get transaction by nonce (for replay detection)."""
        result = await self.db.execute(
            select(Transaction).where(Transaction.nonce == nonce)
        )
        return result.scalar_one_or_none()

    async def exists_by_tx_id(self, tx_id: str) -> bool:
        """Check if transaction exists by tx_id."""
        result = await self.db.execute(
            select(func.count()).select_from(Transaction).where(Transaction.tx_id == tx_id)
        )
        return (result.scalar() or 0) > 0

    async def list_by_user(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
    ) -> tuple[list[Transaction], int]:
        """List transactions for a user (payer or payee)."""
        query = select(Transaction).where(
            (Transaction.payer_user_id == user_id) | (Transaction.payee_user_id == user_id)
        )
        count_query = select(func.count()).select_from(Transaction).where(
            (Transaction.payer_user_id == user_id) | (Transaction.payee_user_id == user_id)
        )

        if status:
            query = query.where(Transaction.status == status)
            count_query = count_query.where(Transaction.status == status)

        # Get total count
        total = (await self.db.execute(count_query)).scalar() or 0

        # Get paginated results
        query = query.order_by(Transaction.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        transactions = list(result.scalars().all())

        return transactions, total

    async def list_all(
        self,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
    ) -> tuple[list[Transaction], int]:
        """List all transactions with pagination."""
        query = select(Transaction)
        count_query = select(func.count()).select_from(Transaction)

        if status:
            query = query.where(Transaction.status == status)
            count_query = count_query.where(Transaction.status == status)

        # Get total count
        total = (await self.db.execute(count_query)).scalar() or 0

        # Get paginated results
        query = query.order_by(Transaction.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        transactions = list(result.scalars().all())

        return transactions, total

    async def update_status(self, tx_id: str, status: str) -> None:
        """Update transaction status."""
        from sqlalchemy import update
        await self.db.execute(
            update(Transaction).where(Transaction.tx_id == tx_id).values(status=status)
        )

    async def mark_settled(self, tx_id: str, nomba_reference: str) -> None:
        """Mark transaction as settled."""
        from sqlalchemy import update
        await self.db.execute(
            update(Transaction).where(Transaction.tx_id == tx_id).values(
                status="settled",
                nomba_reference=nomba_reference,
                settled_at=datetime.now(timezone.utc),
            )
        )

    async def count_by_payer_in_window(
        self,
        payer_user_id: uuid.UUID,
        hours: int = 1,
    ) -> int:
        """Count transactions by payer in time window (for velocity checks)."""
        window_start = datetime.now(timezone.utc).replace(
            hour=datetime.now(timezone.utc).hour - hours // 24 if hours > 24 else 0
        ) if hours > 24 else datetime.now(timezone.utc)

        if hours > 24:
            window_start = datetime.now(timezone.utc)
        else:
            window_start = datetime.now(timezone.utc)

        result = await self.db.execute(
            select(func.count()).select_from(Transaction).where(
                Transaction.payer_user_id == payer_user_id,
                Transaction.created_at >= window_start,
            )
        )
        return result.scalar() or 0

    async def get_pending_settlements(self, limit: int = 100) -> list[Transaction]:
        """Get transactions pending settlement."""
        result = await self.db.execute(
            select(Transaction).where(
                Transaction.status == "verified",
            ).order_by(Transaction.created_at.asc()).limit(limit)
        )
        return list(result.scalars().all())


class TransactionEventRepository:
    """Repository for TransactionEvent model - database queries only."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, event: TransactionEvent) -> TransactionEvent:
        """Create a new transaction event."""
        self.db.add(event)
        await self.db.flush()
        return event

    async def get_by_tx_id(self, tx_id: str) -> list[TransactionEvent]:
        """Get all events for a transaction."""
        result = await self.db.execute(
            select(TransactionEvent).where(
                TransactionEvent.tx_id == tx_id
            ).order_by(TransactionEvent.created_at.asc())
        )
        return list(result.scalars().all())
