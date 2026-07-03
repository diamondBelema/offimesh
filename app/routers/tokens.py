"""Offline token management API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.middleware.auth import CurrentUser
from app.middleware.correlation_id import get_correlation_id
from app.schemas import ProvisionTokenRequest, ok_response

router = APIRouter(prefix="/v1/tokens", tags=["Offline Tokens"])


@router.post("/provision")
async def provision_token(
    request: Request,
    body: ProvisionTokenRequest,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """Provision a new offline spending token."""
    correlation_id = get_correlation_id(request)
    from app.services.token_service import TokenService
    service = TokenService(db)

    token = await service.provision_token(
        user_id=str(user.id),
        device_id=body.device_id,
        requested_limit_kobo=body.requested_limit_kobo,
        correlation_id=correlation_id,
    )

    return ok_response({
        "token_id": token.token_id,
        "spending_limit_kobo": token.spending_limit_kobo,
        "amount_used_kobo": token.amount_used_kobo,
        "remaining_kobo": token.remaining_kobo,
        "status": token.status,
        "expires_at": token.expires_at.isoformat(),
        "server_signature": token.server_signature,
    }, correlation_id)


@router.get("/active")
async def get_active_tokens(
    request: Request,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """Get all active offline tokens for the current user."""
    correlation_id = get_correlation_id(request)
    from app.services.token_service import TokenService
    service = TokenService(db)

    tokens = await service.get_active_tokens(str(user.id))

    return ok_response({
        "tokens": [
            {
                "token_id": t.token_id,
                "spending_limit_kobo": t.spending_limit_kobo,
                "remaining_kobo": t.remaining_kobo,
                "expires_at": t.expires_at.isoformat(),
                "status": t.status,
                "device_id": str(t.device_id),
            }
            for t in tokens
        ],
        "total": len(tokens),
    }, correlation_id)


@router.delete("/{token_id}")
async def revoke_token(
    token_id: str,
    request: Request,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """Revoke an offline token."""
    correlation_id = get_correlation_id(request)
    from app.services.token_service import TokenService
    service = TokenService(db)

    await service.revoke_token(token_id, correlation_id=correlation_id)

    return ok_response({"revoked": True}, correlation_id)
