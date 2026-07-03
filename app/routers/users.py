"""User-related API routes."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.middleware.auth import CurrentUser
from app.middleware.correlation_id import get_correlation_id
from app.schemas import ok_response

router = APIRouter(prefix="/v1/users", tags=["Users"])


class UpdateUserRequest(BaseModel):
    name: str | None = None
    email: str | None = None


@router.get("/me")
async def get_current_user_info(
    request: Request,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """Get current user information."""
    correlation_id = get_correlation_id(request)
    return ok_response({
        "id": str(user.id),
        "name": user.name,
        "phone": "***" + user.phone_encrypted[-4:] if user.phone_encrypted else None,
        "email": user.email,
        "role": user.role,
        "trust_level": user.trust_level,
        "status": user.status,
        "bvn_verified": user.bvn_verified,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }, correlation_id)


@router.patch("/me")
async def update_current_user(
    request: Request,
    body: UpdateUserRequest,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """Update current user profile."""
    correlation_id = get_correlation_id(request)
    from app.services.auth_service import AuthService
    service = AuthService(db)
    updated_user = await service.update_user(
        user_id=str(user.id),
        name=body.name,
        email=body.email,
    )
    return ok_response({
        "id": str(updated_user.id),
        "name": updated_user.name,
        "email": updated_user.email,
    }, correlation_id)


@router.get("/me/balance")
async def get_user_balance(
    request: Request,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """Get user wallet balance."""
    correlation_id = get_correlation_id(request)
    from app.services.wallet_service import WalletService
    service = WalletService(db)
    result = await service.get_balance(str(user.id))
    return ok_response(result, correlation_id)


@router.get("/me/limits")
async def get_user_limits(
    request: Request,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """Get user transaction limits."""
    correlation_id = get_correlation_id(request)
    from app.core.config import settings
    return ok_response({
        "daily_limit_kobo": 1_000_000,  # 10,000 NGN
        "monthly_limit_kobo": 10_000_000,  # 100,000 NGN
        "per_transaction_limit_kobo": settings.max_transaction_amount_kobo,
        "offline_token_max_limit_kobo": settings.offline_token_max_limit_kobo,
    }, correlation_id)


@router.post("/bvn/initiate")
async def initiate_bvn_verification(
    request: Request,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """Initiate BVN verification."""
    correlation_id = get_correlation_id(request)
    # TODO: Implement BVN verification
    return ok_response({
        "reference": "bvn_ref_placeholder",
        "message": "BVN verification initiated",
    }, correlation_id)


@router.get("/bvn/status")
async def get_bvn_status(
    request: Request,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """Get BVN verification status."""
    correlation_id = get_correlation_id(request)
    return ok_response({
        "verified": user.bvn_verified,
        "status": "verified" if user.bvn_verified else "pending",
        "verified_at": None,
    }, correlation_id)
