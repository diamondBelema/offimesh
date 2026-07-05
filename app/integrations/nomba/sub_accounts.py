"""Nomba sub-accounts API client for internal treasury bookkeeping.

ARCHITECTURAL DECISION - WHY VIRTUAL ACCOUNTS ARE NEVER SCOPED TO THIS SUB-ACCOUNT:
================================================================================

This sub-account integration is STRICTLY for internal bookkeeping and reporting.
Virtual accounts are NEVER scoped to this sub-account because of a KNOWN Nomba
integration failure mode:

1. Virtual accounts scoped to sub-accounts receive real money BUT:
   - NO webhook delivery occurs for funding events
   - Balance queries via parent account token return 401 Unauthorized
   - The funds become effectively invisible to the parent operation

2. All user wallet-funding virtual accounts MUST continue to be created at the
   PARENT account level - this is the confirmed working path with reliable
   webhook delivery.

3. This sub-account exists solely as a labeled balance view for treasury
   reconciliation - comparing our internal ledger_balances sum against what
   Nomba reports for this treasury bucket.

DO NOT "fix" this by adding sub-account-scoped virtual accounts. This is a
deliberate architectural decision, not an oversight. If Nomba resolves the
webhook/visibility issue in the future, verify against live documentation and
test thoroughly before changing this pattern.

================================================================================

Refactored to inherit from NombaResourceClient for production-grade reliability.
"""
from __future__ import annotations

import structlog

from app.integrations.nomba.base_client import NombaResourceClient
from app.integrations.nomba.types import NombaSubAccountResponse, NombaBalanceResponse

logger = structlog.get_logger(__name__)


class NombaSubAccountsClient(NombaResourceClient):
    """
    Client for Nomba sub-accounts API.

    Used for internal bookkeeping and balance reporting ONLY.
    NOT for virtual account creation or money movement.

    All requests use PARENT NOMBA_ACCOUNT_ID in the header for authentication.
    Never use the sub-account's own ID for auth.
    """

    async def create_sub_account(
        self,
        account_name: str,
        account_ref: str,
        *,
        request_id: str | None = None,
    ) -> NombaSubAccountResponse:
        """
        Create a sub-account for internal bookkeeping.

        POST /accounts/sub-accounts
        Body: { "accountName": account_name, "accountRef": account_ref }

        accountRef is OUR OWN stable identifier (e.g., "offimesh_treasury"),
        never a Nomba-generated ID. This allows us to look it up from our
        database without storing Nomba IDs as primary keys.

        IMPORTANT: Only ONE sub-account for the whole OffiMesh operation.
        This is NOT per-user.

        Args:
            account_name: Human-readable name for the sub-account
            account_ref: Our stable identifier (e.g., "offimesh_operational_treasury")
            request_id: Optional request ID for tracing

        Returns:
            NombaSubAccountResponse with sub-account details including Nomba ID
        """
        body = {
            "accountName": account_name,
            "accountRef": account_ref,
        }

        response = await self._post(
            "/accounts/sub-accounts",
            body,
            is_idempotent=True,  # accountRef provides idempotency
            request_id=request_id,
        )

        result = self._parse_response(response, NombaSubAccountResponse)

        logger.info(
            "nomba_sub_account_created",
            request_id=request_id,
            account_ref=account_ref,
            account_name=account_name,
            nomba_id=result.account_id,
        )

        return result

    async def list_sub_accounts(
        self,
        *,
        request_id: str | None = None,
    ) -> list[NombaSubAccountResponse]:
        """
        List all sub-accounts under the parent account.

        GET /accounts/sub-accounts

        Args:
            request_id: Optional request ID for tracing

        Returns:
            List of sub-accounts
        """
        response = await self._get(
            "/accounts/sub-accounts",
            request_id=request_id,
        )

        data = response.json()

        # Handle wrapped response
        if isinstance(data, dict) and "data" in data:
            inner = data["data"]
            if isinstance(inner, list):
                return [NombaSubAccountResponse.model_validate(item) for item in inner]
            return [NombaSubAccountResponse.model_validate(inner)]

        # Handle non-wrapped response
        if isinstance(data, list):
            return [NombaSubAccountResponse.model_validate(item) for item in data]

        return []

    async def get_sub_account_balance(
        self,
        sub_account_id: str,
        *,
        request_id: str | None = None,
    ) -> NombaBalanceResponse:
        """
        Get balance of a specific sub-account.

        GET /accounts/sub-accounts/{id}/balance

        This is the ONLY supported sub-account endpoint for reading data.
        There is NO documented endpoint for transfers between sub-accounts
        or from sub-accounts to external accounts.

        Args:
            sub_account_id: The Nomba-generated sub-account ID
            request_id: Optional request ID for tracing

        Returns:
            NombaBalanceResponse with balance information
        """
        response = await self._get(
            f"/accounts/sub-accounts/{sub_account_id}/balance",
            request_id=request_id,
        )

        result = self._parse_response(response, NombaBalanceResponse)

        logger.info(
            "nomba_sub_account_balance_retrieved",
            request_id=request_id,
            sub_account_id=sub_account_id,
        )

        return result

    async def get_sub_account(
        self,
        sub_account_id: str,
        *,
        request_id: str | None = None,
    ) -> NombaSubAccountResponse:
        """
        Get sub-account details by ID.

        GET /accounts/sub-accounts/{id}

        Args:
            sub_account_id: The Nomba-generated sub-account ID
            request_id: Optional request ID for tracing

        Returns:
            NombaSubAccountResponse with sub-account details
        """
        response = await self._get(
            f"/accounts/sub-accounts/{sub_account_id}",
            request_id=request_id,
        )

        return self._parse_response(response, NombaSubAccountResponse)


# Singleton instance
_nomba_sub_accounts_client: NombaSubAccountsClient | None = None


def get_nomba_sub_accounts_client() -> NombaSubAccountsClient:
    """Get the sub-accounts client singleton."""
    global _nomba_sub_accounts_client
    if _nomba_sub_accounts_client is None:
        _nomba_sub_accounts_client = NombaSubAccountsClient()
    return _nomba_sub_accounts_client
