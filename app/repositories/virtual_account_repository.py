"""Virtual account repository - database queries only."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.virtual_account import VirtualAccount


class VirtualAccountRepository:
    """Repository for VirtualAccount model - database queries only."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, account: VirtualAccount) -> VirtualAccount:
        """Create a new virtual account."""
        self.db.add(account)
        await self.db.flush()
        return account

    async def get_by_id(self, account_id: uuid.UUID) -> VirtualAccount | None:
        """Get virtual account by ID."""
        result = await self.db.execute(
            select(VirtualAccount).where(VirtualAccount.id == account_id)
        )
        return result.scalar_one_or_none()

    async def get_by_nomba_account_id(self, nomba_account_id: str) -> VirtualAccount | None:
        """Get virtual account by Nomba account ID."""
        result = await self.db.execute(
            select(VirtualAccount).where(
                VirtualAccount.nomba_account_id == nomba_account_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_account_ref(self, account_ref: str) -> VirtualAccount | None:
        """Get virtual account by account reference."""
        result = await self.db.execute(
            select(VirtualAccount).where(VirtualAccount.account_ref == account_ref)
        )
        return result.scalar_one_or_none()

    async def get_by_nuban(self, nuban: str) -> VirtualAccount | None:
        """Get virtual account by NUBAN."""
        result = await self.db.execute(
            select(VirtualAccount).where(VirtualAccount.nuban == nuban)
        )
        return result.scalar_one_or_none()

    async def get_active_by_user(self, user_id: uuid.UUID) -> list[VirtualAccount]:
        """Get all active virtual accounts for a user."""
        result = await self.db.execute(
            select(VirtualAccount).where(
                VirtualAccount.user_id == user_id,
                VirtualAccount.status == "active",
            ).order_by(VirtualAccount.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_status(self, account_id: uuid.UUID, status: str) -> None:
        """Update virtual account status."""
        await self.db.execute(
            update(VirtualAccount).where(
                VirtualAccount.id == account_id
            ).values(status=status, updated_at=datetime.now(timezone.utc))
        )

    async def mark_funded(
        self,
        account_id: uuid.UUID,
        received_amount: int,
        status: str = "funded",
    ) -> None:
        """Mark virtual account as funded."""
        await self.db.execute(
            update(VirtualAccount).where(
                VirtualAccount.id == account_id
            ).values(
                received_amount_kobo=received_amount,
                status=status,
                updated_at=datetime.now(timezone.utc),
            )
        )

    async def expire_accounts(self) -> int:
        """Mark expired accounts. Returns count updated."""
        result = await self.db.execute(
            update(VirtualAccount).where(
                VirtualAccount.status == "pending",
                VirtualAccount.expires_at < datetime.now(timezone.utc),
            ).values(status="expired")
        )
        return result.rowcount
