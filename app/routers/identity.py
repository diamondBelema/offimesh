"""Identity verification API routes."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.middleware.auth import CurrentUser, get_current_user
from app.middleware.correlation_id import get_correlation_id
from app.schemas.identity import (
    CanProvisionTokenResponse,
    DeviceTrustPayloadSchema,
    InitiateVerificationRequest,
    InitiateVerificationResponse,
    VerificationStatusResponse,
    VerifyFaceRequest,
    VerifyFaceResponse,
)
from app.schemas import ok_response
from app.services.identity_verification_service import IdentityVerificationService

router = APIRouter(prefix="/v1/users/identity", tags=["Identity Verification"])


@router.post("/initiate")
async def initiate_verification(
    request: Request,
    body: InitiateVerificationRequest,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """
    Initiate identity verification (NIN or BVN).

    HACKATHON MODE: Auto-verifies after simulated check.
    In production: Integrates with Dojah/Smile Identity/VerifyMe.
    """
    correlation_id = get_correlation_id(request)
    service = IdentityVerificationService(db)

    result = await service.initiate_verification(
        user_id=str(user.id),
        id_type=body.id_type,
        id_number=body.id_number,
        correlation_id=correlation_id,
    )

    return ok_response(
        InitiateVerificationResponse(
            verification_id=str(result.id),
            id_type=result.id_type,
            status=result.status,
        ),
        correlation_id,
    )


@router.post("/face-verify")
async def verify_face(
    request: Request,
    body: VerifyFaceRequest,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """
    Verify face matches ID photo.

    HACKATHON MODE: Always returns 95% match.
    In production: Uses Smile Identity/VerifyMe face comparison API.
    """
    correlation_id = get_correlation_id(request)
    service = IdentityVerificationService(db)

    result = await service.verify_face(
        user_id=str(user.id),
        id_type=body.id_type,
        selfie_image_base64=body.selfie_image_base64,
        correlation_id=correlation_id,
    )

    return ok_response(
        VerifyFaceResponse(
            verification_id=str(result.id),
            id_type=result.id_type,
            status=result.status,
            face_match_score=result.face_match_score or 0.0,
            face_verified=result.face_verified,
            message="Face verification completed",
        ),
        correlation_id,
    )


@router.get("/status")
async def get_verification_status(
    request: Request,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """
    Get user's identity verification status.

    Returns NIN, BVN, and face verification status.
    """
    correlation_id = get_correlation_id(request)
    service = IdentityVerificationService(db)

    result = await service.get_verification_status(str(user.id))

    return ok_response(
        VerificationStatusResponse(
            nin_verified=result.get("nin_verified", False),
            bvn_verified=result.get("bvn_verified", False),
            face_verified=result.get("face_verified", False),
            can_provision_offline_token=result.get("can_provision_offline_token", False),
        ),
        correlation_id,
    )


@router.get("/can-provision-token")
async def check_token_provisioning_eligibility(
    request: Request,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """
    Check if user is eligible to provision offline tokens.

    Requirements: NIN verified AND face verified.
    """
    correlation_id = get_correlation_id(request)
    service = IdentityVerificationService(db)

    can_provision, reason = await service.can_user_provision_token(str(user.id))

    requirements = []
    if not user.nin_verified:
        requirements.append("NIN verification required")
    if not user.face_verified:
        requirements.append("Face verification required")

    return ok_response(
        CanProvisionTokenResponse(
            can_provision=can_provision,
            reason=reason,
            requirements=requirements,
        ),
        correlation_id,
    )


@router.get("/{id_type}/details")
async def get_id_verification_details(
    request: Request,
    id_type: str,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """
    Get detailed verification info for a specific ID type.
    """
    correlation_id = get_correlation_id(request)
    service = IdentityVerificationService(db)

    result = await service.get_verification_status(str(user.id), id_type=id_type)

    return ok_response(result, correlation_id)
