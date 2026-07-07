"""Webhook handling service."""
from __future__ import annotations

import hashlib
import hmac
import json

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import WebhookSignatureError
from app.core.security import constant_time_compare
from app.models.audit import AuditLog
from app.models.webhook import WebhookEvent
from app.repositories.audit_repository import AuditRepository
from app.repositories.webhook_repository import WebhookRepository
from app.services.settlement_service import SettlementService
from app.services.wallet_service import WalletService

logger = structlog.get_logger(__name__)


class WebhookService:
    """Service for processing Nomba webhooks."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.webhook_repo = WebhookRepository(db)
        self.audit_repo = AuditRepository(db)
        self.wallet_service = WalletService(db)
        self.settlement_service = SettlementService(db)

    def verify_signature(self, raw_body: bytes, signature: str) -> bool:
        """
        Verify webhook signature using HMAC-SHA256.

        Uses constant-time comparison to prevent timing attacks.
        """
        expected = hmac.new(
            settings.nomba_webhook_secret.encode(),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        return constant_time_compare(expected, signature)

    async def handle_webhook(
        self,
        raw_body: bytes,
        signature: str,
        correlation_id: str | None = None,
    ) -> WebhookEvent:
        """
        Handle incoming Nomba webhook.

        1. Verify signature
        2. Parse body
        3. Check for duplicate (idempotency)
        4. Store event
        5. Return 200 (actual processing is async)
        """
        # Verify signature
        signature_valid = self.verify_signature(raw_body, signature)
        if not signature_valid:
            logger.warning("webhook_signature_invalid")
            raise WebhookSignatureError()

        # Parse body
        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError as e:
            logger.error("webhook_parse_error", error=str(e))
            raise ValueError("Invalid JSON body")

        # Extract fields
        request_id = body.get("requestId") or body.get("request_id", "")
        event_type = body.get("event", "")
        data = body.get("data", {})

        if not request_id:
            raise ValueError("Missing request_id")

        # Check for duplicate
        existing = await self.webhook_repo.get_by_request_id(request_id)
        if existing:
            logger.info("webhook_duplicate", request_id=request_id)
            return existing

        # Store event
        event = WebhookEvent(
            request_id=request_id,
            event_type=event_type,
            payload=data,
            raw_body=raw_body.decode() if isinstance(raw_body, bytes) else raw_body,
            signature_valid=True,
            processed=False,
        )
        await self.webhook_repo.create(event)

        # Audit log
        await self.audit_repo.create(AuditLog(
            actor_type="system",
            actor_id="nomba",
            action="webhook.received",
            resource="webhook_event",
            resource_id=request_id,
            metadata={"event_type": event_type},
            correlation_id=correlation_id,
        ))

        logger.info(
            "webhook_received",
            request_id=request_id,
            event_type=event_type,
        )

        return event

    async def process_event(self, event: WebhookEvent) -> None:
        """
        Process a webhook event asynchronously.

        Called by Celery worker after handler returns 200.
        """
        try:
            if event.event_type == "virtual_account.funded":
                await self._handle_virtual_account_funded(event)
            elif event.event_type == "transfer.success":
                await self._handle_transfer_success(event)
            elif event.event_type == "transfer.failed":
                await self._handle_transfer_failed(event)
            else:
                logger.info("webhook_event_ignored", event_type=event.event_type)

            await self.webhook_repo.mark_processed(event.id)

        except Exception as e:
            logger.error(
                "webhook_processing_failed",
                event_id=str(event.id),
                error=str(e),
            )
            await self.webhook_repo.mark_failed(event.id, str(e))
            raise

    async def _handle_virtual_account_funded(self, event: WebhookEvent) -> None:
        """Handle wallet funding event."""
        data = event.payload

        account_id = data.get("accountId")
        account_ref = data.get("accountRef")
        amount_received = data.get("amountReceived") or data.get("amount_received")
        tx_ref = data.get("transactionReference") or data.get("transaction_reference")

        if not account_id or amount_received is None:
            logger.warning("incomplete_funding_event", data=data)
            return

        result = await self.wallet_service.process_funding(
            nomba_account_id=account_id,
            amount_received_kobo=amount_received,
            transaction_reference=tx_ref or "",
            correlation_id=event.request_id,
        )

        logger.info("funding_processed", result=result)

    async def _handle_transfer_success(self, event: WebhookEvent) -> None:
        """Handle successful settlement transfer."""
        data = event.payload

        transfer_id = data.get("transferId") or data.get("transfer_id")
        merchant_tx_ref = data.get("merchantTxRef") or data.get("merchant_tx_ref")
        amount = data.get("amount")
        status = data.get("status")
        completed_at = data.get("completedAt") or data.get("completed_at")

        if not merchant_tx_ref:
            logger.warning("missing_merchant_ref", data=data)
            return

        await self.settlement_service.process_transfer_success_webhook(
            merchant_tx_ref=merchant_tx_ref,
            transfer_id=transfer_id or "",
            correlation_id=event.request_id,
        )

    async def _handle_transfer_failed(self, event: WebhookEvent) -> None:
        """Handle failed settlement transfer."""
        data = event.payload

        transfer_id = data.get("transferId") or data.get("transfer_id")
        merchant_tx_ref = data.get("merchantTxRef") or data.get("merchant_tx_ref")
        error_code = data.get("errorCode") or data.get("error_code")
        error_message = data.get("errorMessage") or data.get("error_message")

        if not merchant_tx_ref:
            logger.warning("missing_merchant_ref", data=data)
            return

        await self.settlement_service.process_transfer_failed_webhook(
            merchant_tx_ref=merchant_tx_ref,
            error_code=error_code,
            error_message=error_message,
            correlation_id=event.request_id,
        )

    async def get_unprocessed_events(self, limit: int = 100) -> list[WebhookEvent]:
        """Get unprocessed webhook events for worker."""
        return await self.webhook_repo.get_unprocessed(limit)
