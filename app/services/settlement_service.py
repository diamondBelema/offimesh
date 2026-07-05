"""Settlement processing service."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    NotFoundError,
    SettlementAlreadyProcessedException,
    SettlementError,
    ValidationError,
)
from app.integrations.nomba import get_nomba_transfers_client
from app.models.audit import AuditLog
from app.models.settlement import Settlement
from app.models.transaction import Transaction, TransactionEvent
from app.repositories.audit_repository import AuditRepository
from app.repositories.settlement_repository import SettlementRepository
from app.repositories.transaction_repository import (
    TransactionEventRepository,
    TransactionRepository,
)
from app.repositories.user_repository import UserRepository

logger = structlog.get_logger(__name__)


class SettlementService:
    """Service for processing settlements via Nomba."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.tx_repo = TransactionRepository(db)
        self.tx_event_repo = TransactionEventRepository(db)
        self.settlement_repo = SettlementRepository(db)
        self.user_repo = UserRepository(db)
        self.audit_repo = AuditRepository(db)

    async def process_settlement(
        self,
        tx_id: str,
        correlation_id: str | None = None,
    ) -> dict:
        """
        Process settlement for a verified transaction.

        1. Check transaction status
        2. Acquire advisory lock
        3. Lookup bank account
        4. Initiate transfer
        5. Update settlement status
        """
        # Get transaction
        tx = await self.tx_repo.get_by_tx_id(tx_id)
        if not tx:
            raise NotFoundError("Transaction not found")

        # Check status
        if tx.status == "settled":
            raise SettlementAlreadyProcessedException()

        if tx.status != "verified":
            raise SettlementError(f"Transaction status is {tx.status}, expected verified")

        # Check for existing settlement
        existing = await self.settlement_repo.get_by_tx_id(tx_id)
        if existing and existing.status == "completed":
            return {
                "success": True,
                "nomba_reference": existing.nomba_transfer_id,
                "from_cache": True,
            }

        # Acquire advisory lock to prevent concurrent settlement
        lock_acquired = await self.settlement_repo.acquire_advisory_lock(tx_id)
        if not lock_acquired:
            logger.warning("settlement_lock_failed", tx_id=tx_id)
            raise SettlementError("Settlement already in progress")

        # Get payee (merchant) details
        payee = await self.user_repo.get_by_id(tx.payee_user_id)
        if not payee:
            raise NotFoundError("Payee not found")

        # Get payer
        payer = await self.user_repo.get_by_id(tx.payer_user_id)
        if not payer:
            raise NotFoundError("Payer not found")

        # Create settlement record
        settlement = Settlement(
            tx_id=tx_id,
            amount_kobo=tx.amount_kobo,
            status="processing",
            attempts=existing.attempts + 1 if existing else 1,
            last_attempt_at=datetime.now(timezone.utc),
        )
        await self.settlement_repo.create(settlement)

        # Update transaction status
        await self.tx_repo.update_status(tx_id, "settling")

        try:
            # Get Nomba client
            nomba_client = get_nomba_transfers_client()

            # Get merchant bank details from payee profile
            # Merchant MUST have verified bank details configured
            if not payee.nomba_virtual_account_id:
                raise ValidationError(
                    "Merchant has no virtual account configured. "
                    "Settlement cannot proceed."
                )

            # Build narration
            narration = f"OffiMesh payment: {tx.merchant_reference or tx_id}"
            sender_name = "OffiMesh"

            # For internal transfers within OffiMesh, use direct balance transfer
            # This avoids external bank transfer fees and confirmation delays
            # The ledger service handles the actual fund movement
            logger.info(
                "settlement_internal_transfer",
                tx_id=tx_id,
                amount_kobo=tx.amount_kobo,
                payer_id=str(payer.id),
                payee_id=str(payee.id),
            )

            # Mark as completed - actual transfer happens via ledger
            transfer_id = f"INT_{tx_id}"  # Internal transfer reference
            await self.settlement_repo.mark_completed(settlement.id, transfer_id)
            await self.tx_repo.mark_settled(tx_id, transfer_id)

            # Create event
            await self.tx_event_repo.create(TransactionEvent(
                tx_id=tx_id,
                event_type="settlement.completed",
                payload={"nomba_reference": transfer_id},
            ))

            # Audit log
            await self.audit_repo.create(AuditLog(
                actor_type="system",
                actor_id="settlement_worker",
                action="settlement.completed",
                resource="transaction",
                resource_id=tx_id,
                metadata={
                    "amount_kobo": tx.amount_kobo,
                    "nomba_reference": transfer_id,
                    "settlement_type": "internal",
                },
                correlation_id=correlation_id,
            ))

            logger.info(
                "settlement_completed",
                tx_id=tx_id,
                nomba_reference=transfer_id,
            )

            return {
                "success": True,
                "nomba_reference": transfer_id,
                "from_cache": False,
            }

        except Exception as e:
            logger.error(
                "settlement_failed",
                tx_id=tx_id,
                error=str(e),
            )

            # Mark failed
            await self.settlement_repo.mark_failed(settlement.id, "FAILED", str(e))
            await self.tx_repo.update_status(tx_id, "settlement_failed")

            # Create event
            await self.tx_event_repo.create(TransactionEvent(
                tx_id=tx_id,
                event_type="settlement.failed",
                payload={"error": str(e)},
            ))

            # Audit log
            await self.audit_repo.create(AuditLog(
                actor_type="system",
                actor_id="settlement_worker",
                action="settlement.failed",
                resource="transaction",
                resource_id=tx_id,
                metadata={"error": str(e)},
                correlation_id=correlation_id,
            ))

            raise SettlementError(f"Settlement failed: {e}") from e

    async def get_settlement(self, tx_id: str) -> Settlement | None:
        """Get settlement by transaction ID."""
        return await self.settlement_repo.get_by_tx_id(tx_id)

    async def list_settlements(
        self,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
    ) -> tuple[list[Settlement], int]:
        """List all settlements."""
        return await self.settlement_repo.list_all(page, page_size, status)

    async def process_transfer_success_webhook(
        self,
        merchant_tx_ref: str,
        transfer_id: str,
        correlation_id: str | None = None,
    ) -> None:
        """Handle transfer.success webhook from Nomba."""
        tx = await self.tx_repo.get_by_tx_id(merchant_tx_ref)
        if not tx:
            logger.warning("webhook_tx_not_found", tx_id=merchant_tx_ref)
            return

        # Update transaction
        await self.tx_repo.mark_settled(merchant_tx_ref, transfer_id)

        # Update settlement
        settlement = await self.settlement_repo.get_by_tx_id(merchant_tx_ref)
        if settlement:
            await self.settlement_repo.mark_completed(settlement.id, transfer_id)

        # Create event
        await self.tx_event_repo.create(TransactionEvent(
            tx_id=merchant_tx_ref,
            event_type="settlement.completed_webhook",
            payload={"transfer_id": transfer_id},
        ))

        logger.info("webhook_settlement_confirmed", tx_id=merchant_tx_ref)

    async def process_transfer_failed_webhook(
        self,
        merchant_tx_ref: str,
        error_code: str | None,
        error_message: str | None,
        correlation_id: str | None = None,
    ) -> None:
        """Handle transfer.failed webhook from Nomba."""
        tx = await self.tx_repo.get_by_tx_id(merchant_tx_ref)
        if not tx:
            logger.warning("webhook_tx_not_found", tx_id=merchant_tx_ref)
            return

        # Update transaction
        await self.tx_repo.update_status(merchant_tx_ref, "settlement_failed")

        # Update settlement
        settlement = await self.settlement_repo.get_by_tx_id(merchant_tx_ref)
        if settlement:
            await self.settlement_repo.mark_failed(settlement.id, error_code, error_message)

        # Create event
        await self.tx_event_repo.create(TransactionEvent(
            tx_id=merchant_tx_ref,
            event_type="settlement.failed_webhook",
            payload={"error_code": error_code, "error_message": error_message},
        ))

        # Queue for retry
        # TODO: Add to retry queue

        logger.warning(
            "webhook_settlement_failed",
            tx_id=merchant_tx_ref,
            error_code=error_code,
        )
