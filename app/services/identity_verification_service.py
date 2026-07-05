"""Identity verification service (mocked for hackathon)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.audit import AuditLog
from app.models.identity_verification import IdentityVerification
from app.models.user import User
from app.repositories.audit_repository import AuditRepository
from app.repositories.user_repository import UserRepository

logger = structlog.get_logger(__name__)


class IdentityVerificationService:
    """
    Identity verification service.

    HACKATHON MODE: Always returns verified = True after delay.
    TODO: Replace with live Dojah/Smile Identity/VerifyMe calls before production.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.user_repo = UserRepository(db)
        self.audit_repo = AuditRepository(db)

    async def initiate_verification(
        self,
        user_id: str,
        id_type: str,
        id_number: str,
        correlation_id: str | None = None,
    ) -> IdentityVerification:
        """
        Initiate identity verification (NIN or BVN).

        Creates verification record and calls mock provider.
        """
        if id_type not in ("nin", "bvn"):
            raise ValidationError("id_type must be 'nin' or 'bvn'")

        user = await self.user_repo.get_by_id(uuid.UUID(user_id))
        if not user:
            raise NotFoundError("User not found")

        # Create verification record
        verification = IdentityVerification(
            user_id=user.id,
            id_type=id_type,
            id_number_encrypted=id_number,  # TODO: Encrypt before storing
            status="pending",
            provider="mock_provider",  # TODO: Replace with real provider
        )
        self.db.add(verification)
        await self.db.flush()

        logger.info(
            "identity_verification_initiated",
            verification_id=str(verification.id),
            user_id=user_id,
            id_type=id_type,
            # TODO: This is mocked - replace with live provider call
        )

        # HACKATHON MODE: Auto-verify after simulated delay
        # In production, this would be an async callback from the provider
        verification.status = "verified"
        verification.verified_at = datetime.now(timezone.utc)
        verification.face_match_score = 95.0  # Mock score
        verification.provider_reference = f"mock_ref_{verification.id}"

        await self.db.flush()

        # Update user verification flags
        if id_type == "nin":
            user.nin_verified = True
            user.nin_verification_reference = str(verification.id)
        elif id_type == "bvn":
            user.bvn_verified = True
            user.bvn_verification_reference = str(verification.id)

        # Audit log
        await self.audit_repo.create(AuditLog(
            actor_type="user",
            actor_id=user_id,
            action="identity.verification_initiated",
            resource="identity_verification",
            resource_id=str(verification.id),
            metadata={"id_type": id_type},
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
        """
        Verify face matches ID photo.

        HACKATHON MODE: Always returns 95% match.
        TODO: Replace with live Smile Identity/VerifyMe face comparison API.
        """
        user = await self.user_repo.get_by_id(uuid.UUID(user_id))
        if not user:
            raise NotFoundError("User not found")

        # Find pending verification
        result = await self.db.execute(
            select(IdentityVerification).where(
                IdentityVerification.user_id == user.id,
                IdentityVerification.id_type == id_type,
            ).order_by(IdentityVerification.created_at.desc())
        )
        verification = result.scalar_one_or_none()

        if not verification:
            raise NotFoundError(f"No {id_type.upper()} verification found")

        # HACKATHON MODE: Always succeed
        # TODO: Replace with actual face comparison API call
        verification.face_match_score = 95.0
        verification.face_verified = True
        verification.status = "verified"
        verification.verified_at = datetime.now(timezone.utc)

        user.face_verified = True

        await self.db.flush()

        logger.info(
            "face_verification_completed_mocked",
            verification_id=str(verification.id),
            match_score=95.0,
            # TODO: Replace with live face verification API
        )

        # Audit log
        await self.audit_repo.create(AuditLog(
            actor_type="user",
            actor_id=user_id,
            action="identity.face_verified",
            resource="identity_verification",
            resource_id=str(verification.id),
            metadata={"match_score": 95.0, "id_type": id_type},
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
        """
        Check if user can provision offline tokens.

        Requires: NIN verified AND face verified.
        """
        user = await self.user_repo.get_by_id(uuid.UUID(user_id))
        if not user:
            return False, "User not found"

        if not user.nin_verified:
            return False, "NIN verification required before offline token issuance"

        if not user.face_verified:
            return False, "Face verification required before offline token issuance"

        return True, "Eligible for offline tokens"
