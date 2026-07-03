"""Transaction API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.middleware.auth import CurrentUser
from app.middleware.correlation_id import get_correlation_id
from app.schemas import TransactionSyncRequest, ok_response

router = APIRouter(prefix="/v1/transactions", tags=["Transactions"])


@router.post("/sync")
async def sync_transactions(
    request: Request,
    body: TransactionSyncRequest,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """Sync a batch of offline transactions."""
    correlation_id = get_correlation_id(request)
    from app.services.transaction_service import TransactionService
    service = TransactionService(db)

    result = await service.sync_batch(
        batch_id=body.batch_id,
        device_id=body.device_id,
        transactions=body.transactions,
        device_signature=body.device_signature,
        correlation_id=correlation_id,
    )

    return ok_response(result, correlation_id)


@router.get("")
async def list_transactions(
    request: Request,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
):
    """List transactions for the current user."""
    correlation_id = get_correlation_id(request)
    from app.services.transaction_service import TransactionService
    service = TransactionService(db)

    transactions, total = await service.list_transactions(
        user_id=str(user.id),
        page=page,
        page_size=page_size,
        status=status,
    )

    return ok_response({
        "items": [
            {
                "tx_id": tx.tx_id,
                "payer_user_id": str(tx.payer_user_id),
                "payee_user_id": str(tx.payee_user_id),
                "amount_kobo": tx.amount_kobo,
                "currency": tx.currency,
                "status": tx.status,
                "merchant_reference": tx.merchant_reference,
                "initiated_at": tx.initiated_at.isoformat() if tx.initiated_at else None,
                "synced_at": tx.synced_at.isoformat() if tx.synced_at else None,
                "settled_at": tx.settled_at.isoformat() if tx.settled_at else None,
            }
            for tx in transactions
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": (page * page_size) < total,
    }, correlation_id)


@router.get("/{tx_id}")
async def get_transaction(
    tx_id: str,
    request: Request,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """Get a specific transaction by ID."""
    correlation_id = get_correlation_id(request)
    from app.services.transaction_service import TransactionService
    service = TransactionService(db)

    tx = await service.get_transaction(tx_id)

    if not tx:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("Transaction not found")

    # Check user is payer or payee
    if tx.payer_user_id != user.id and tx.payee_user_id != user.id:
        from app.core.exceptions import PermissionDeniedError
        raise PermissionDeniedError()

    return ok_response({
        "tx_id": tx.tx_id,
        "payer_user_id": str(tx.payer_user_id),
        "payee_user_id": str(tx.payee_user_id),
        "amount_kobo": tx.amount_kobo,
        "currency": tx.currency,
        "status": tx.status,
        "nomba_reference": tx.nomba_reference,
        "merchant_reference": tx.merchant_reference,
        "fraud_score": tx.fraud_score,
        "initiated_at": tx.initiated_at.isoformat() if tx.initiated_at else None,
        "synced_at": tx.synced_at.isoformat() if tx.synced_at else None,
        "settled_at": tx.settled_at.isoformat() if tx.settled_at else None,
    }, correlation_id)
