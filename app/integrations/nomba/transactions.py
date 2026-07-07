from __future__ import annotations

import structlog
from datetime import date

from app.core.exceptions import NombaNotFoundError
from app.integrations.nomba.base_client import NombaResourceClient
from app.integrations.nomba.types import NombaTransactionResponse

logger = structlog.get_logger(__name__)


class NombaTransactionsClient(NombaResourceClient):
    """
    Client for Nomba transactions API.

    Used for reconciliation - comparing Nomba's view of transactions
    with our local ledger to catch discrepancies during offline-sync.

    
    """

    async def get_transaction(
        self,
        transaction_id: str,
        *,
        request_id: str | None = None,
    ) -> NombaTransactionResponse | None:
        """
        Get a single transaction by Nomba's transaction ID/reference.

        GET /v1/transactions/accounts/single?transactionRef={transactionId}

        This is the lightweight single-lookup endpoint (distinct from
        the POST filter endpoint below), confirmed from the transfer
        docs' requery guidance.

        Args:
            transaction_id: Nomba's transaction ID (the "id" field from
                a prior transaction/transfer response)
            request_id: Optional request ID for tracing

        Returns:
            NombaTransactionResponse, or None if genuinely not found
            (404). Other errors (auth, rate limit, timeout) are NOT
            swallowed here -- they propagate so a transient failure
            during sync isn't mistaken for "doesn't exist."
        """
        try:
            response = await self._get(
                "/v1/transactions/accounts/single",
                params={"transactionRef": transaction_id},
                request_id=request_id,
            )
            return self._parse_response(response, NombaTransactionResponse)
        except NombaNotFoundError:
            return None

    async def get_transaction_by_reference(
        self,
        reference: str,
        *,
        request_id: str | None = None,
    ) -> NombaTransactionResponse | None:
        """
        Get a transaction by OUR reference (merchantTxRef).

        POST /v1/transactions/accounts
        Body: { "merchantTxRef": reference }

        merchantTxRef is documented as a filter field on the POST list
        endpoint, not as a query param on the single-lookup GET
        endpoint -- this method uses the filter endpoint with limit=1
        and returns the first match.

        Args:
            reference: Our unique reference (merchantTxRef)
            request_id: Optional request ID for tracing

        Returns:
            NombaTransactionResponse, or None if no match found.
        """
        results, _ = await self.list_transactions(
            limit=1,
            merchant_tx_ref=reference,
            request_id=request_id,
        )
        return results[0] if results else None

    async def list_transactions(
        self,
        limit: int = 100,
        cursor: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        *,
        transaction_ref: str | None = None,
        status: str | None = None,
        source: str | None = None,
        transaction_type: str | None = None,
        terminal_id: str | None = None,
        rrn: str | None = None,
        merchant_tx_ref: str | None = None,
        request_id: str | None = None,
    ) -> tuple[list[NombaTransactionResponse], str | None]:
        """
        Filter transactions, with optional date range and field filters.

        POST /v1/transactions/accounts
        Query params: limit, cursor, dateFrom, dateTo
        Body: transactionRef, status, source, type, terminalId, rrn,
              merchantTxRef (all optional filters)

        This is a POST, not a GET -- the endpoint takes a JSON filter
        body even though pagination/date range are query params.

        Used for nightly reconciliation. Returns a tuple of
        (results, next_cursor). Pass next_cursor to subsequent calls
        to paginate.

        Date format must be yyyy-MM-ddTHH:mm:ss (UTC), with NO
        milliseconds and NO trailing "Z" -- confirmed from the docs'
        own examples ("2023-01-01T00:00:00", "2024-09-30T23:59:59").

        Args:
            limit: Page size (max 100)
            cursor: Pagination cursor from a previous call
            date_from: Start date filter (UTC)
            date_to: End date filter (UTC)
            transaction_ref: Filter by transaction ID/reference
            status: Filter by transaction status
            source: Filter by transaction source (e.g. "pos", "api")
            transaction_type: Filter by transaction type
            terminal_id: Filter by terminal ID
            rrn: Filter by Retrieval Reference Number
            merchant_tx_ref: Filter by our own merchantTxRef
            request_id: Optional request ID for tracing

        Returns:
            Tuple of (list of NombaTransactionResponse, next_cursor or None)
        """
        params: dict[str, str] = {"limit": str(min(limit, 100))}
        if cursor:
            params["cursor"] = cursor
        if date_from:
            params["dateFrom"] = date_from.strftime("%Y-%m-%dT00:00:00")
        if date_to:
            params["dateTo"] = date_to.strftime("%Y-%m-%dT23:59:59")

        body = {
            k: v
            for k, v in {
                "transactionRef": transaction_ref,
                "status": status,
                "source": source,
                "type": transaction_type,
                "terminalId": terminal_id,
                "rrn": rrn,
                "merchantTxRef": merchant_tx_ref,
            }.items()
            if v is not None
        }

        response = await self._post(
            "/v1/transactions/accounts",
            body,
            params=params,
            is_idempotent=True,
            request_id=request_id,
        )

        payload = response.json()
        wrapper = payload.get("data", payload) if isinstance(payload, dict) else payload
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
        
