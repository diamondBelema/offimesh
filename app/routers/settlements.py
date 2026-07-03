"""Settlement API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.middleware.auth import CurrentUser
from app.middleware.correlation_id import get_correlation_id
from app.schemas import ok_response

router = APIRouter(prefix="/v1/settlements", tags=["Settlements"])


@router.get("")
async def list_settlements(
    request: Request,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
):
    """List settlements."""
    correlation_id = get_correlation_id(request)
    from app.services.settlement_service import SettlementService
    service = SettlementService(db)

    settlements, total = await service.list_settlements(
        page=page,
        page_size=page_size,
        status=status,
    )

    return ok_response({
        "items": [
            {
                "id": str(s.id),
                "tx_id": s.tx_id,
                "amount_kobo": s.amount_kobo,
                "status": s.status,
                "nomba_transfer_id": s.nomba_transfer_id,
                "attempts": s.attempts,
                "settled_at": s.settled_at.isoformat() if s.settled_at else None,
                "created_at": s.created_at.isoformat(),
            }
            for s in settlements
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": (page * page_size) < total,
    }, correlation_id)


@router.get("/{tx_id}")
async def get_settlement(
    tx_id: str,
    request: Request,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """Get settlement by transaction ID."""
    correlation_id = get_correlation_id(request)
    from app.services.settlement_service import SettlementService
    service = SettlementService(db)

    settlement = await service.get_settlement(tx_id)

    if not settlement:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("Settlement not found")

    return ok_response({
        "id": str(settlement.id),
        "tx_id": settlement.tx_id,
        "nomba_transfer_id": settlement.nomba_transfer_id,
        "amount_kobo": settlement.amount_kobo,
        "fee_kobo": settlement.fee_kobo,
        "status": settlement.status,
        "attempts": settlement.attempts,
        "last_attempt_at": settlement.last_attempt_at.isoformat() if settlement.last_attempt_at else None,
        "settled_at": settlement.settled_at.isoformat() if settlement.settled_at else None,
        "error_code": settlement.error_code,
        "error_message": settlement.error_message,
        "created_at": settlement.created_at.isoformat(),
    }, correlation_id)


@router.post("/{tx_id}/process")
async def process_settlement(
    tx_id: str,
    request: Request,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """Trigger settlement for a transaction."""
    correlation_id = get_correlation_id(request)
    from app.services.settlement_service import SettlementService
    service = SettlementService(db)

    result = await service.process_settlement(tx_id, correlation_id)

    return ok_response({
        "tx_id": tx_id,
        "success": result.get("success", False),
        "nomba_reference": result.get("nomba_reference"),
        "status": "settled" if result.get("success") else "failed",
        "message": None if result.get("success") else result.get("reason"),
    }, correlation_id)
