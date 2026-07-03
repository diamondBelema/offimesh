"""Webhook handling API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.middleware.correlation_id import get_correlation_id
from app.schemas import ok_response

router = APIRouter(prefix="/v1/webhooks", tags=["Webhooks"])


@router.post("/nomba")
async def handle_nomba_webhook(
    request: Request,
    db: AsyncSession = Depends(get_session),
    nomba_signature: str = Header(None, alias="nomba-signature"),
):
    """
    Handle incoming Nomba webhook.

    CRITICAL: This endpoint must:
    1. Verify signature with HMAC-SHA256
    2. Check request_id for idempotency
    3. Return 200 immediately
    4. Offload processing to Celery worker
    """
    correlation_id = get_correlation_id(request)

    # Read raw body bytes BEFORE any JSON parsing
    raw_body = await request.body()

    from app.services.webhook_service import WebhookService
    service = WebhookService(db)

    try:
        # This will verify signature, check for duplicates, and store event
        event = await service.handle_webhook(
            raw_body=raw_body,
            signature=nomba_signature or "",
            correlation_id=correlation_id,
        )

        # Offload processing to Celery worker (don't await)
        # from app.workers.webhook_worker import process_webhook_event
        # process_webhook_event.delay(str(event.id))
        # For now, process inline (in production, use Celery)

        # Return 200 immediately
        return ok_response({"received": True, "request_id": event.request_id}, correlation_id)

    except Exception as e:
        # Still return 200 for duplicate webhooks (they will retry)
        if "duplicate" in str(e).lower() or "already" in str(e).lower():
            return ok_response({"received": True, "duplicate": True}, correlation_id)

        # Return 401 for signature errors
        from app.core.exceptions import WebhookSignatureError
        if isinstance(e, WebhookSignatureError):
            return Response(
                content='{"success": false, "error": "Invalid signature"}',
                status_code=401,
                media_type="application/json",
            )

        # Log and return 200 for other errors (Nomba will retry otherwise)
        import structlog
        logger = structlog.get_logger()
        logger.error("webhook_error", error=str(e))

        return Response(
            content='{"success": false, "error": "Processing failed"}',
            status_code=500,
            media_type="application/json",
        )
