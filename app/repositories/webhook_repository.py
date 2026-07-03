"""Webhook event repository - database queries only."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook import WebhookEvent


class WebhookRepository:
    """Repository for WebhookEvent model - database queries only."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, event: WebhookEvent) -> WebhookEvent:
        """Create a new webhook event."""
        self.db.add(event)
        await self.db.flush()
        return event

    async def get_by_id(self, event_id: uuid.UUID) -> WebhookEvent | None:
        """Get webhook event by ID."""
        result = await self.db.execute(
            select(WebhookEvent).where(WebhookEvent.id == event_id)
        )
        return result.scalar_one_or_none()

    async def get_by_request_id(self, request_id: str) -> WebhookEvent | None:
        """Get webhook event by request_id (idempotency key)."""
        result = await self.db.execute(
            select(WebhookEvent).where(WebhookEvent.request_id == request_id)
        )
        return result.scalar_one_or_none()

    async def exists_by_request_id(self, request_id: str) -> bool:
        """Check if webhook event exists by request_id."""
        result = await self.db.execute(
            select(WebhookEvent).where(WebhookEvent.request_id == request_id)
        )
        return result.scalar_one_or_none() is not None

    async def mark_processed(self, event_id: uuid.UUID) -> None:
        """Mark webhook event as processed."""
        from sqlalchemy import update
        await self.db.execute(
            update(WebhookEvent).where(WebhookEvent.id == event_id).values(
                processed=True,
                processed_at=datetime.now(timezone.utc),
            )
        )

    async def mark_failed(self, event_id: uuid.UUID, error: str) -> None:
        """Mark webhook event as failed with error."""
        from sqlalchemy import update
        await self.db.execute(
            update(WebhookEvent).where(WebhookEvent.id == event_id).values(
                processed=True,
                processed_at=datetime.now(timezone.utc),
                processing_error=error,
            )
        )

    async def get_unprocessed(self, limit: int = 100) -> list[WebhookEvent]:
        """Get unprocessed webhook events."""
        result = await self.db.execute(
            select(WebhookEvent).where(
                WebhookEvent.processed == False,
                WebhookEvent.signature_valid == True,
            ).order_by(WebhookEvent.created_at.asc()).limit(limit)
        )
        return list(result.scalars().all())

    async def list_events(
        self,
        page: int = 1,
        page_size: int = 20,
        event_type: str | None = None,
    ) -> tuple[list[WebhookEvent], int]:
        """List webhook events with pagination."""
        query = select(WebhookEvent)
        count_query = select(WebhookEvent)

        if event_type:
            query = query.where(WebhookEvent.event_type == event_type)
            count_query = count_query.where(WebhookEvent.event_type == event_type)

        # Get total count
        count_result = await self.db.execute(count_query)
        total = len(count_result.scalars().all())

        # Get paginated results
        query = query.order_by(WebhookEvent.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        events = list(result.scalars().all())

        return events, total
