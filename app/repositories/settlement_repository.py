"""Settlement repository - database queries only."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settlement import Settlement


class SettlementRepository:
    """Repository for Settlement model - database queries only."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, settlement: Settlement) -> Settlement:
        """Create a new settlement."""
        self.db.add(settlement)
        await self.db.flush()
        return settlement

    async def get_by_id(self, settlement_id: uuid.UUID) -> Settlement | None:
        """Get settlement by ID."""
        result = await self.db.execute(
            select(Settlement).where(Settlement.id == settlement_id)
        )
        return result.scalar_one_or_none()

    async def get_by_tx_id(self, tx_id: str) -> Settlement | None:
        """Get settlement by transaction ID."""
        result = await self.db.execute(
            select(Settlement).where(Settlement.tx_id == tx_id)
        )
        return result.scalar_one_or_none()

    async def get_by_nomba_transfer_id(self, nomba_transfer_id: str) -> Settlement | None:
        """Get settlement by Nomba transfer ID."""
        result = await self.db.execute(
            select(Settlement).where(Settlement.nomba_transfer_id == nomba_transfer_id)
        )
        return result.scalar_one_or_none()

    async def update_status(self, settlement_id: uuid.UUID, status: str) -> None:
        """Update settlement status."""
        await self.db.execute(
            update(Settlement).where(Settlement.id == settlement_id).values(status=status)
        )

    async def increment_attempts(self, settlement_id: uuid.UUID) -> None:
        """Increment settlement attempt count."""
        await self.db.execute(
            update(Settlement).where(Settlement.id == settlement_id).values(
                attempts=Settlement.attempts + 1,
                last_attempt_at=datetime.now(timezone.utc),
            )
        )

    async def mark_completed(
        self,
        settlement_id: uuid.UUID,
        nomba_transfer_id: str,
    ) -> None:
        """Mark settlement as completed."""
        await self.db.execute(
            update(Settlement).where(Settlement.id == settlement_id).values(
                status="completed",
                nomba_transfer_id=nomba_transfer_id,
                settled_at=datetime.now(timezone.utc),
            )
        )

    async def mark_failed(
        self,
        settlement_id: uuid.UUID,
        error_code: str | None,
        error_message: str | None,
    ) -> None:
        """Mark settlement as failed."""
        await self.db.execute(
            update(Settlement).where(Settlement.id == settlement_id).values(
                status="failed",
                error_code=error_code,
                error_message=error_message,
            )
        )

    async def list_all(
        self,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
    ) -> tuple[list[Settlement], int]:
        """List all settlements with pagination."""
        query = select(Settlement)
        count_query = select(func.count()).select_from(Settlement)

        if status:
            query = query.where(Settlement.status == status)
            count_query = count_query.where(Settlement.status == status)

        # Get total count
        total = (await self.db.execute(count_query)).scalar() or 0

        # Get paginated results
        query = query.order_by(Settlement.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        settlements = list(result.scalars().all())

        return settlements, total

    async def get_pending_retry(self, max_attempts: int = 3, limit: int = 50) -> list[Settlement]:
        """Get failed settlements eligible for retry."""
        result = await self.db.execute(
            select(Settlement).where(
                Settlement.status == "failed",
                Settlement.attempts < max_attempts,
            ).order_by(Settlement.last_attempt_at.asc()).limit(limit)
        )
        return list(result.scalars().all())

    async def acquire_advisory_lock(self, tx_id: str) -> bool:
        """
        Acquire PostgreSQL advisory lock for settlement processing.
        Uses pg_try_advisory_xact_lock for transaction-scoped locking.
        """
        # Generate a stable integer from tx_id hash
        lock_key = abs(hash(tx_id)) % (2**31)

        result = await self.db.execute(
            select(func.pg_try_advisory_xact_lock(lock_key))
        )
        return result.scalar() or False
