"""Token expiry worker for refunding unused offline token balance."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import get_session_context
from app.core.logging import get_logger
from app.models.audit import AuditLog
from app.models.offline_token import OfflineToken
from app.repositories.audit_repository import AuditRepository
from app.services.ledger_service import LedgerService
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(
    name="app.workers.token_expiry_worker.expire_tokens",
    bind=True,
)
def expire_tokens(self) -> dict:
    """
    Expire tokens past their expires_at timestamp.

    Refunds any unused balance back to user's available balance.
    Runs hourly via Celery Beat.
    """
    import asyncio

    async def _expire():
        async with get_session_context() as db:
            now = datetime.now(timezone.utc)

            # Find expired tokens that haven't been processed
            result = await db.execute(
                select(OfflineToken).where(
                    OfflineToken.expires_at < now,
                    OfflineToken.status.in_(["active", "spend_locked"]),
                )
            )
            expired_tokens = result.scalars().all()

            logger.info("expiring_tokens", count=len(expired_tokens))

            processed = 0
            refunded_total = 0
            audit_repo = AuditRepository(db)
            ledger_service = LedgerService(db)

            for token in expired_tokens:
                try:
                    # Calculate unused amount
                    locked_amount = token.amount_kobo
                    used_amount = token.amount_used_kobo or 0
                    refund_amount = locked_amount - used_amount

                    if refund_amount > 0:
                        # Refund unused balance
                        await ledger_service.unlock_and_refund(
                            user_id=token.user_id,
                            amount_kobo=refund_amount,
                            token_id=str(token.id),
                        )
                        refunded_total += refund_amount

                    # Mark token as expired
                    token.status = "expired"

                    # Audit log
                    await audit_repo.create(AuditLog(
                        actor_type="system",
                        actor_id="token_expiry_worker",
                        action="offline_token.expired",
                        resource="offline_token",
                        resource_id=str(token.id),
                        metadata={
                            "original_amount_kobo": token.amount_kobo,
                            "used_amount_kobo": used_amount,
                            "refunded_kobo": refund_amount,
                        },
                    ))

                    processed += 1

                except Exception as e:
                    logger.error(
                        "token_expiry_failed",
                        token_id=str(token.id),
                        error=str(e),
                    )

            await db.commit()

            return {
                "processed": processed,
                "total_refunded_kobo": refunded_total,
            }

    return asyncio.run(_expire())


@celery_app.task(
    name="app.workers.token_expiry_worker.refund_specific_token",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def refund_specific_token(self, token_id: str) -> dict:
    """
    Refund a specific expired token.

    Used for manual refunds or cleanup.
    """
    import asyncio

    async def _refund():
        async with get_session_context() as db:
            from uuid import UUID

            result = await db.execute(
                select(OfflineToken).where(OfflineToken.id == UUID(token_id))
            )
            token = result.scalar_one_or_none()

            if not token:
                raise ValueError(f"Token {token_id} not found")

            if token.status == "expired":
                logger.info("token_already_expired", token_id=token_id)
                return {"status": "already_expired", "token_id": token_id}

            audit_repo = AuditRepository(db)
            ledger_service = LedgerService(db)

            # Calculate refund
            refund_amount = token.amount_kobo - (token.amount_used_kobo or 0)

            if refund_amount > 0:
                await ledger_service.unlock_and_refund(
                    user_id=token.user_id,
                    amount_kobo=refund_amount,
                    token_id=token_id,
                )

            token.status = "expired"

            await audit_repo.create(AuditLog(
                actor_type="system",
                actor_id="token_expiry_worker",
                action="offline_token.manually_expired",
                resource="offline_token",
                resource_id=token_id,
                metadata={"refunded_kobo": refund_amount},
            ))

            await db.commit()

            return {
                "status": "expired",
                "token_id": token_id,
                "refunded_kobo": refund_amount,
            }

    try:
        return asyncio.run(_refund())
    except Exception as e:
        logger.error("manual_token_refund_failed", token_id=token_id, error=str(e))
        raise self.retry(exc=e)
