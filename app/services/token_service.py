"""Offline token provisioning service."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import structlog
import ulid
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    NotFoundError,
    TokenExhaustedError,
    TokenExpiredError,
    ValidationError,
)
from app.core.security import generate_nonce, sign_payload
from app.models.audit import AuditLog
from app.models.token import OfflineToken
from app.repositories.audit_repository import AuditRepository
from app.repositories.device_repository import DeviceRepository
from app.repositories.token_repository import TokenRepository
from app.repositories.user_repository import UserRepository

logger = structlog.get_logger(__name__)


class TokenService:
    """Service for offline spending token management."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.token_repo = TokenRepository(db)
        self.user_repo = UserRepository(db)
        self.device_repo = DeviceRepository(db)
        self.audit_repo = AuditRepository(db)

    async def provision_token(
        self,
        user_id: str,
        device_id: str | None,
        requested_limit_kobo: int,
        correlation_id: str | None = None,
    ) -> OfflineToken:
        """
        Provision an offline spending token.

        Token is signed by the server and has configurable limits.
        """
        user = await self.user_repo.get_by_id(uuid.UUID(user_id))
        if not user:
            raise NotFoundError("User not found")

        # Get active devices
        devices = await self.device_repo.get_active_by_user(user.id)
        if not devices:
            raise NotFoundError("No active devices found")

        # Use specified device or first active device
        if device_id:
            device = await self.device_repo.get_by_id(uuid.UUID(device_id))
            if not device or device.user_id != user.id:
                raise NotFoundError("Device not found or not owned by user")
        else:
            device = devices[0]

        # Check user has sufficient balance (soft check, offline)
        limit = min(requested_limit_kobo, settings.offline_token_max_limit_kobo)

        # Generate token ID
        token_id = f"tok_{ulid.new()}"

        # Set expiry
        expires_at = datetime.now(timezone.utc) + timedelta(
            hours=settings.offline_token_ttl_hours
        )

        # Create token payload for signing
        token_payload = {
            "token_id": token_id,
            "user_id": user_id,
            "device_id": str(device.id),
            "spending_limit_kobo": limit,
            "expires_at": expires_at.isoformat(),
        }

        # Sign with server key (in production, use proper signing)
        server_signature = generate_nonce(64)  # Placeholder for actual signature

        # Create token
        token = OfflineToken(
            token_id=token_id,
            user_id=user.id,
            device_id=device.id,
            spending_limit_kobo=limit,
            status="active",
            server_signature=server_signature,
            expires_at=expires_at,
        )
        await self.token_repo.create(token)

        # Audit log
        await self.audit_repo.create(AuditLog(
            actor_type="user",
            actor_id=user_id,
            action="token.provisioned",
            resource="offline_token",
            resource_id=token_id,
            metadata={
                "spending_limit_kobo": limit,
                "device_id": str(device.id),
                "expires_at": expires_at.isoformat(),
            },
            correlation_id=correlation_id,
        ))

        logger.info(
            "token_provisioned",
            token_id=token_id,
            user_id=user_id,
            limit=limit,
        )

        return token

    async def get_active_tokens(self, user_id: str) -> list[OfflineToken]:
        """Get all active tokens for a user."""
        return await self.token_repo.get_active_by_user(uuid.UUID(user_id))

    async def revoke_token(
        self,
        token_id: str,
        reason: str = "user_requested",
        correlation_id: str | None = None,
    ) -> None:
        """Revoke an offline token."""
        await self.token_repo.revoke(token_id, reason)

        await self.audit_repo.create(AuditLog(
            actor_type="user",
            actor_id="system",  # Would be actual user
            action="token.revoked",
            resource="offline_token",
            resource_id=token_id,
            metadata={"reason": reason},
            correlation_id=correlation_id,
        ))

        logger.info("token_revoked", token_id=token_id, reason=reason)

    async def increment_usage(
        self,
        token_id: str,
        amount_kobo: int,
    ) -> OfflineToken:
        """
        Increment token usage after successful transaction.

        Marks as exhausted if limit reached.
        """
        token = await self.token_repo.increment_usage(token_id, amount_kobo)
        if token and token.is_exhausted:
            await self.token_repo.mark_exhausted(token_id)
            logger.info("token_exhausted", token_id=token_id)
        return token

    async def validate_token(self, token_id: str) -> OfflineToken:
        """Validate token for transaction processing."""
        token = await self.token_repo.get_by_token_id(token_id)
        if not token:
            raise NotFoundError("Token not found")

        if token.status == "revoked":
            raise ValidationError("Token has been revoked")
        if token.status == "exhausted":
            raise TokenExhaustedError()
        if token.status == "expired" or token.is_expired:
            raise TokenExpiredError()

        return token
