"""Offline token repository - database queries only."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.token import OfflineToken


class TokenRepository:
    """Repository for OfflineToken model - database queries only."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, token: OfflineToken) -> OfflineToken:
        """Create a new offline token."""
        self.db.add(token)
        await self.db.flush()
        return token

    async def get_by_id(self, token_id: uuid.UUID) -> OfflineToken | None:
        """Get token by internal ID."""
        result = await self.db.execute(
            select(OfflineToken).where(OfflineToken.id == token_id)
        )
        return result.scalar_one_or_none()

    async def get_by_token_id(self, token_id: str) -> OfflineToken | None:
        """Get token by public token_id."""
        result = await self.db.execute(
            select(OfflineToken).where(OfflineToken.token_id == token_id)
        )
        return result.scalar_one_or_none()

    async def get_active_by_user(self, user_id: uuid.UUID) -> list[OfflineToken]:
        """Get all active tokens for a user."""
        result = await self.db.execute(
            select(OfflineToken).where(
                OfflineToken.user_id == user_id,
                OfflineToken.status == "active",
                OfflineToken.expires_at > datetime.now(timezone.utc),
            ).order_by(OfflineToken.expires_at.asc())
        )
        return list(result.scalars().all())

    async def get_by_user(self, user_id: uuid.UUID) -> list[OfflineToken]:
        """Get all tokens for a user (including inactive)."""
        result = await self.db.execute(
            select(OfflineToken).where(
                OfflineToken.user_id == user_id
            ).order_by(OfflineToken.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_device(self, device_id: uuid.UUID) -> list[OfflineToken]:
        """Get all tokens for a device."""
        result = await self.db.execute(
            select(OfflineToken).where(
                OfflineToken.device_id == device_id
            ).order_by(OfflineToken.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_status(self, token_id: str, status: str) -> None:
        """Update token status."""
        await self.db.execute(
            update(OfflineToken).where(OfflineToken.token_id == token_id).values(status=status)
        )

    async def increment_usage(self, token_id: str, amount: int) -> OfflineToken | None:
        """Increment token usage amount."""
        token = await self.get_by_token_id(token_id)
        if token:
            token.amount_used_kobo += amount
            await self.db.flush()
        return token

    async def revoke(self, token_id: str, reason: str) -> None:
        """Revoke a token."""
        await self.db.execute(
            update(OfflineToken).where(OfflineToken.token_id == token_id).values(
                status="revoked",
                revoked_at=datetime.now(timezone.utc),
                revoked_reason=reason,
            )
        )

    async def expire_tokens(self) -> int:
        """Mark all expired tokens. Returns count of updated tokens."""
        result = await self.db.execute(
            update(OfflineToken).where(
                OfflineToken.status == "active",
                OfflineToken.expires_at < datetime.now(timezone.utc),
            ).values(status="expired")
        )
        return result.rowcount

    async def mark_exhausted(self, token_id: str) -> None:
        """Mark token as exhausted when limit reached."""
        await self.db.execute(
            update(OfflineToken).where(OfflineToken.token_id == token_id).values(
                status="exhausted"
            )
        )
