"""Debug endpoints for troubleshooting Nomba integration."""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/v1/debug", tags=["Debug"])


@router.get("/nomba/verify-webhook-routing")
async def verify_webhook_routing(
    db: AsyncSession = Depends(get_session),
):
    """
    Debug endpoint to verify Nomba webhook routing configuration.
    
    This endpoint:
    1. Fetches our virtual account's accountHolderId
    2. Calls POST /v1/webhooks/event-logs with that coreUserId and a test event
    3. Returns whether Nomba reports "No redirect configuration found"
    
    If the response indicates no redirect is configured, this will fail loudly
    with instructions to check the webhook registration form.
    """
    import httpx
    from app.core.config import settings
    from app.integrations.nomba import get_nomba_virtual_accounts_client
    from app.integrations.nomba.base_client import get_nomba_http_client
    
    try:
        nomba_client = get_nomba_virtual_accounts_client()
        
        # Use a test account ref to verify webhook routing
        test_ref = "OFFIMESH_WEBHOOK_TEST"
        
        # Check if we can get account info
        try:
            account_info = await nomba_client.get_virtual_account(test_ref)
            account_holder_id = account_info.get("accountHolderId")
            
            if not account_holder_id:
                return {
                    "status": "warning",
                    "message": "Could not determine accountHolderId from virtual account",
                    "account_holder_id": None,
                    "webhook_configured": False,
                    "instructions": (
                        "Register your webhook URL at: Nomba Dashboard > Webhooks & Sub-accounts. "
                        "Make sure to use the accountHolderId from your virtual account "
                        "(GET /v1/accounts/virtual/{accountRef}) as the account ID in the webhook form."
                    )
                }
        except Exception as e:
            logger.warning("account_lookup_failed", error=str(e))
            return {
                "status": "warning",
                "message": "Could not fetch virtual account details",
                "error": str(e),
                "instructions": (
                    "Create a virtual account first, then check the accountHolderId "
                    "from GET /v1/accounts/virtual/{accountRef}. "
                    "Use that exact ID when registering webhooks."
                )
            }
        
        # Now test webhook delivery
        try:
            http_client = get_nomba_http_client()
            client = await http_client.get_client()
            
            response = await client.post(
                f"{settings.nomba_base_url}/webhooks/event-logs",
                headers={
                    "accountId": account_holder_id,
                    "Content-Type": "application/json",
                },
                json={
                    "eventType": "test.webhook",
                    "pageSize": 1,
                }
            )
            
            if response.status_code == 200:
                webhook_configured = True
                status = "success"
                message = "Webhook routing verified successfully"
            else:
                webhook_configured = False
                status = "error"
                message = f"Webhook returned status {response.status_code}"
                
        except httpx.HTTPError as e:
            webhook_configured = False
            status = "error"
            message = f"Could not verify webhook routing: {str(e)}"
        
        if not webhook_configured:
            return {
                "status": "error",
                "message": message,
                "account_holder_id": account_holder_id,
                "webhook_configured": False,
                "instructions": (
                    "IMPORTANT: Webhook is not properly configured!\n\n"
                    f"1. Go to Nomba Dashboard > Webhooks & Sub-accounts\n"
                    f"2. Register your webhook URL pointing to: https://your-domain.com/v1/webhooks/nomba\n"
                    f"3. Use accountHolderId: {account_holder_id}\n"
                    f"4. Select event types: transfer.successful, transfer.failed\n\n"
                    "The accountHolderId must match the sub-account ID, NOT the parent account ID."
                ),
                "action_required": True
            }
        
        return {
            "status": "success",
            "message": message,
            "account_holder_id": account_holder_id,
            "webhook_configured": True,
        }
        
    except Exception as e:
        logger.exception("webhook_verification_failed", error=str(e))
        return {
            "status": "error",
            "message": f"Verification failed: {str(e)}",
            "account_holder_id": None,
            "webhook_configured": False,
            "error": str(e),
            "instructions": (
                "An error occurred during verification. Check your Nomba API credentials "
                "and ensure the virtual account service is properly configured."
            )
        }
