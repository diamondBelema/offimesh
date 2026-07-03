"""Nomba virtual accounts API client."""
from __future__ import annotations

import structlog
from typing import TYPE_CHECKING

import httpx

from app.core.config import settings
from app.core.exceptions import NombaError
from app.integrations.nomba.auth import get_nomba_auth_client
from app.integrations.nomba.types import NombaVirtualAccountResponse

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)


class NombaVirtualAccountsClient:
    """
    Client for Nomba virtual accounts API.

    Used for wallet funding - creates a dedicated NUBAN for customers
    to transfer funds into their OffiMesh wallet.
    """

    def __init__(self) -> None:
        self.base_url = settings.nomba_base_url
        self.account_id = settings.nomba_account_id
        self._http_client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=30.0,
            )
        return self._http_client

    async def _get_headers(self) -> dict[str, str]:
        """Get headers with valid access token."""
        auth_client = get_nomba_auth_client()
        token = await auth_client.get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "accountId": self.account_id,
            "Content-Type": "application/json",
        }

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def create_virtual_account(
        self,
        account_ref: str,
        account_name: str,
        amount: int | None = None,
    ) -> NombaVirtualAccountResponse:
        """
        Create a virtual account for wallet funding.

        POST /accounts/virtual
        Body: accountRef, accountName, amount (optional)
        Returns a dedicated NUBAN for the customer.
        """
        client = await self._get_client()
        headers = await self._get_headers()

        body = {
            "accountRef": account_ref,
            "accountName": account_name,
        }
        if amount:
            body["amount"] = amount

        try:
            response = await client.post(
                "/accounts/virtual",
                headers=headers,
                json=body,
            )

            if response.status_code not in (200, 201):
                logger.error(
                    "nomba_virtual_account_create_failed",
                    status=response.status_code,
                    body=response.text[:500],
                )
                raise NombaError(
                    f"Failed to create virtual account: {response.status_code}"
                )

            data = response.json()

            # Nomba wraps response in "data" key
            if "data" in data:
                account_data = data["data"]
            else:
                account_data = data

            logger.info(
                "nomba_virtual_account_created",
                account_ref=account_ref,
            )

            return NombaVirtualAccountResponse(**account_data)

        except httpx.HTTPError as e:
            logger.error("nomba_virtual_account_http_error", error=str(e))
            raise NombaError(f"HTTP error: {e}") from e

    async def get_virtual_account(self, account_id: str) -> NombaVirtualAccountResponse:
        """
        Get virtual account details.

        GET /accounts/virtual/{accountId}
        """
        client = await self._get_client()
        headers = await self._get_headers()

        try:
            response = await client.get(
                f"/accounts/virtual/{account_id}",
                headers=headers,
            )

            if response.status_code != 200:
                raise NombaError(
                    f"Failed to get virtual account: {response.status_code}"
                )

            data = response.json()

            if "data" in data:
                account_data = data["data"]
            else:
                account_data = data

            return NombaVirtualAccountResponse(**account_data)

        except httpx.HTTPError as e:
            raise NombaError(f"HTTP error: {e}") from e


# Singleton instance
_nomba_virtual_accounts_client: NombaVirtualAccountsClient | None = None


def get_nomba_virtual_accounts_client() -> NombaVirtualAccountsClient:
    """Get the virtual accounts client singleton."""
    global _nomba_virtual_accounts_client
    if _nomba_virtual_accounts_client is None:
        _nomba_virtual_accounts_client = NombaVirtualAccountsClient()
    return _nomba_virtual_accounts_client
