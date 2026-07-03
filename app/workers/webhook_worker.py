"""Webhook processing Celery worker."""
from __future__ import annotations

import structlog

from app.core.database import get_session_context
from app.core.logging import get_logger
from app.models.webhook import WebhookEvent
from app.repositories.webhook_repository import WebhookRepository
from app.services.webhook_service import WebhookService
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(
    name="app.workers.webhook_worker.process_webhook_event",
    bind=True,
    max_retries=5,
    default_retry_delay=30,
)
def process_webhook_event(self, event_id: str) -> dict:
    """
    Process a single webhook event.

    Called after webhook handler returns 200.
    """
    import asyncio

    async def _process():
        async with get_session_context() as db:
            webhook_repo = WebhookRepository(db)
            event = await webhook_repo.get_by_id(event_id)

            if not event:
                logger.warning("webhook_event_not_found", event_id=event_id)
                return {"status": "not_found"}

            if event.processed:
                logger.info("webhook_already_processed", event_id=event_id)
                return {"status": "already_processed"}

            service = WebhookService(db)
            await service.process_event(event)

            return {"status": "processed"}

    try:
        return asyncio.run(_process())
    except Exception as e:
        logger.error("webhook_processing_failed", event_id=event_id, error=str(e))
        raise self.retry(exc=e)


@celery_app.task(
    name="app.workers.webhook_worker.process_pending_webhooks",
    bind=True,
)
def process_pending_webhooks(self) -> int:
    """
    Process any unprocessed webhook events.

    Used for recovery if webhook processing was interrupted.
    """
    import asyncio

    async def _process_pending():
        async with get_session_context() as db:
            webhook_repo = WebhookRepository(db)
            service = WebhookService(db)

            events = await webhook_repo.get_unprocessed(limit=100)

            logger.info("processing_pending_webhooks", count=len(events))

            processed_count = 0
            for event in events:
                try:
                    await service.process_event(event)
                    processed_count += 1
                except Exception as e:
                    logger.error(
                        "pending_webhook_failed",
                        event_id=str(event.id),
                        error=str(e),
                    )

            return processed_count

    return asyncio.run(_process_pending())


@celery_app.task(
    name="app.workers.webhook_worker.process_wallet_funding",
    bind=True,
)
def process_wallet_funding(
    self,
    nomba_account_id: str,
    amount_kobo: int,
    transaction_reference: str,
) -> dict:
    """Process wallet funding from virtual account."""
    import asyncio

    async def _process():
        async with get_session_context() as db:
            from app.services.wallet_service import WalletService
            service = WalletService(db)
            return await service.process_funding(
                nomba_account_id=nomba_account_id,
                amount_received_kobo=amount_kobo,
                transaction_reference=transaction_reference,
            )

    try:
        return asyncio.run(_process())
    except Exception as e:
        logger.error("wallet_funding_failed", error=str(e))
        raise self.retry(exc=e)
