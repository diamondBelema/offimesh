"""Device repository - database queries only."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device


class DeviceRepository:
    """Repository for Device model - database queries only."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, device: Device) -> Device:
        """Create a new device."""
        self.db.add(device)
        await self.db.flush()
        return device

    async def get_by_id(self, device_id: uuid.UUID) -> Device | None:
        """Get device by ID."""
        result = await self.db.execute(select(Device).where(Device.id == device_id))
        return result.scalar_one_or_none()

    async def get_by_fingerprint(self, fingerprint: str) -> Device | None:
        """Get device by fingerprint."""
        result = await self.db.execute(
            select(Device).where(Device.device_fingerprint == fingerprint)
        )
        return result.scalar_one_or_none()

    async def get_by_user(self, user_id: uuid.UUID) -> list[Device]:
        """Get all devices for a user."""
        result = await self.db.execute(
            select(Device).where(Device.user_id == user_id).order_by(Device.registered_at.desc())
        )
        return list(result.scalars().all())

    async def get_active_by_user(self, user_id: uuid.UUID) -> list[Device]:
        """Get all active (non-revoked) devices for a user."""
        result = await self.db.execute(
            select(Device).where(
                Device.user_id == user_id,
                Device.trust_level != "revoked",
            ).order_by(Device.registered_at.desc())
        )
        return list(result.scalars().all())

    async def update_last_seen(self, device_id: uuid.UUID) -> None:
        """Update device last seen timestamp."""
        await self.db.execute(
            update(Device).where(Device.id == device_id).values(
                last_seen_at=datetime.now(timezone.utc)
            )
        )

    async def revoke(self, device_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Revoke a device."""
        result = await self.db.execute(
            update(Device).where(
                Device.id == device_id,
                Device.user_id == user_id,
            ).values(
                trust_level="revoked",
                revoked_at=datetime.now(timezone.utc),
            )
        )
        return result.rowcount > 0

    async def update_trust_level(self, device_id: uuid.UUID, trust_level: str) -> None:
        """Update device trust level."""
        await self.db.execute(
            update(Device).where(Device.id == device_id).values(trust_level=trust_level)
        )

    async def count_by_user(self, user_id: uuid.UUID) -> int:
        """Count devices for a user."""
        result = await self.db.execute(
            select(Device).where(Device.user_id == user_id)
        )
        return len(result.scalars().all())

    async def count_active_by_user(self, user_id: uuid.UUID) -> int:
        """Count active devices for a user."""
        result = await self.db.execute(
            select(Device).where(
                Device.user_id == user_id,
                Device.trust_level != "revoked",
            )
        )
        return len(result.scalars().all())
