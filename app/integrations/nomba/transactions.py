"""Nomba transactions API client for reconciliation."""
from __future__ import annotations

import structlog
from datetime import date, datetime

import httpx

from app.core.config import settings
from app.core.exceptions import NombaError
from app.integrations.nomba.auth import get_nomba_auth_client
from app.integrations.nomba.types import NombaTransactionResponse

logger = structlog.get_logger(__name__)


class NombaTransactionsClient:
    """
    Client for Nomba transactions API.

    Used for nightly reconciliation - diffing our ledger against Nomba's records.
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
                timeout=60.0,  # Longer timeout for bulk fetches
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

    async def list_transactions(
        self,
        date_from: date | None = None,
        date_to: date | None = None,
        status: str | None = None,
        tx_type: str | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[list[NombaTransactionResponse], int]:
        """
        List transactions with filters.

        GET /transactions?dateFrom=&dateTo=&status=&type=&page=&pageSize=

        Used for reconciliation - pull all transactions for a date range
        and diff against our ledger by merchantTxRef.
        """
        client = await self._get_client()
        headers = await self._get_headers()

        params: dict[str, str | int] = {
            "page": page,
            "pageSize": page_size,
        }

        if date_from:
            params["dateFrom"] = date_from.isoformat()
        if date_to:
            params["dateTo"] = date_to.isoformat()
        if status:
            params["status"] = status
        if tx_type:
            params["type"] = tx_type

        try:
            response = await client.get(
                "/transactions",
                headers=headers,
                params=params,
            )

            if response.status_code != 200:
                raise NombaError(
                    f"Failed to list transactions: {response.status_code}"
                )

            data = response.json()

            if "data" in data:
                transactions_data = data["data"].get("transactions", [])
                total = data["data"].get("total", 0)
            else:
                transactions_data = data.get("transactions", [])
                total = data.get("total", 0)

            transactions = [
                NombaTransactionResponse(**tx) for tx in transactions_data
            ]

            return transactions, total

        except httpx.HTTPError as e:
            raise NombaError(f"HTTP error: {e}") from e

    async def get_transaction(self, merchant_tx_ref: str) -> NombaTransactionResponse | None:
        """
        Get a single transaction by our reference.

        GET /transactions/{merchantTxRef}
        """
        client = await self._get_client()
        headers = await self._get_headers()

        try:
            response = await client.get(
                f"/transactions/{merchant_tx_ref}",
                headers=headers,
            )

            if response.status_code == 404:
                return None

            if response.status_code != 200:
                raise NombaError(
                    f"Failed to get transaction: {response.status_code}"
                )

            data = response.json()

            if "data" in data:
                tx_data = data["data"]
            else:
                tx_data = data

            return NombaTransactionResponse(**tx_data)

        except httpx.HTTPError as e:
            raise NombaError(f"HTTP error: {e}") from e


# Singleton instance
_nomba_transactions_client: NombaTransactionsClient | None = None


def get_nomba_transactions_client() -> NombaTransactionsClient:
    """Get the transactions client singleton."""
    global _nomba_transactions_client
    if _nomba_transactions_client is None:
        _nomba_transactions_client = NombaTransactionsClient()
    return _nomba_transactions_client
