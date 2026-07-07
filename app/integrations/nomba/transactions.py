"""Nomba transactions API client for transaction queries and reconciliation.
"""
from __future__ import annotations

import structlog
from datetime import date

from app.integrations.nomba.base_client import NombaResourceClient
from app.integrations.nomba.types import NombaTransactionResponse

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
    ) -> NombaTransactionResponse | None:
        """
        Get a transaction by Nomba's transaction ID.

        GET /v1/transactions/accounts/single?transactionRef={transactionId}

        Args:
            transaction_id: Nomba's transaction ID
            request_id: Optional request ID for tracing

        Returns:
            NombaTransactionResponse or None if not found
        """
        try:
            response = await self._get(
                "/v1/transactions/accounts/single",
                params={"transactionRef": transaction_id},
                request_id=request_id,
            )
            return self._parse_response(response, NombaTransactionResponse)
        except Exception:
            return None

    async def get_transaction_by_reference(
        self,
        reference: str,
        *,
        request_id: str | None = None,
    ) -> NombaTransactionResponse | None:
        """
        Get a transaction by our reference (merchantTxRef).

        GET /v1/transactions/accounts/single?merchantTxRef={reference}

        Args:
            reference: Our unique reference (merchantTxRef)
            request_id: Optional request ID for tracing

        Returns:
            NombaTransactionResponse or None if not found
        """
        try:
            response = await self._get(
                "/v1/transactions/accounts/single",
                params={"merchantTxRef": reference},
                request_id=request_id,
            )
            return self._parse_response(response, NombaTransactionResponse)
        except Exception:
            return None

    async def list_transactions(
        self,
        limit: int = 100,
        cursor: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        *,
        request_id: str | None = None,
    ) -> tuple[list[NombaTransactionResponse], str | None]:
        """
        List transactions with optional date filtering.

        GET /v1/transactions/accounts
        Query params: limit, cursor, dateFrom, dateTo

        Used for nightly reconciliation. Returns a tuple of
        (results, next_cursor). Pass next_cursor to subsequent
        calls to paginate.

        Args:
            limit: Page size (max 100)
            cursor: Pagination cursor from a previous call
            date_from: Start date filter (UTC)
            date_to: End date filter (UTC)
            request_id: Optional request ID for tracing

        Returns:
            Tuple of (list of NombaTransactionResponse, next_cursor or None)
        """
        params: dict = {"limit": str(min(limit, 100))}
        if cursor:
            params["cursor"] = cursor
        if date_from:
            params["dateFrom"] = date_from.strftime("%Y-%m-%dT00:00:00.000Z")
        if date_to:
            params["dateTo"] = date_to.strftime("%Y-%m-%dT23:59:59.000Z")

        response = await self._get(
            "/v1/transactions/accounts",
            params=params,
            request_id=request_id,
        )

        body = response.json()
        wrapper = body.get("data", body) if isinstance(body, dict) else body
        raw_results = wrapper.get("results", []) if isinstance(wrapper, dict) else []
        next_cursor = wrapper.get("cursor") or None if isinstance(wrapper, dict) else None

        transactions = [
            NombaTransactionResponse.model_validate(item)
            for item in raw_results
        ]

        return transactions, next_cursor

    async def list_all_transactions_for_period(
        self,
        date_from: date,
        date_to: date,
        *,
        request_id: str | None = None,
    ) -> list[NombaTransactionResponse]:
        """
        Fetch all transactions for a date range, handling cursor pagination.

        Args:
            date_from: Start date
            date_to: End date
            request_id: Optional request ID for tracing

        Returns:
            List of all transactions in the period
        """
        all_transactions: list[NombaTransactionResponse] = []
        cursor: str | None = None

        while True:
            results, cursor = await self.list_transactions(
                limit=100,
                cursor=cursor,
                date_from=date_from,
                date_to=date_to,
                request_id=request_id,
            )

            all_transactions.extend(results)

            if not cursor:
                break

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
