
from __future__ import annotations

import structlog

import httpx

from app.core.config import settings
from app.core.exceptions import NombaError
from app.integrations.nomba.auth import get_nomba_auth_client

logger = structlog.get_logger(__name__)


class NombaSubAccountsClient:
    """
    Client for Nomba sub-accounts API.

    Used for internal bookkeeping and balance reporting ONLY.
    NOT for virtual account creation or money movement.

    All requests use PARENT NOMBA_ACCOUNT_ID in the header for authentication.
    We never use the sub-account's own ID for auth.
    """

    def __init__(self) -> None:
        self.base_url = settings.nomba_base_url
        self.account_id = settings.nomba_account_id  # ALWAYS parent account ID for auth
        self._http_client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(30.0),
                limits=httpx.Limits(
                    max_connections=100,
                    max_keepalive_connections=20,
                ),
            )
        return self._http_client

    async def _get_headers(self) -> dict[str, str]:
        """
        Get headers with valid access token.

        IMPORTANT: Uses PARENT account ID for authentication, never sub-account ID.
        """
        auth_client = get_nomba_auth_client()
        token = await auth_client.get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "accountId": self.account_id,  # Parent account ID
            "Content-Type": "application/json",
        }

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def create_sub_account(
        self,
        account_name: str,
        account_ref: str,
    ) -> dict:
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

        Returns:
            dict with sub-account details including the Nomba-generated ID
        """
        client = await self._get_client()
        headers = await self._get_headers()

        body = {
            "accountName": account_name,
            "accountRef": account_ref,
        }

        try:
            response = await client.post(
                "/accounts/sub-accounts",
                headers=headers,
                json=body,
            )

            if response.status_code not in (200, 201):
                error_body = response.text[:500]
                logger.error(
                    "nomba_sub_account_create_failed",
                    status=response.status_code,
                    body=error_body,
                )
                raise NombaError(
                    f"Failed to create sub-account: {response.status_code} - {error_body}"
                )

            data = response.json()

            if "data" in data:
                result = data["data"]
            else:
                result = data

            logger.info(
                "nomba_sub_account_created",
                account_ref=account_ref,
                account_name=account_name,
            )

            return result

        except httpx.HTTPError as e:
            logger.error("nomba_sub_account_http_error", error=str(e))
            raise NombaError(f"HTTP error creating sub-account: {e}") from e

    async def list_sub_accounts(self) -> list[dict]:
        """
        List all sub-accounts under the parent account.

        GET /accounts/sub-accounts

        Returns:
            List of sub-account dictionaries
        """
        client = await self._get_client()
        headers = await self._get_headers()

        try:
            response = await client.get(
                "/accounts/sub-accounts",
                headers=headers,
            )

            if response.status_code != 200:
                raise NombaError(
                    f"Failed to list sub-accounts: {response.status_code}"
                )

            data = response.json()

            if "data" in data:
                return data["data"] if isinstance(data["data"], list) else [data["data"]]

            return data if isinstance(data, list) else [data]

        except httpx.HTTPError as e:
            logger.error("nomba_list_sub_accounts_http_error", error=str(e))
            raise NombaError(f"HTTP error listing sub-accounts: {e}") from e

    async def get_sub_account_balance(self, sub_account_id: str) -> dict:
        """
        Get balance of a specific sub-account.

        GET /accounts/sub-accounts/{id}/balance

        This is the ONLY supported sub-account endpoint for reading data.
        There is NO documented endpoint for transfers between sub-accounts
        or from sub-accounts to external accounts.

        Args:
            sub_account_id: The Nomba-generated sub-account ID

        Returns:
            dict with balance information
        """
        client = await self._get_client()
        headers = await self._get_headers()

        try:
            response = await client.get(
                f"/accounts/sub-accounts/{sub_account_id}/balance",
                headers=headers,
            )

            if response.status_code == 401:
                logger.warning(
                    "nomba_sub_account_balance_401",
                    sub_account_id=sub_account_id,
                    note="This may indicate sub-account visibility issue - see module docstring"
                )
                raise NombaError(
                    f"Unauthorized to access sub-account balance. "
                    f"This is a known Nomba limitation for sub-account-scoped resources."
                )

            if response.status_code != 200:
                raise NombaError(
                    f"Failed to get sub-account balance: {response.status_code}"
                )

            data = response.json()

            if "data" in data:
                result = data["data"]
            else:
                result = data

            logger.info(
                "nomba_sub_account_balance_retrieved",
                sub_account_id=sub_account_id,
            )

            return result

        except httpx.HTTPError as e:
            logger.error("nomba_sub_account_balance_http_error", error=str(e))
            raise NombaError(f"HTTP error getting sub-account balance: {e}") from e


# Singleton instance
_nomba_sub_accounts_client: NombaSubAccountsClient | None = None


def get_nomba_sub_accounts_client() -> NombaSubAccountsClient:
    """Get the sub-accounts client singleton."""
    global _nomba_sub_accounts_client
    if _nomba_sub_accounts_client is None:
        _nomba_sub_accounts_client = NombaSubAccountsClient()
    return _nomba_sub_accounts_client
