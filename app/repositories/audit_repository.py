"""Audit log repository - database queries only."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


class AuditRepository:
    """Repository for AuditLog model - database queries only."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, entry: AuditLog) -> AuditLog:
        """Create a new audit log entry."""
        self.db.add(entry)
        await self.db.flush()
        return entry

    async def get_by_id(self, entry_id: uuid.UUID) -> AuditLog | None:
        """Get audit log entry by ID."""
        result = await self.db.execute(
            select(AuditLog).where(AuditLog.id == entry_id)
        )
        return result.scalar_one_or_none()

    async def list_by_actor(
        self,
        actor_id: str,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AuditLog], int]:
        """List audit log entries by actor."""
        query = select(AuditLog).where(AuditLog.actor_id == actor_id)
        count_query = select(AuditLog).where(AuditLog.actor_id == actor_id)

        # Get total count
        count_result = await self.db.execute(count_query)
        total = len(count_result.scalars().all())

        # Get paginated results
        query = query.order_by(AuditLog.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        entries = list(result.scalars().all())

        return entries, total

    async def list_by_resource(
        self,
        resource: str,
        resource_id: str,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AuditLog], int]:
        """List audit log entries by resource."""
        query = select(AuditLog).where(
            AuditLog.resource == resource,
            AuditLog.resource_id == resource_id,
        )
        count_query = select(AuditLog).where(
            AuditLog.resource == resource,
            AuditLog.resource_id == resource_id,
        )

        # Get total count
        count_result = await self.db.execute(count_query)
        total = len(count_result.scalars().all())

        # Get paginated results
        query = query.order_by(AuditLog.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        entries = list(result.scalars().all())

        return entries, total

    async def list_by_correlation_id(
        self,
        correlation_id: str,
    ) -> list[AuditLog]:
        """List all audit entries for a correlation ID (request chain)."""
        result = await self.db.execute(
            select(AuditLog).where(
                AuditLog.correlation_id == correlation_id
            ).order_by(AuditLog.created_at.asc())
        )
        return list(result.scalars().all())
