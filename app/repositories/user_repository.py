"""User repository - database queries only."""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

if TYPE_CHECKING:
    pass


class UserRepository:
    """Repository for User model - database queries only."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, user: User) -> User:
        """Create a new user."""
        self.db.add(user)
        await self.db.flush()
        return user

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """Get user by ID."""
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_phone_hash(self, phone_hash: str) -> User | None:
        """Get user by phone hash."""
        result = await self.db.execute(select(User).where(User.phone_hash == phone_hash))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """Get user by email."""
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def update(self, user: User) -> User:
        """Update user."""
        await self.db.flush()
        return user

    async def update_status(self, user_id: uuid.UUID, status: str) -> None:
        """Update user status."""
        await self.db.execute(
            update(User).where(User.id == user_id).values(status=status)
        )

    async def update_balance(self, user_id: uuid.UUID, balance_delta: int) -> User | None:
        """Update user balance by delta (can be negative)."""
        user = await self.get_by_id(user_id)
        if user:
            user.balance_kobo += balance_delta
            await self.db.flush()
        return user

    async def set_balance(self, user_id: uuid.UUID, balance: int) -> None:
        """Set user balance to specific value."""
        await self.db.execute(
            update(User).where(User.id == user_id).values(balance_kobo=balance)
        )

    async def set_pin(self, user_id: uuid.UUID, pin_hash: str) -> None:
        """Set user PIN hash."""
        await self.db.execute(
            update(User).where(User.id == user_id).values(pin_hash=pin_hash)
        )

    async def verify_bvn(self, user_id: uuid.UUID, bvn_encrypted: str, reference: str) -> None:
        """Mark BVN as verified."""
        await self.db.execute(
            update(User).where(User.id == user_id).values(
                bvn=bvn_encrypted,
                bvn_verified=True,
                bvn_verification_reference=reference,
                trust_level="elevated",
            )
        )

    async def set_nomba_account(self, user_id: uuid.UUID, nomba_account_id: str) -> None:
        """Set Nomba virtual account ID."""
        await self.db.execute(
            update(User).where(User.id == user_id).values(
                nomba_virtual_account_id=nomba_account_id
            )
        )

    async def update_trust_level(self, user_id: uuid.UUID, trust_level: str) -> None:
        """Update user trust level."""
        await self.db.execute(
            update(User).where(User.id == user_id).values(trust_level=trust_level)
        )

    async def list_users(
        self,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        role: str | None = None,
    ) -> tuple[list[User], int]:
        """List users with pagination and filters."""
        query = select(User)
        count_query = select(User)

        if status:
            query = query.where(User.status == status)
            count_query = count_query.where(User.status == status)
        if role:
            query = query.where(User.role == role)
            count_query = count_query.where(User.role == role)

        # Get total count
        count_result = await self.db.execute(count_query)
        total = len(count_result.scalars().all())

        # Get paginated results
        query = query.order_by(User.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        users = list(result.scalars().all())

        return users, total
