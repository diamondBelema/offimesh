"""Transaction sync and processing service."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    BatchLimitExceededError,
    ConflictError,
    NotFoundError,
    ReplayAttackError,
    SignatureVerificationError,
    ValidationError,
)
from app.core.redis import check_and_store_nonce, get_last_sequence, set_last_sequence

from app.models.audit import AuditLog
from app.models.transaction import Transaction, TransactionEvent
from app.repositories.audit_repository import AuditRepository
from app.repositories.device_repository import DeviceRepository
from app.repositories.token_repository import TokenRepository
from app.repositories.transaction_repository import (
    TransactionEventRepository,
    TransactionRepository,
)
from app.repositories.user_repository import UserRepository

logger = structlog.get_logger(__name__)


class TransactionService:
    """Service for transaction sync and processing."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.tx_repo = TransactionRepository(db)
        self.tx_event_repo = TransactionEventRepository(db)
        self.user_repo = UserRepository(db)
        self.device_repo = DeviceRepository(db)
        self.token_repo = TokenRepository(db)
        self.audit_repo = AuditRepository(db)

    async def sync_batch(
        self,
        batch_id: str,
        device_id: str,
        transactions: list[dict],
        device_signature: str,
        correlation_id: str | None = None,
    ) -> dict:
        """
        Sync a batch of offline transactions.

        Max 100 transactions per batch. Each is processed independently.
        """
        # Check batch size
        if len(transactions) > settings.max_sync_batch_size:
            raise BatchLimitExceededError(
                len(transactions),
                settings.max_sync_batch_size,
            )

        # Verify device
        device = await self.device_repo.get_by_id(uuid.UUID(device_id))
        if not device:
            raise NotFoundError("Device not found")

        # Verify batch signature
        batch_payload = {
            "device_id": device_id,
            "batch_id": batch_id,
            "tx_count": len(transactions),
        }
        # In production, verify signature properly
        # if not verify_payload(batch_payload, device_signature, device.device_public_key):
        #     raise SignatureVerificationError("Invalid batch signature")

        # Process each transaction
        results = []
        for tx_data in transactions:
            result = await self._process_single_transaction(
                tx_data,
                device,
                correlation_id,
            )
            results.append(result)

        accepted = sum(1 for r in results if r["status"] == "accepted")
        rejected = sum(1 for r in results if r["status"] == "rejected")
        duplicates = sum(1 for r in results if r["status"] == "duplicate")

        # Audit log
        await self.audit_repo.create(AuditLog(
            actor_type="device",
            actor_id=device_id,
            action="transaction.batch_synced",
            resource="batch",
            resource_id=batch_id,
            metadata={
                "total": len(transactions),
                "accepted": accepted,
                "rejected": rejected,
                "duplicates": duplicates,
            },
            correlation_id=correlation_id,
        ))

        logger.info(
            "batch_processed",
            batch_id=batch_id,
            accepted=accepted,
            rejected=rejected,
            duplicates=duplicates,
        )

        return {
            "batch_id": batch_id,
            "processed": len(transactions),
            "accepted": accepted,
            "rejected": rejected,
            "results": results,
        }

    async def _process_single_transaction(
        self,
        tx_data: dict,
        device: any,
        correlation_id: str | None,
    ) -> dict:
        """Process a single transaction from a batch."""
        tx_id = tx_data.get("tx_id")

        # Check for duplicate
        if await self.tx_repo.exists_by_tx_id(tx_id):
            return {"tx_id": tx_id, "status": "duplicate", "reason": None}

        # Validate required fields
        required = [
            "tx_id", "token_id", "payer_user_id", "payee_user_id",
            "amount_kobo", "nonce", "sequence_number", "initiated_at",
            "payer_signature", "merchant_signature", "payload_hash",
        ]
        for field in required:
            if not tx_data.get(field):
                return {
                    "tx_id": tx_id,
                    "status": "rejected",
                    "reason": f"MISSING_{field.upper()}",
                }

        # Validate token
        token = await self.token_repo.get_by_token_id(tx_data["token_id"])
        if not token:
            return {"tx_id": tx_id, "status": "rejected", "reason": "TOKEN_NOT_FOUND"}

        if token.status != "active":
            return {"tx_id": tx_id, "status": "rejected", "reason": f"TOKEN_{token.status.upper()}"}

        if token.is_expired:
            return {"tx_id": tx_id, "status": "rejected", "reason": "TOKEN_EXPIRED"}

        # Check spending limit
        remaining = token.amount_kobo - token.amount_used_kobo
        if tx_data["amount_kobo"] > remaining:
            return {"tx_id": tx_id, "status": "rejected", "reason": "INSUFFICIENT_TOKEN_LIMIT"}

        # Validate payer and payee
        payer = await self.user_repo.get_by_id(uuid.UUID(tx_data["payer_user_id"]))
        if not payer:
            return {"tx_id": tx_id, "status": "rejected", "reason": "PAYER_NOT_FOUND"}

        payee = await self.user_repo.get_by_id(uuid.UUID(tx_data["payee_user_id"]))
        if not payee:
            return {"tx_id": tx_id, "status": "rejected", "reason": "PAYEE_NOT_FOUND"}

        # Validate payer device
        payer_device = await self.device_repo.get_by_id(
            uuid.UUID(tx_data.get("payer_device_id", device.id))
        )
        if not payer_device:
            return {"tx_id": tx_id, "status": "rejected", "reason": "PAYER_DEVICE_NOT_FOUND"}

        # Replay protection - check nonce
        if not await check_and_store_nonce(tx_data["nonce"]):
            logger.warning("replay_detected", tx_id=tx_id, nonce=tx_data["nonce"])
            return {"tx_id": tx_id, "status": "rejected", "reason": "REPLAY_DETECTED"}

        # Sequence number validation
        payer_device_id = str(payer_device.id)
        token_id = tx_data["token_id"]
        last_seq = await get_last_sequence(payer_device_id, token_id)
        if last_seq is not None and tx_data["sequence_number"] <= last_seq:
            return {"tx_id": tx_id, "status": "rejected", "reason": "STALE_SEQUENCE"}

        # Verify signatures (simplified for demo)
        # In production, properly verify Ed25519 signatures
        # verify_canonical = self._build_verification_payload(tx_data)
        # payload_hash = sha256(canonicalize(verify_canonical))
        # if payload_hash != tx_data["payload_hash"]:
        #     return {"tx_id": tx_id, "status": "rejected", "reason": "PAYLOAD_HASH_MISMATCH"}

        # All validations passed - create transaction
        try:
            initiated_at = datetime.fromisoformat(tx_data["initiated_at"].replace("Z", "+00:00"))
        except (ValueError, TypeError):
            initiated_at = datetime.now(timezone.utc)

        transaction = Transaction(
            tx_id=tx_id,
            payer_user_id=payer.id,
            payee_user_id=payee.id,
            amount_kobo=tx_data["amount_kobo"],
            currency=tx_data.get("currency", "NGN"),
            offline_token_id=token.id,
            merchant_reference=tx_data.get("merchant_reference"),
            status="verified",
            payer_signature=tx_data["payer_signature"],
            merchant_signature=tx_data["merchant_signature"],
            signed_payload_hash=tx_data["payload_hash"],
            nonce=tx_data["nonce"],
            sequence_number=tx_data["sequence_number"],
            initiated_at=initiated_at,
            synced_at=datetime.now(timezone.utc),
            fraud_score=0,  # TODO: Call fraud service
        )
        await self.tx_repo.create(transaction)

        # Update sequence tracking
        await set_last_sequence(payer_device_id, token_id, tx_data["sequence_number"])

        # Update token usage
        await self.token_repo.increment_usage(tx_data["token_id"], tx_data["amount_kobo"])

        # Create event
        await self.tx_event_repo.create(TransactionEvent(
            tx_id=tx_id,
            event_type="transaction.verified",
            payload={"amount_kobo": tx_data["amount_kobo"]},
        ))

        # Audit log
        await self.audit_repo.create(AuditLog(
            actor_type="user",
            actor_id=str(payer.id),
            action="transaction.created",
            resource="transaction",
            resource_id=tx_id,
            metadata={"amount_kobo": tx_data["amount_kobo"]},
            correlation_id=correlation_id,
        ))

        return {"tx_id": tx_id, "status": "accepted", "reason": None}

    def _build_verification_payload(self, tx_data: dict) -> dict:
        """Build canonical payload for signature verification."""
        return {
            "txId": tx_data["tx_id"],
            "tokenId": tx_data["token_id"],
            "amount": tx_data["amount_kobo"],
            "currency": tx_data.get("currency", "NGN"),
            "payerId": tx_data["payer_user_id"],
            "merchantId": tx_data["payee_user_id"],
            "ref": tx_data.get("merchant_reference", ""),
            "nonce": tx_data["nonce"],
            "seq": tx_data["sequence_number"],
            "ts": tx_data["initiated_at"],
        }

    async def get_transaction(self, tx_id: str) -> Transaction | None:
        """Get transaction by ID."""
        return await self.tx_repo.get_by_tx_id(tx_id)

    async def list_transactions(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
    ) -> tuple[list[Transaction], int]:
        """List transactions for a user."""
        return await self.tx_repo.list_by_user(
            uuid.UUID(user_id),
            page=page,
            page_size=page_size,
            status=status,
        )
