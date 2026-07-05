"""Nomba transactions API client for transaction queries and reconciliation.

Used for:
- Querying transactions by reference or ID
- Listing transactions for reconciliation
- Fetching transaction details for settlement verification

Refactored to inherit from NombaResourceClient for production-grade reliability.
"""
from __future__ import annotations

import structlog
from datetime import date

from app.integrations.nomba.base_client import NombaResourceClient
from app.integrations.nomba.types import NombaTransactionResponse, NombaTransactionListResponse

logger = structlog.get_logger(__name__)


class NombaTransactionsClient(NombaResourceClient):
    """
    Client for Nomba transactions API.

    Used for reconciliation - comparing Nomba's view of transactions
    with our local ledger to catch discrepancies.
    """

    async def get_transaction(
        self,
        transaction_id: str,
        *,
        request_id: str | None = None,
    ) -> NombaTransactionResponse:
        """
        Get a transaction by Nomba's transaction ID.

        GET /transactions/{transactionId}

        Args:
            transaction_id: Nomba's transaction ID
            request_id: Optional request ID for tracing

        Returns:
            NombaTransactionResponse with transaction details
        """
        response = await self._get(
            f"/transactions/{transaction_id}",
            request_id=request_id,
        )

        return self._parse_response(response, NombaTransactionResponse)

    async def get_transaction_by_reference(
        self,
        reference: str,
        *,
        request_id: str | None = None,
    ) -> NombaTransactionResponse | None:
        """
        Get a transaction by our reference (merchantTxRef).

        GET /transactions/{reference}

        Args:
            reference: Our unique reference (merchantTxRef)
            request_id: Optional request ID for tracing

        Returns:
            NombaTransactionResponse or None if not found
        """
        try:
            response = await self._get(
                f"/transactions/{reference}",
                request_id=request_id,
            )
            return self._parse_response(response, NombaTransactionResponse)
        except Exception:
            return None

    async def list_transactions(
        self,
        page: int = 1,
        page_size: int = 100,
        date_from: date | None = None,
        date_to: date | None = None,
        status: str | None = None,
        tx_type: str | None = None,
        *,
        request_id: str | None = None,
    ) -> NombaTransactionListResponse:
        """
        List transactions with optional date filtering.

        GET /transactions

        Used for nightly reconciliation to compare Nomba transactions
        against our local ledger.

        Args:
            page: Page number (1-indexed)
            page_size: Number of results per page (max 100)
            date_from: Start date filter
            date_to: End date filter
            status: Filter by transaction status
            tx_type: Filter by transaction type
            request_id: Optional request ID for tracing

        Returns:
            NombaTransactionListResponse with paginated results
        """
        params: dict = {"page": page, "pageSize": min(page_size, 100)}

        if date_from:
            params["dateFrom"] = date_from.isoformat()
        if date_to:
            params["dateTo"] = date_to.isoformat()
        if status:
            params["status"] = status
        if tx_type:
            params["type"] = tx_type

        response = await self._get(
            "/transactions",
            params=params,
            request_id=request_id,
        )

        data = response.json()

        # Handle wrapped response
        if isinstance(data, dict) and "data" in data:
            inner = data["data"]
            if isinstance(inner, dict) and "transactions" in inner:
                transactions = [
                    NombaTransactionResponse.model_validate(item)
                    for item in inner.get("transactions", [])
                ]
                return NombaTransactionListResponse(
                    transactions=transactions,
                    total=inner.get("total"),
                    page=inner.get("page", page),
                    page_size=inner.get("pageSize", page_size),
                )
            elif isinstance(inner, list):
                transactions = [NombaTransactionResponse.model_validate(item) for item in inner]
                return NombaTransactionListResponse(transactions=transactions)

        # Handle non-wrapped response
        if isinstance(data, dict) and "transactions" in data:
            transactions = [NombaTransactionResponse.model_validate(item) for item in data["transactions"]]
            return NombaTransactionListResponse(
                transactions=transactions,
                total=data.get("total"),
                page=data.get("page", page),
                page_size=data.get("pageSize", page_size),
            )

        if isinstance(data, list):
            transactions = [NombaTransactionResponse.model_validate(item) for item in data]
            return NombaTransactionListResponse(transactions=transactions)

        return NombaTransactionListResponse(transactions=[])

    async def list_all_transactions_for_period(
        self,
        date_from: date,
        date_to: date,
        *,
        request_id: str | None = None,
    ) -> list[NombaTransactionResponse]:
        """
        Fetch all transactions for a date range, handling pagination.

        Convenience method that handles pagination automatically.

        Args:
            date_from: Start date
            date_to: End date
            request_id: Optional request ID for tracing

        Returns:
            List of all transactions in the period
        """
        all_transactions: list[NombaTransactionResponse] = []
        page = 1
        page_size = 100

        while True:
            result = await self.list_transactions(
                page=page,
                page_size=page_size,
                date_from=date_from,
                date_to=date_to,
                request_id=request_id,
            )

            all_transactions.extend(result.transactions)

            # Check if we need to fetch more pages
            if result.total is None or len(all_transactions) >= result.total:
                break

            page += 1

        logger.info(
            "nomba_transactions_fetched",
            request_id=request_id,
            date_from=date_from.isoformat(),
            date_to=date_to.isoformat(),
            total=len(all_transactions),
        )

        return all_transactions


# Singleton instance
_nomba_transactions_client: NombaTransactionsClient | None = None


def get_nomba_transactions_client() -> NombaTransactionsClient:
    """Get the transactions client singleton."""
    global _nomba_transactions_client
    if _nomba_transactions_client is None:
        _nomba_transactions_client = NombaTransactionsClient()
    return _nomba_transactions_client
