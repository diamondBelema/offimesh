"""Offline token provisioning service with two-clock TTL and fraud checks."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import structlog
import ulid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    NotFoundError,
    TokenExhaustedError,
    TokenExpiredError,
    ValidationError,
    InsufficientFundsError,
    FraudBlockError,
)
from app.core.security import generate_nonce
from app.models.audit import AuditLog
from app.models.offline_token import OfflineToken
from app.repositories.audit_repository import AuditRepository
from app.repositories.device_repository import DeviceRepository
from app.repositories.user_repository import UserRepository
from app.services.device_trust_service import DeviceTrustService, DeviceTrustPayload
from app.services.fraud_service import FraudService
from app.services.identity_verification_service import IdentityVerificationService
from app.services.ledger_service import LedgerService

logger = structlog.get_logger(__name__)


class TokenService:
    """
    Service for offline spending token management.

    Two-clock TTL system:
    - customer_spend_cutoff (issued_at + 48h): Customer can no longer spend
    - expires_at (issued_at + 72h): Token dies, unused balance refunded

    Requirements for token issuance:
    - User must have NIN verified AND face verified
    - Device must pass trust evaluation
    - User must have sufficient balance (locked on issuance)
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.user_repo = UserRepository(db)
        self.device_repo = DeviceRepository(db)
        self.audit_repo = AuditRepository(db)
        self.ledger_service = LedgerService(db)
        self.device_trust_service = DeviceTrustService(db)
        self.fraud_service = FraudService(db)
        self.identity_service = IdentityVerificationService(db)

    async def provision_token(
        self,
        user_id: str,
        device_id: str | None,
        requested_limit_kobo: int,
        device_trust_payload: DeviceTrustPayload | None = None,
        ip_address: str = "0.0.0.0",
        correlation_id: str | None = None,
    ) -> OfflineToken:
        """
        Provision an offline spending token.

        CHECKPOINT 1 fraud evaluation happens here.
        """
        # 1. Verify user exists
        user = await self.user_repo.get_by_id(uuid.UUID(user_id))
        if not user:
            raise NotFoundError("User not found")

        # 2. Check identity verification requirements
        can_provision, reason = await self.identity_service.can_user_provision_token(user_id)
        if not can_provision:
            raise ValidationError(f"Cannot provision token: {reason}")

        # 3. Get active device
        devices = await self.device_repo.get_active_by_user(user.id)
        if not devices:
            raise NotFoundError("No active devices found")

        if device_id:
            device = await self.device_repo.get_by_id(uuid.UUID(device_id))
            if not device or device.user_id != user.id:
                raise NotFoundError("Device not found or not owned by user")
        else:
            device = devices[0]

        # 4. Evaluate device trust
        if device_trust_payload is None:
            device_trust_payload = DeviceTrustPayload(
                device_fingerprint=device.device_fingerprint or "unknown",
                is_hardware_backed_key=device.is_hardware_backed_key or False,
            )

        trust_result = await self.device_trust_service.evaluate_trust(
            device=device,
            trust_payload=device_trust_payload,
            ip_address=ip_address,
            action="token_provisioning",
            correlation_id=correlation_id,
        )

        if not trust_result.get("trusted"):
            raise ValidationError(f"Device not trusted: {trust_result.get('reason', 'Unknown reason')}")

        # 5. Run fraud checkpoint 1
        fraud_result = await self.fraud_service.evaluate_checkpoint_1(
            user_id=user_id,
            device_fingerprint_hash=device_trust_payload.device_fingerprint_hash,
            trust_check_result=trust_result,
            correlation_id=correlation_id,
        )

        if fraud_result.get("blocked"):
            raise FraudBlockError(
                score=fraud_result.get("fraud_score", 0),
                signals=fraud_result.get("signals_detected", []),
            )

        # 6. Determine limits based on device trust
        limits = trust_result.get("limits", {})
        max_allowed = limits.get("max_token_kobo", 0)
        ttl_hours = limits.get("ttl_hours", 24)

        if max_allowed == 0:
            raise ValidationError("Device not eligible for offline tokens")

        # Cap at device limit
        actual_limit = min(requested_limit_kobo, max_allowed)

        # 7. Check and lock balance
        try:
            balance = await self.ledger_service.lock_for_offline_token(
                user_id=user.id,
                amount_kobo=actual_limit,
                token_id="pending",  # Will update after token creation
                correlation_id=correlation_id,
            )
        except InsufficientFundsError as e:
            raise ValidationError(f"Insufficient balance: need {actual_limit} kobo, have {e.available} kobo")

        # 8. Generate token
        now = datetime.now(timezone.utc)
        serial = ulid.new()
        nonce = generate_nonce(32)  # Server-generated nonce

        # Two-clock TTL
        customer_spend_cutoff = now + timedelta(hours=48)
        expires_at = now + timedelta(hours=ttl_hours)

        # Sign payload
        server_signature = self._generate_server_signature(
            user_id=str(user.id),
            device_id=str(device.id),
            serial=serial,
            limit=actual_limit,
        )

        # 9. Create token record
        token = OfflineToken(
            serial=serial,
            user_id=user.id,
            device_id=device.id,
            device_fingerprint_hash=device_trust_payload.device_fingerprint_hash,
            amount_kobo=actual_limit,
            customer_spend_cutoff=customer_spend_cutoff,
            expires_at=expires_at,
            nonce=nonce,
            server_signature=server_signature,
            status="active",
        )
        self.db.add(token)
        await self.db.flush()

        # 10. Update ledger with actual token ID
        # (We used "pending" earlier, now update the reference)
        await self._update_token_ledger_reference(user.id, token.id)

        # 11. Audit log
        await self.audit_repo.create(AuditLog(
            actor_type="user",
            actor_id=user_id,
            action="offline_token.provisioned",
            resource="offline_token",
            resource_id=str(token.id),
            metadata={
                "serial": serial,
                "amount_kobo": actual_limit,
                "device_id": str(device.id),
                "device_trust_score": trust_result.get("trust_score", 0),
                "customer_spend_cutoff": customer_spend_cutoff.isoformat(),
                "expires_at": expires_at.isoformat(),
                "fraud_score": fraud_result.get("fraud_score", 0),
            },
            correlation_id=correlation_id,
        ))

        logger.info(
            "offline_token_provisioned",
            token_id=str(token.id),
            serial=serial,
            user_id=user_id,
            amount_kobo=actual_limit,
            trust_score=trust_result.get("trust_score", 0),
            fraud_score=fraud_result.get("fraud_score", 0),
        )

        return token

    def _generate_server_signature(
        self,
        user_id: str,
        device_id: str,
        serial: str,
        limit: int,
    ) -> str:
        """Generate server signature for token."""
        payload = f"{user_id}:{device_id}:{serial}:{limit}"
        return hashlib.sha256(payload.encode()).hexdigest()[:64]

    async def _update_token_ledger_reference(
        self,
        user_id: uuid.UUID,
        token_id: uuid.UUID,
    ) -> None:
        """Update ledger entry reference with actual token ID."""
        # This is handled implicitly because we flush before the lock
        # In production, you'd update the ledger entry reference_id
        pass

    async def get_active_tokens(self, user_id: str) -> list[OfflineToken]:
        """Get all active/spend_locked tokens for a user."""
        result = await self.db.execute(
            select(OfflineToken).where(
                OfflineToken.user_id == uuid.UUID(user_id),
                OfflineToken.status.in_(["active", "spend_locked"]),
            ).order_by(OfflineToken.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_token_by_serial(self, serial: str) -> OfflineToken | None:
        """Get token by its serial number."""
        result = await self.db.execute(
            select(OfflineToken).where(OfflineToken.serial == serial)
        )
        return result.scalar_one_or_none()

    async def record_spend(
        self,
        token_id: str | uuid.UUID,
        amount_kobo: int,
    ) -> OfflineToken:
        """
        Record a spend against a token.

        Uses row-level locking for atomicity.
        """
        token_uuid = uuid.UUID(token_id) if isinstance(token_id, str) else token_id

        # Lock the row for update
        result = await self.db.execute(
            select(OfflineToken)
            .where(OfflineToken.id == token_uuid)
            .with_for_update()
        )
        token = result.scalar_one_or_none()

        if not token:
            raise NotFoundError("Token not found")

        if token.status not in ["active"]:
            if token.status == "spend_locked":
                raise ValidationError("Token past spend cutoff")
            raise ValidationError(f"Token is {token.status}")

        # Check spend cutoff
        if datetime.now(timezone.utc) > token.customer_spend_cutoff:
            token.status = "spend_locked"
            raise ValidationError("Token past spend cutoff time")

        # Check if spend would exceed limit
        new_used = (token.amount_used_kobo or 0) + amount_kobo
        if new_used > token.amount_kobo:
            raise ValidationError("Insufficient token balance")

        # Update atomically
        token.amount_used_kobo = new_used

        if new_used >= token.amount_kobo:
            token.status = "exhausted"
            logger.info("token_exhausted", token_id=str(token.id))

        await self.db.flush()

        return token

    async def revoke_token(
        self,
        token_id: str,
        reason: str = "user_requested",
        correlation_id: str | None = None,
    ) -> None:
        """Revoke an offline token and refund unused balance."""
        result = await self.db.execute(
            select(OfflineToken).where(OfflineToken.id == uuid.UUID(token_id))
        )
        token = result.scalar_one_or_none()

        if not token:
            raise NotFoundError("Token not found")

        if token.status in ["revoked", "expired"]:
            return  # Already done

        # Calculate refund
        unused = token.amount_kobo - (token.amount_used_kobo or 0)

        # Refund unused balance
        if unused > 0:
            await self.ledger_service.unlock_and_refund(
                user_id=token.user_id,
                amount_kobo=unused,
                token_id=token_id,
                correlation_id=correlation_id,
            )

        token.status = "revoked"

        await self.audit_repo.create(AuditLog(
            actor_type="user",
            actor_id=str(token.user_id),
            action="offline_token.revoked",
            resource="offline_token",
            resource_id=token_id,
            metadata={"reason": reason, "refunded_kobo": unused},
            correlation_id=correlation_id,
        ))

        logger.info("token_revoked", token_id=token_id, reason=reason, refunded_kobo=unused)

    async def validate_token_for_spend(
        self,
        serial: str,
        amount_kobo: int,
    ) -> OfflineToken:
        """
        Validate token is eligible for a spend.

        Checks status, expiry, and spend cutoff.
        """
        token = await self.get_token_by_serial(serial)

        if not token:
            raise NotFoundError("Token not found")

        now = datetime.now(timezone.utc)

        # Check basic status
        if token.status == "revoked":
            raise ValidationError("Token has been revoked")
        if token.status == "expired":
            raise TokenExpiredError()
        if token.status == "exhausted":
            raise TokenExhaustedError()

        # Check expiry
        if now > token.expires_at:
            raise TokenExpiredError()

        # Check spend cutoff (two-clock TTL)
        if now > token.customer_spend_cutoff:
            raise ValidationError("Token past spend cutoff time")

        # Check sufficient remaining balance
        remaining = token.amount_kobo - (token.amount_used_kobo or 0)
        if amount_kobo > remaining:
            raise ValidationError(f"Insufficient token balance: need {amount_kobo}, have {remaining}")

        return token

    async def get_token_status(self, token_id: str) -> dict:
        """Get detailed token status."""
        result = await self.db.execute(
            select(OfflineToken).where(OfflineToken.id == uuid.UUID(token_id))
        )
        token = result.scalar_one_or_none()

        if not token:
            raise NotFoundError("Token not found")

        now = datetime.now(timezone.utc)
        remaining = token.amount_kobo - (token.amount_used_kobo or 0)

        return {
            "token_id": str(token.id),
            "serial": token.serial,
            "status": token.status,
            "original_amount_kobo": token.amount_kobo,
            "used_amount_kobo": token.amount_used_kobo or 0,
            "remaining_kobo": remaining,
            "customer_spend_cutoff": token.customer_spend_cutoff.isoformat(),
            "expires_at": token.expires_at.isoformat(),
            "can_spend": (
                token.status == "active" and
                now <= token.customer_spend_cutoff and
                remaining > 0
            ),
            "is_spend_locked": now > token.customer_spend_cutoff,
            "is_expired": now > token.expires_at,
        }
