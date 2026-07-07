from __future__ import annotations

import base64
import hashlib
import hmac
import json

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import WebhookDuplicateError, WebhookSignatureError
from app.core.security import constant_time_compare
from app.models.audit import AuditLog
from app.models.webhook import WebhookEvent
from app.repositories.audit_repository import AuditRepository
from app.repositories.webhook_repository import WebhookRepository
from app.services.settlement_service import SettlementService
from app.services.wallet_service import WalletService

logger = structlog.get_logger(__name__)

# Nomba's documented event types (data.event_type). These are the ONLY
# values that will ever actually appear -- the old code checked for
# "virtual_account.funded" / "transfer.success" / "transfer.failed",
# none of which exist, so no event ever matched.
EVENT_PAYMENT_SUCCESS = "payment_success"
EVENT_PAYOUT_SUCCESS = "payout_success"
EVENT_PAYMENT_FAILED = "payment_failed"
EVENT_PAYMENT_REVERSAL = "payment_reversal"
EVENT_PAYOUT_FAILED = "payout_failed"
EVENT_PAYOUT_REFUND = "payout_refund"


class WebhookService:
    """Service for processing Nomba webhooks."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.webhook_repo = WebhookRepository(db)
        self.audit_repo = AuditRepository(db)
        self.wallet_service = WalletService(db)
        self.settlement_service = SettlementService(db)

    def _build_signing_string(self, body: dict, timestamp: str) -> str:
        """
        Build the exact string Nomba signs, per their documented scheme.

        Format: event_type:requestId:userId:walletId:transactionId:type:time:responseCode:timestamp

        This is NOT a hash of the raw body -- it's a colon-joined string
        of specific fields pulled from the PARSED payload, plus the
        nomba-timestamp header value appended at the end.
        """
        data = body.get("data", {})
        merchant = data.get("merchant", {}) or {}
        transaction = data.get("transaction", {}) or {}

        event_type = body.get("event_type", "")
        request_id = body.get("requestId", "")
        user_id = merchant.get("userId", "")
        wallet_id = merchant.get("walletId", "")
        transaction_id = transaction.get("transactionId", "")
        transaction_type = transaction.get("type", "")
        time_ = transaction.get("time", "")
        response_code = transaction.get("responseCode", "")

        # Nomba's own sample code normalizes the literal string "null" to "".
        if response_code == "null" or response_code is None:
            response_code = ""

        return (
            f"{event_type}:{request_id}:{user_id}:{wallet_id}:"
            f"{transaction_id}:{transaction_type}:{time_}:{response_code}:{timestamp}"
        )

    def verify_signature(self, body: dict, signature: str, timestamp: str) -> bool:
        """
        Verify webhook signature using HMAC-SHA256 + base64, over the
        field-concatenation string Nomba actually signs -- NOT a hash
        of the raw request body.

        Uses constant-time comparison to prevent timing attacks. Nomba's
        own reference implementations compare case-insensitively, so we
        lowercase both sides before the constant-time compare to match
        their behavior exactly (both sides are still fixed-length
        base64 strings, so this doesn't introduce a length side-channel).
        """
        if not settings.nomba_webhook_secret:
            logger.error("webhook_secret_not_configured")
            return False

        signing_string = self._build_signing_string(body, timestamp)

        digest = hmac.new(
            settings.nomba_webhook_secret.encode(),
            signing_string.encode(),
            hashlib.sha256,
        ).digest()
        expected = base64.b64encode(digest).decode()

        return constant_time_compare(expected.lower(), (signature or "").lower())

    async def handle_webhook(
        self,
        raw_body: bytes,
        signature: str,
        timestamp: str = "",
        correlation_id: str | None = None,
    ) -> WebhookEvent:
        """
        Handle incoming Nomba webhook.

        1. Parse body (required first -- Nomba's signature is computed
           over parsed fields, not raw bytes, so we can't verify before
           parsing).
        2. Verify signature using the parsed fields + timestamp header.
        3. Check requestId for idempotency -- raises WebhookDuplicateError
           if already seen, so the router can ack without reprocessing.
        4. Store event.
        """
        # Parse body first -- required to build the signing string.
        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError as e:
            logger.error("webhook_parse_error", error=str(e))
            raise ValueError("Invalid JSON body") from e

        # Verify signature using parsed fields + timestamp header.
        if not self.verify_signature(body, signature, timestamp):
            logger.warning("webhook_signature_invalid")
            raise WebhookSignatureError()

        # Real field name is "event_type", not "event".
        request_id = body.get("requestId") or body.get("request_id", "")
        event_type = body.get("event_type", "")
        data = body.get("data", {})

        if not request_id:
            raise ValueError("Missing requestId")

        # Check for duplicate -- raise so the router can distinguish
        # "already handled, just ack" from a fresh event.
        existing = await self.webhook_repo.get_by_request_id(request_id)
        if existing:
            logger.info("webhook_duplicate", request_id=request_id)
            raise WebhookDuplicateError(request_id=request_id)

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

        Dispatches on Nomba's real event_type values. For
        payment_success specifically, transaction.aliasAccountType
        distinguishes a virtual-account funding event ("VIRTUAL") from
        other payment types (POS/card/etc.) that also fire
        payment_success but aren't wallet top-ups.
        """
        try:
            data = event.payload or {}
            transaction = data.get("transaction", {}) or {}

            if event.event_type == EVENT_PAYMENT_SUCCESS:
                if transaction.get("aliasAccountType") == "VIRTUAL":
                    await self._handle_virtual_account_funded(event)
                else:
                    logger.info(
                        "payment_success_non_virtual_ignored",
                        event_id=str(event.id),
                        transaction_type=transaction.get("type"),
                    )
            elif event.event_type == EVENT_PAYOUT_SUCCESS:
                await self._handle_transfer_success(event)
            elif event.event_type in (EVENT_PAYMENT_FAILED, EVENT_PAYOUT_FAILED):
                await self._handle_transfer_failed(event)
            elif event.event_type in (EVENT_PAYMENT_REVERSAL, EVENT_PAYOUT_REFUND):
                # Not previously handled at all. At minimum, log loudly
                # so a reversed/refunded transaction doesn't vanish
                # silently -- wire this to settlement_service once its
                # refund-handling method is confirmed.
                logger.warning(
                    "webhook_reversal_or_refund_needs_handling",
                    event_id=str(event.id),
                    event_type=event.event_type,
                    transaction_id=transaction.get("transactionId"),
                )
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
        """
        Handle a payment_success event where aliasAccountType == "VIRTUAL"
        -- i.e. a customer funded one of our virtual accounts (NUBAN).

        Real payload shape (data.transaction / data.merchant), not the
        flat accountId/accountRef/amountReceived keys the previous
        version assumed:

          data.merchant.userId, data.merchant.walletId
          data.transaction.aliasAccountReference  -- THIS is our accountRef,
              the correlation key per hackathon org guidance
          data.transaction.transactionAmount      -- in NAIRA, not kobo
          data.transaction.transactionId
        """
        data = event.payload
        merchant = data.get("merchant", {}) or {}
        transaction = data.get("transaction", {}) or {}

        account_ref = transaction.get("aliasAccountReference")
        amount_naira = transaction.get("transactionAmount")
        transaction_id = transaction.get("transactionId")

        if not account_ref or amount_naira is None:
            logger.warning("incomplete_funding_event", data=data)
            return

        amount_received_kobo = int(round(float(amount_naira) * 100))

        # NOTE: renamed from nomba_account_id -> account_ref since the
        # correlation key here is genuinely the accountRef we assigned
        # at virtual account creation, not any Nomba-internal account id.
        # If wallet_service.process_funding's signature still expects
        # nomba_account_id specifically, this call needs to be reconciled
        # against that file -- flagging rather than guessing further.
        result = await self.wallet_service.process_funding(
            account_ref=account_ref,
            amount_received_kobo=amount_received_kobo,
            transaction_reference=transaction_id or "",
            correlation_id=event.request_id,
        )

        logger.info("funding_processed", result=result, account_ref=account_ref)

    async def _handle_transfer_success(self, event: WebhookEvent) -> None:
        """Handle a payout_success event (outbound transfer completed)."""
        data = event.payload
        transaction = data.get("transaction", {}) or {}

        transfer_id = transaction.get("transactionId")
        merchant_tx_ref = transaction.get("merchantTxRef")

        if not merchant_tx_ref:
            logger.warning("missing_merchant_ref", data=data)
            return

        await self.settlement_service.process_transfer_success_webhook(
            merchant_tx_ref=merchant_tx_ref,
            transfer_id=transfer_id or "",
            correlation_id=event.request_id,
        )

    async def _handle_transfer_failed(self, event: WebhookEvent) -> None:
        """Handle a payment_failed / payout_failed event."""
        data = event.payload
        transaction = data.get("transaction", {}) or {}

        transfer_id = transaction.get("transactionId")
        merchant_tx_ref = transaction.get("merchantTxRef")
        # Real field is responseCodeMessage, not errorMessage/errorCode.
        error_message = transaction.get("responseCodeMessage")
        error_code = transaction.get("responseCode")

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
