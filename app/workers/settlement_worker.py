"""Settlement processing Celery worker."""
from __future__ import annotations

import structlog

from app.core.database import get_session_context
from app.core.logging import get_logger
from app.repositories.settlement_repository import SettlementRepository
from app.repositories.transaction_repository import TransactionRepository
from app.services.settlement_service import SettlementService
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(
    name="app.workers.settlement_worker.process_settlement",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def process_settlement(self, tx_id: str, correlation_id: str | None = None) -> dict:
    """
    Process settlement for a transaction.

    Used for both initial settlement and retry attempts.
    """
    import asyncio

    async def _process():
        async with get_session_context() as db:
            service = SettlementService(db)
            return await service.process_settlement(tx_id, correlation_id)

    try:
        return asyncio.run(_process())
    except Exception as e:
        logger.error("settlement_task_failed", tx_id=tx_id, error=str(e))
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


@celery_app.task(
    name="app.workers.settlement_worker.retry_failed_settlements",
    bind=True,
)
def retry_failed_settlements(self) -> int:
    """
    Retry failed settlements that haven't exceeded max attempts.

    Runs periodically (every 5 minutes).
    """
    import asyncio

    async def _retry():
        async with get_session_context() as db:
            settlement_repo = SettlementRepository(db)
            tx_repo = TransactionRepository(db)

            # Get failed settlements eligible for retry
            failed_settlements = await settlement_repo.get_pending_retry(max_attempts=3, limit=50)

            logger.info("retrying_failed_settlements", count=len(failed_settlements))

            success_count = 0
            for settlement in failed_settlements:
                try:
                    service = SettlementService(db)
                    result = await service.process_settlement(settlement.tx_id)
                    if result.get("success"):
                        success_count += 1
                except Exception as e:
                    logger.warning(
                        "settlement_retry_failed",
                        tx_id=settlement.tx_id,
                        error=str(e),
                    )

            return success_count

    return asyncio.run(_retry())


@celery_app.task(
    name="app.workers.settlement_worker.process_batch_settlements",
    bind=True,
)
def process_batch_settlements(self, tx_ids: list[str]) -> dict:
    """Process settlements for multiple transactions."""
    import asyncio

    async def _process_batch():
        async with get_session_context() as db:
            service = SettlementService(db)
            results = []

            for tx_id in tx_ids:
                try:
                    result = await service.process_settlement(tx_id)
                    results.append({"tx_id": tx_id, "success": result.get("success", False)})
                except Exception as e:
                    results.append({"tx_id": tx_id, "success": False, "error": str(e)})

            return {
                "total": len(tx_ids),
                "successful": sum(1 for r in results if r.get("success")),
                "results": results,
            }

    return asyncio.run(_process_batch())
