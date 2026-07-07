"""Identity verification service with configurable provider."""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.core.security import encrypt_value
from app.models.audit import AuditLog
from app.models.identity_verification import IdentityVerification
from app.repositories.audit_repository import AuditRepository
from app.repositories.user_repository import UserRepository

logger = structlog.get_logger(__name__)


class IdentityProvider(ABC):
    """Abstract base class for identity verification providers."""

    @abstractmethod
    async def verify_nin(self, nin: str, name: str) -> dict:
        """Verify NIN and return verification result."""
        pass

    @abstractmethod
    async def verify_bvn(self, bvn: str, name: str) -> dict:
        """Verify BVN and return verification result."""
        pass

    @abstractmethod
    async def verify_face(self, id_type: str, selfie_base64: str, id_image_url: str | None = None) -> dict:
        """Verify face matches ID photo."""
        pass


class MockIdentityProvider(IdentityProvider):
    """Mock provider for development/testing - always succeeds."""

    async def verify_nin(self, nin: str, name: str) -> dict:
        """Mock NIN verification."""
        return {
            "success": True,
            "verified": True,
            "name": name,
            "reference": f"mock_nin_{nin}",
            "message": "NIN verified (mock)",
        }

    async def verify_bvn(self, bvn: str, name: str) -> dict:
        """Mock BVN verification."""
        return {
            "success": True,
            "verified": True,
            "name": name,
            "reference": f"mock_bvn_{bvn}",
            "message": "BVN verified (mock)",
        }

    async def verify_face(self, id_type: str, selfie_base64: str, id_image_url: str | None = None) -> dict:
        """Mock face verification."""
        return {
            "success": True,
            "verified": True,
            "match_score": 95.0,
            "message": "Face verified (mock)",
        }


class DojahIdentityProvider(IdentityProvider):
    """Dojah identity verification provider."""

    def __init__(self) -> None:
        self.api_key = getattr(settings, 'dojah_api_key', '')
        self.app_id = getattr(settings, 'dojah_app_id', '')
        self.base_url = "https://api.dojah.io/api/v1"

    async def verify_nin(self, nin: str, name: str) -> dict:
        """Verify NIN via Dojah."""
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/kyc/nin",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "AppId": self.app_id,
                },
                json={
                    "nin": nin,
                    "name": name,
                },
            )
            response.raise_for_status()
            data = response.json()
            return {
                "success": True,
                "verified": data.get("verified", False),
                "name": data.get("full_name"),
                "reference": data.get("tracking_id"),
                "message": "NIN verified via Dojah",
            }

    async def verify_bvn(self, bvn: str, name: str) -> dict:
        """Verify BVN via Dojah."""
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/kyc/bvn",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "AppId": self.app_id,
                },
                json={
                    "bvn": bvn,
                    "name": name,
                },
            )
            response.raise_for_status()
            data = response.json()
            return {
                "success": True,
                "verified": data.get("verified", False),
                "name": data.get("full_name"),
                "reference": data.get("tracking_id"),
                "message": "BVN verified via Dojah",
            }

    async def verify_face(self, id_type: str, selfie_base64: str, id_image_url: str | None = None) -> dict:
        """Verify face via Dojah."""
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/kyc/face-match",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "AppId": self.app_id,
                },
                json={
                    "selfie_image": selfie_base64,
                    "id_type": id_type.upper(),
                },
            )
            response.raise_for_status()
            data = response.json()
            return {
                "success": True,
                "verified": data.get("verified", False),
                "match_score": data.get("confidence", 0) * 100,
                "message": "Face verified via Dojah",
            }


