"""Wallet funding API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.middleware.auth import CurrentUser
from app.middleware.correlation_id import get_correlation_id
from app.schemas import FundWalletRequest, ok_response

router = APIRouter(prefix="/v1/wallet", tags=["Wallet"])


@router.post("/fund")
async def create_funding_account(
    request: Request,
    body: FundWalletRequest,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """Create a virtual account for wallet funding."""
    correlation_id = get_correlation_id(request)
    from app.services.wallet_service import WalletService
    service = WalletService(db)

    account = await service.create_funding_account(
        user_id=str(user.id),
        expected_amount_kobo=body.expected_amount_kobo,
        correlation_id=correlation_id,
    )

    return ok_response({
        "id": str(account.id),
        "nuban": account.nuban,
        "account_name": account.account_name,
        "bank_name": account.bank_name,
        "expected_amount_kobo": account.expected_amount_kobo,
        "status": account.status,
        "created_at": account.created_at.isoformat(),
        "expires_at": account.expires_at.isoformat() if account.expires_at else None,
    }, correlation_id)


@router.get("/fund/{account_id}")
async def get_funding_status(
    account_id: str,
    request: Request,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """Get funding account status."""
    correlation_id = get_correlation_id(request)
    from app.services.wallet_service import WalletService
    service = WalletService(db)

    account = await service.get_funding_account(account_id)

    if not account:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("Funding account not found")

    if account.user_id != user.id:
        from app.core.exceptions import PermissionDeniedError
        raise PermissionDeniedError()

    return ok_response({
        "account_id": str(account.id),
        "nuban": account.nuban,
        "status": account.status,
        "expected_amount_kobo": account.expected_amount_kobo,
        "received_amount_kobo": account.received_amount_kobo,
        "created_at": account.created_at.isoformat(),
    }, correlation_id)


@router.get("/balance")
async def get_wallet_balance(
    request: Request,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """Get wallet balance."""
    correlation_id = get_correlation_id(request)
    from app.services.wallet_service import WalletService
    service = WalletService(db)

    result = await service.get_balance(str(user.id))
    return ok_response(result, correlation_id)
