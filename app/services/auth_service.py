"""Authentication and user management service."""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    InvalidOTPError,
    NotFoundError,
    ValidationError,
)
from app.core.redis import cache_get, cache_set
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decrypt_value,
    encrypt_value,
    hash_phone,
    hash_pin,
    verify_phone_hash,
    verify_pin,
)
from app.models.audit import AuditLog
from app.models.device import Device
from app.models.user import User
from app.repositories.audit_repository import AuditRepository
from app.repositories.device_repository import DeviceRepository
from app.repositories.user_repository import UserRepository

logger = structlog.get_logger(__name__)


class AuthService:
    """Service for authentication and user management."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.user_repo = UserRepository(db)
        self.device_repo = DeviceRepository(db)
        self.audit_repo = AuditRepository(db)

    async def register(
        self,
        phone: str,
        name: str | None,
        role: str,
        correlation_id: str | None = None,
    ) -> dict:
        """Register a new user."""
        # Check if user already exists
        phone_hash, salt = hash_phone(phone)
        existing = await self.user_repo.get_by_phone_hash(phone_hash)
        if existing:
            raise ConflictError("User already registered", field="phone")

        # Encrypt phone for support lookup
        phone_encrypted = encrypt_value(phone)

        # Create user
        user = User(
            phone_hash=phone_hash,
            phone_salt=salt,
            phone_encrypted=phone_encrypted,
            name=name,
            role=role,
            trust_level="untrusted",
            status="pending_verification",
        )
        await self.user_repo.create(user)

        # Generate and cache OTP
        otp = self._generate_otp()
        await cache_set(f"otp:{user.id}", otp, ttl_seconds=600)

        logger.info("otp_generated", user_id=str(user.id))  # Never log OTP value

        # Audit log
        await self.audit_repo.create(AuditLog(
            actor_type="user",
            actor_id=str(user.id),
            action="user.registered",
            resource="user",
            resource_id=str(user.id),
            correlation_id=correlation_id,
        ))

        return {
            "user_id": str(user.id),
            "otp_sent": True,
            "message": "OTP sent to your phone",
        }

    def _generate_otp(self) -> str:
        """Generate a 6-digit OTP."""
        return "".join(secrets.choice("0123456789") for _ in range(6))

    async def verify_otp(
        self,
        user_id: str,
        otp: str,
        correlation_id: str | None = None,
    ) -> dict:
        """Verify OTP and activate user account."""
        cached_otp = await cache_get(f"otp:{user_id}")
        if not cached_otp:
            raise InvalidOTPError("OTP expired or invalid")

        if otp != cached_otp:
            raise InvalidOTPError("Invalid OTP")

        user_uuid = uuid.UUID(user_id)
        await self.user_repo.update_status(user_uuid, "active")

        await self.audit_repo.create(AuditLog(
            actor_type="user",
            actor_id=user_id,
            action="user.verified",
            resource="user",
            resource_id=user_id,
            correlation_id=correlation_id,
        ))

        return {"verified": True, "user_id": user_id}

    async def login(
        self,
        phone: str,
        correlation_id: str | None = None,
    ) -> dict:
        """Initiate login by sending OTP to phone."""
        phone_hash, _ = hash_phone(phone)
        user = await self.user_repo.get_by_phone_hash(phone_hash)

        if not user:
            return {"otp_sent": True, "message": "OTP sent if phone is registered"}

        otp = self._generate_otp()
        await cache_set(f"otp:{user.id}", otp, ttl_seconds=600)

        logger.info("login_otp_generated", user_id=str(user.id))  # Never log OTP value

        await self.audit_repo.create(AuditLog(
            actor_type="user",
            actor_id=str(user.id),
            action="user.login_initiated",
            resource="user",
            resource_id=str(user.id),
            correlation_id=correlation_id,
        ))

        return {"user_id": str(user.id), "otp_sent": True}

    async def verify_login(
        self,
        user_id: str,
        otp: str,
        correlation_id: str | None = None,
    ) -> dict:
        """Verify login OTP and issue tokens."""
        cached_otp = await cache_get(f"otp:{user_id}")
        if not cached_otp or otp != cached_otp:
            raise InvalidOTPError("Invalid OTP")

        user = await self.user_repo.get_by_id(uuid.UUID(user_id))
        if not user:
            raise NotFoundError("User not found")

        if user.status != "active":
            raise AuthenticationError("Account not active")

        devices = await self.device_repo.get_active_by_user(user.id)
        device_id = devices[0].id if devices else None

        if not device_id:
            device = Device(
                user_id=user.id,
                device_fingerprint=f"web_{user.id}",
                device_public_key="web_client",
                trust_level="standard",
                device_type="web",
            )
            await self.device_repo.create(device)
            device_id = device.id

        token_family = str(uuid.uuid4())
        access_token = create_access_token(
            subject=str(user.id),
            device_id=str(device_id),
            role=user.role,
        )
        refresh_token = create_refresh_token(
            subject=str(user.id),
            device_id=str(device_id),
            token_family=token_family,
        )

        await self.audit_repo.create(AuditLog(
            actor_type="user",
            actor_id=user_id,
            action="user.login_completed",
            resource="user",
            resource_id=user_id,
            correlation_id=correlation_id,
        ))

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": settings.jwt_access_ttl_minutes * 60,
        }

    async def refresh_tokens(self, refresh_token: str) -> dict:
        """Refresh access token using refresh token."""
        from app.core.security import decode_token

        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise AuthenticationError("Invalid token type")

        user_id = payload["sub"]
        device_id = payload["device_id"]

        user = await self.user_repo.get_by_id(uuid.UUID(user_id))
        if not user or user.status != "active":
            raise AuthenticationError("User not found or inactive")

        new_family = str(uuid.uuid4())
        new_access = create_access_token(
            subject=user_id,
            device_id=device_id,
            role=user.role,
        )
        new_refresh = create_refresh_token(
            subject=user_id,
            device_id=device_id,
            token_family=new_family,
        )

        return {
            "access_token": new_access,
            "refresh_token": new_refresh,
            "token_type": "Bearer",
            "expires_in": settings.jwt_access_ttl_minutes * 60,
        }

    async def set_pin(
        self,
        user_id: str,
        pin: str,
        correlation_id: str | None = None,
    ) -> dict:
        """Set transaction PIN for user."""
        pin_hash = hash_pin(pin)
        await self.user_repo.set_pin(uuid.UUID(user_id), pin_hash)

        await self.audit_repo.create(AuditLog(
            actor_type="user",
            actor_id=user_id,
            action="user.pin_set",
            resource="user",
            resource_id=user_id,
            correlation_id=correlation_id,
        ))

        return {"pin_set": True}

    async def verify_pin(
        self,
        user_id: str,
        pin: str,
        correlation_id: str | None = None,
    ) -> dict:
        """
        Verify transaction PIN.

        RATE LIMITED: 5 attempts per 15 minutes.
        Uses atomic Redis operations to prevent race conditions.
        """
        from app.core.redis import get_pin_attempts, increment_pin_attempts, reset_pin_attempts
        from app.core.security import verify_pin as verify_pin_hash

        # Check rate limit (5 attempts per 15 minutes)
        attempt_count = await get_pin_attempts(user_id)

        if attempt_count >= 5:
            raise ValidationError(
                "Too many PIN attempts. Please try again in 15 minutes."
            )

        user = await self.user_repo.get_by_id(uuid.UUID(user_id))
        if not user or not user.pin_hash:
            # Atomically increment counter even on invalid user (prevents enumeration)
            await increment_pin_attempts(user_id)
            raise AuthenticationError("PIN not set or user not found")

        if verify_pin_hash(pin, user.pin_hash):
            # Reset attempts on success
            await reset_pin_attempts(user_id)

            await self.audit_repo.create(AuditLog(
                actor_type="user",
                actor_id=user_id,
                action="user.pin_verified",
                resource="user",
                resource_id=user_id,
                correlation_id=correlation_id,
            ))

            return {"verified": True, "remaining_attempts": 5}
        else:
            # Atomically increment failed attempts
            new_count = await increment_pin_attempts(user_id)

            await self.audit_repo.create(AuditLog(
                actor_type="user",
                actor_id=user_id,
                action="user.pin_verify_failed",
                resource="user",
                resource_id=user_id,
                metadata={"attempt": new_count},
                correlation_id=correlation_id,
            ))

            remaining = 5 - new_count
            if remaining <= 0:
                raise ValidationError(
                    "Too many PIN attempts. Please try again in 15 minutes."
                )

            return {"verified": False, "remaining_attempts": remaining}

    async def get_user(self, user_id: str) -> User:
        """Get user by ID."""
        user = await self.user_repo.get_by_id(uuid.UUID(user_id))
        if not user:
            raise NotFoundError("User not found")
        return user

    async def update_user(
        self,
        user_id: str,
        name: str | None = None,
        email: str | None = None,
    ) -> User:
        """Update user profile."""
        user = await self.user_repo.get_by_id(uuid.UUID(user_id))
        if not user:
            raise NotFoundError("User not found")

        if name:
            user.name = name
        if email:
            user.email = email

        await self.user_repo.update(user)
        return user