class IdentityVerificationService:
    """Service for identity verification with configurable provider."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.user_repo = UserRepository(db)
        self.audit_repo = AuditRepository(db)
        self.provider = self._get_provider()

    def _get_provider(self) -> IdentityProvider:
        """Get the configured identity provider."""
        provider_type = getattr(settings, 'identity_provider', 'mock').lower()

        if provider_type == 'dojah' and hasattr(settings, 'dojah_api_key') and settings.dojah_api_key:
            return DojahIdentityProvider()

        logger.warning(
            "identity_provider_fallback",
            provider=provider_type,
            reason="No API key configured",
        )
        return MockIdentityProvider()

    async def initiate_verification(
        self,
        user_id: str,
        id_type: str,
        id_number: str,
        correlation_id: str | None = None,
    ) -> IdentityVerification:
        """Initiate NIN or BVN verification."""
        if id_type not in ("nin", "bvn"):
            raise ValidationError("id_type must be 'nin' or 'bvn'")

        user = await self.user_repo.get_by_id(uuid.UUID(user_id))
        if not user:
            raise NotFoundError("User not found")

        id_encrypted = encrypt_value(id_number)

        verification = IdentityVerification(
            user_id=user.id,
            id_type=id_type,
            id_number_encrypted=id_encrypted,
            status="pending",
            provider=self.provider.__class__.__name__.replace("IdentityProvider", "").lower(),
        )
        self.db.add(verification)
        await self.db.flush()

        user_name = user.name or ""

        try:
            if id_type == "nin":
                result = await self.provider.verify_nin(id_number, user_name)
            else:
                result = await self.provider.verify_bvn(id_number, user_name)

            if result.get("success"):
                verification.status = "verified" if result.get("verified") else "failed"
                verification.verified_at = datetime.now(timezone.utc)
                verification.provider_reference = result.get("reference")
                verification.failure_reason = result.get("message") if not result.get("verified") else None

                if result.get("verified"):
                    if id_type == "nin":
                        user.nin_verified = True
                        user.nin_verification_reference = str(verification.id)
                    else:
                        user.bvn_verified = True
                        user.bvn_verification_reference = str(verification.id)

                    if result.get("name"):
                        user.name = result["name"]

                await self.db.flush()

                logger.info(
                    f"identity_{id_type}_verification_result",
                    verification_id=str(verification.id),
                    user_id=user_id,
                    verified=result.get("verified"),
                )
            else:
                verification.status = "failed"
                verification.failure_reason = result.get("message", "Verification failed")

        except Exception as e:
            logger.error(
                "identity_verification_error",
                verification_id=str(verification.id),
                user_id=user_id,
                id_type=id_type,
                error=str(e),
            )
            verification.status = "failed"
            verification.failure_reason = str(e)

        await self.audit_repo.create(AuditLog(
            actor_type="user",
            actor_id=user_id,
            action=f"identity.{id_type}_initiated",
            resource="identity_verification",
            resource_id=str(verification.id),
            metadata={"id_type": id_type, "status": verification.status},
            correlation_id=correlation_id,
        ))

        return verification

    async def verify_face(
        self,
        user_id: str,
        id_type: str,
        selfie_image_base64: str,
        correlation_id: str | None = None,
    ) -> IdentityVerification:
        """Verify face matches ID photo."""
        user = await self.user_repo.get_by_id(uuid.UUID(user_id))
        if not user:
            raise NotFoundError("User not found")

        result = await self.db.execute(
            select(IdentityVerification).where(
                IdentityVerification.user_id == user.id,
                IdentityVerification.id_type == id_type,
                IdentityVerification.status == "verified",
            ).order_by(IdentityVerification.verified_at.desc())
        )
        verification = result.scalar_one_or_none()

        if not verification:
            raise ValidationError(f"No verified {id_type.upper()} found. Complete {id_type.upper()} verification first.")

        try:
            face_result = await self.provider.verify_face(id_type, selfie_image_base64)

            verification.face_match_score = face_result.get("match_score", 0)
            verification.face_verified = face_result.get("verified", False)

            if face_result.get("verified"):
                user.face_verified = True
                verification.status = "verified"

            verification.verified_at = datetime.now(timezone.utc)
            await self.db.flush()

            logger.info(
                "face_verification_result",
                verification_id=str(verification.id),
                user_id=user_id,
                verified=face_result.get("verified"),
                match_score=face_result.get("match_score"),
            )

        except Exception as e:
            logger.error(
                "face_verification_error",
                verification_id=str(verification.id),
                user_id=user_id,
                error=str(e),
            )
            verification.failure_reason = str(e)

        await self.audit_repo.create(AuditLog(
            actor_type="user",
            actor_id=user_id,
            action="identity.face_verified",
            resource="identity_verification",
            resource_id=str(verification.id),
            metadata={
                "id_type": id_type,
                "verified": verification.face_verified,
                "score": verification.face_match_score,
            },
            correlation_id=correlation_id,
        ))

        return verification

    async def get_verification_status(
        self,
        user_id: str,
        id_type: str | None = None,
    ) -> dict:
        """Get user's identity verification status."""
        user = await self.user_repo.get_by_id(uuid.UUID(user_id))
        if not user:
            raise NotFoundError("User not found")

        result = {
            "nin_verified": user.nin_verified,
            "bvn_verified": user.bvn_verified,
            "face_verified": user.face_verified,
            "can_provision_offline_token": user.nin_verified and user.face_verified,
        }

        if id_type:
            verification = await self._get_latest_verification(user_id, id_type)
            if verification:
                result[f"{id_type}_verification"] = {
                    "status": verification.status,
                    "verified_at": verification.verified_at.isoformat() if verification.verified_at else None,
                    "face_match_score": verification.face_match_score,
                }

        return result

    async def _get_latest_verification(
        self,
        user_id: str,
        id_type: str,
    ) -> IdentityVerification | None:
        """Get latest verification for a user and ID type."""
        result = await self.db.execute(
            select(IdentityVerification).where(
                IdentityVerification.user_id == uuid.UUID(user_id),
                IdentityVerification.id_type == id_type,
            ).order_by(IdentityVerification.created_at.desc())
        )
        return result.scalar_one_or_none()

    async def can_user_provision_token(self, user_id: str) -> tuple[bool, str]:
        """Check if user can provision offline tokens."""
        user = await self.user_repo.get_by_id(uuid.UUID(user_id))
        if not user:
            return False, "User not found"

        if not user.nin_verified:
            return False, "NIN verification required before offline token issuance"

        if not user.face_verified:
            return False, "Face verification required before offline token issuance"

        return True, "Eligible for offline tokens"
