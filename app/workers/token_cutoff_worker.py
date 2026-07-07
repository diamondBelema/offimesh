"""Token cutoff worker for locking spending on tokens past their cutoff time."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import get_session_context
from app.core.logging import get_logger
from app.models.audit import AuditLog
from app.models.offline_token import OfflineToken
from app.repositories.audit_repository import AuditRepository
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(
    name="app.workers.token_cutoff_worker.apply_spend_cutoffs",
    bind=True,
)
def apply_spend_cutoffs(self) -> dict:
    """
    Apply spend lock to tokens past their customer_spend_cutoff.

    This is the first clock of the two-clock TTL system:
    - customer_spend_cutoff (issued_at + 48h): Customer can no longer spend
    - expires_at (issued_at + 72h): Token dies, unused balance refunded

    Runs every 15 minutes via Celery Beat.
    """
    import asyncio

    async def _apply_cutoff():
        async with get_session_context() as db:
            now = datetime.now(timezone.utc)

            # Find tokens past cutoff that are still active
            result = await db.execute(
                select(OfflineToken).where(
                    OfflineToken.customer_spend_cutoff < now,
                    OfflineToken.status == "active",
                )
            )
            tokens_to_lock = result.scalars().all()

            logger.info("applying_spend_cutoffs", count=len(tokens_to_lock))

            processed = 0
            audit_repo = AuditRepository(db)

            for token in tokens_to_lock:
                try:
                    # Flip to spend_locked status
                    token.status = "spend_locked"
                    processed += 1

                    # Audit log
                    await audit_repo.create(AuditLog(
                        actor_type="system",
                        actor_id="token_cutoff_worker",
                        action="offline_token.spend_locked",
                        resource="offline_token",
                        resource_id=str(token.id),
                        metadata={
                            "cutoff_time": token.customer_spend_cutoff.isoformat(),
                            "remaining_amount_kobo": token.amount_kobo - (token.amount_used_kobo or 0),
                        },
                    ))

                except Exception as e:
                    logger.error(
                        "spend_cutoff_failed",
                        token_id=str(token.id),
                        error=str(e),
                    )

            await db.commit()

            return {
                "processed": processed,
                "tokens_locked": processed,
            }

    return asyncio.run(_apply_cutoff())


@celery_app.task(
    name="app.workers.token_cutoff_worker.get_spend_locked_tokens",
    bind=True,
)
def get_spend_locked_tokens(self, user_id: str | None = None) -> list[dict]:
    """
    Get all tokens that are currently spend-locked.

    Useful for dashboard display and monitoring.
    """
    import asyncio
    from uuid import UUID

    async def _get():
        async with get_session_context() as db:
            query = select(OfflineToken).where(OfflineToken.status == "spend_locked")

            if user_id:
                query = query.where(OfflineToken.user_id == UUID(user_id))

            result = await db.execute(query)
            tokens = result.scalars().all()

            return [
                {
                    "token_id": str(t.id),
                    "user_id": str(t.user_id),
                    "serial": t.serial,
                    "original_amount_kobo": t.amount_kobo,
                    "used_amount_kobo": t.amount_used_kobo or 0,
                    "remaining_kobo": t.amount_kobo - (t.amount_used_kobo or 0),
                    "expires_at": t.expires_at.isoformat(),
                    "time_until_expiry_seconds": (t.expires_at - datetime.now(timezone.utc)).total_seconds(),
                }
                for t in tokens
            ]

    return asyncio.run(_get())


@celery_app.task(
    name="app.workers.token_cutoff_worker.get_cutoff_warning_tokens",
    bind=True,
)
def get_cutoff_warning_tokens(self, hours_threshold: int = 4) -> list[dict]:
    """
    Get tokens approaching their spend cutoff (for notifications).

    Returns tokens within hours_threshold of their cutoff.
    """
    import asyncio
    from datetime import timedelta

    async def _get():
        async with get_session_context() as db:
            now = datetime.now(timezone.utc)
            threshold = now + timedelta(hours=hours_threshold)

            result = await db.execute(
                select(OfflineToken).where(
                    OfflineToken.status == "active",
                    OfflineToken.customer_spend_cutoff > now,
                    OfflineToken.customer_spend_cutoff < threshold,
                )
            )
            tokens = result.scalars().all()

            return [
                {
                    "token_id": str(t.id),
                    "user_id": str(t.user_id),
                    "serial": t.serial,
                    "remaining_kobo": t.amount_kobo - (t.amount_used_kobo or 0),
                    "cutoff_at": t.customer_spend_cutoff.isoformat(),
                    "minutes_until_cutoff": (t.customer_spend_cutoff - now).total_seconds() / 60,
                }
                for t in tokens
            ]

    return asyncio.run(_get())
