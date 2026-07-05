"""Nomba virtual accounts API client for wallet funding.

Virtual accounts are dedicated NUBAN accounts that customers can
transfer funds into to top up their OffiMesh wallet.

Refactored to inherit from NombaResourceClient for production-grade
reliability, observability, and error handling.
"""
from __future__ import annotations

import structlog

from app.integrations.nomba.base_client import NombaResourceClient
from app.integrations.nomba.types import NombaVirtualAccountResponse

logger = structlog.get_logger(__name__)


class NombaVirtualAccountsClient(NombaResourceClient):
    """
    Client for Nomba virtual accounts API.

    Used for wallet funding - creates a dedicated NUBAN for customers
    to transfer funds into their OffiMesh wallet.

    IMPORTANT: Virtual accounts are created at the PARENT account level,
    NOT under sub-accounts. Sub-account-scoped virtual accounts have known
    issues with webhook delivery and balance visibility.
    """

    async def create_virtual_account(
        self,
        account_ref: str,
        account_name: str,
        amount: int | None = None,
        *,
        request_id: str | None = None,
    ) -> NombaVirtualAccountResponse:
        """
        Create a virtual account for wallet funding.

        POST /accounts/virtual
        Body: accountRef, accountName, amount (optional)

        Returns a dedicated NUBAN that the customer can transfer to.
        The account_ref should be a stable identifier we can use to
        match webhook events back to the user.

        Args:
            account_ref: Our stable reference (e.g., user_id or UUID)
            account_name: Name to show on the NUBAN (e.g., user's name)
            amount: Optional expected amount in kobo
            request_id: Optional request ID for tracing

        Returns:
            NombaVirtualAccountResponse with NUBAN and bank details
        """
        body = {
            "accountRef": account_ref,
            "accountName": account_name,
        }
        if amount is not None:
            body["amount"] = amount

        response = await self._post(
            "/accounts/virtual",
            body,
            is_idempotent=True,  # accountRef provides idempotency
            request_id=request_id,
        )

        result = self._parse_response(response, NombaVirtualAccountResponse)

        logger.info(
            "nomba_virtual_account_created",
            request_id=request_id,
            account_ref=account_ref,
            nuban=result.account_number,
        )

        return result

    async def get_virtual_account(
        self,
        account_id: str,
        *,
        request_id: str | None = None,
    ) -> NombaVirtualAccountResponse:
        """
        Get virtual account details by Nomba account ID.

        GET /accounts/virtual/{accountId}

        Args:
            account_id: Nomba's account ID (not the NUBAN)
            request_id: Optional request ID for tracing

        Returns:
            NombaVirtualAccountResponse with account details
        """
        response = await self._get(
            f"/accounts/virtual/{account_id}",
            request_id=request_id,
        )

        return self._parse_response(response, NombaVirtualAccountResponse)

    async def get_virtual_account_by_ref(
        self,
        account_ref: str,
        *,
        request_id: str | None = None,
    ) -> NombaVirtualAccountResponse:
        """
        Get virtual account by our reference.

        GET /accounts/virtual/ref/{accountRef}

        Args:
            account_ref: Our stable reference used in create
            request_id: Optional request ID for tracing

        Returns:
            NombaVirtualAccountResponse with account details
        """
        response = await self._get(
            f"/accounts/virtual/ref/{account_ref}",
            request_id=request_id,
        )

        return self._parse_response(response, NombaVirtualAccountResponse)

    async def list_virtual_accounts(
        self,
        page: int = 1,
        page_size: int = 20,
        *,
        request_id: str | None = None,
    ) -> list[NombaVirtualAccountResponse]:
        """
        List virtual accounts for the parent account.

        GET /accounts/virtual

        Args:
            page: Page number (1-indexed)
            page_size: Number of results per page
            request_id: Optional request ID for tracing

        Returns:
            List of virtual accounts
        """
        params = {"page": page, "pageSize": page_size}

        response = await self._get(
            "/accounts/virtual",
            params=params,
            request_id=request_id,
        )

        data = response.json()

        # Handle paginated response
        if isinstance(data, dict) and "data" in data:
            inner = data["data"]
            if isinstance(inner, list):
                return [NombaVirtualAccountResponse.model_validate(item) for item in inner]
            return [NombaVirtualAccountResponse.model_validate(inner)]

        # Handle non-wrapped response
        if isinstance(data, list):
            return [NombaVirtualAccountResponse.model_validate(item) for item in data]

        return []


# Singleton instance
_nomba_virtual_accounts_client: NombaVirtualAccountsClient | None = None


def get_nomba_virtual_accounts_client() -> NombaVirtualAccountsClient:
    """Get the virtual accounts client singleton."""
    global _nomba_virtual_accounts_client
    if _nomba_virtual_accounts_client is None:
        _nomba_virtual_accounts_client = NombaVirtualAccountsClient()
    return _nomba_virtual_accounts_client
