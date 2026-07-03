"""Nomba transfers API client for settlements."""
from __future__ import annotations

import structlog

import httpx

from app.core.config import settings
from app.core.exceptions import NombaError, NombaRateLimitError, NombaTransferError
from app.integrations.nomba.auth import get_nomba_auth_client
from app.integrations.nomba.types import NombaTransferResponse, NombiTransferLookupResponse

logger = structlog.get_logger(__name__)


class CircuitBreaker:
    """
    Circuit breaker for Nomba API calls.

    Opens after 5 failures in 60 seconds, resets after 30 seconds.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout_seconds: int = 30,
        window_seconds: int = 60,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.reset_timeout_seconds = reset_timeout_seconds
        self.window_seconds = window_seconds
        self.failures: list[float] = []
        self.last_failure_time: float | None = None
        self.state: str = "closed"  # closed, open, half-open

    def record_failure(self) -> None:
        """Record a failure and check if circuit should open."""
        import time
        now = time.time()

        # Remove old failures outside window
        self.failures = [f for f in self.failures if now - f < self.window_seconds]

        # Add new failure
        self.failures.append(now)
        self.last_failure_time = now

        # Check if threshold exceeded
        if len(self.failures) >= self.failure_threshold:
            self.state = "open"
            logger.warning("nomba_circuit_opened", failure_count=len(self.failures))

    def record_success(self) -> None:
        """Record a success and reset circuit."""
        self.failures = []
        self.state = "closed"

    def can_execute(self) -> bool:
        """Check if request can proceed."""
        import time

        if self.state == "closed":
            return True

        if self.state == "open":
            # Check if we should try half-open
            if self.last_failure_time:
                elapsed = time.time() - self.last_failure_time
                if elapsed >= self.reset_timeout_seconds:
                    self.state = "half-open"
                    logger.info("nomba_circuit_half_open")
                    return True
            return False

        # half-open - allow one test request
        return True


class NombaTransfersClient:
    """
    Client for Nomba transfers API.

    Used for settlements - transferring funds to merchant bank accounts.
    """

    def __init__(self) -> None:
        self.base_url = settings.nomba_base_url
        self.account_id = settings.nomba_account_id
        self._http_client: httpx.AsyncClient | None = None
        self.circuit_breaker = CircuitBreaker()

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

    async def lookup_bank_account(
        self,
        bank_code: str,
        account_number: str,
    ) -> NombiTransferLookupResponse:
        """
        Resolve bank account to name BEFORE transfer.

        POST /transfers/bank/lookup
        Body: bankCode, accountNumber

        MUST always be called before /transfers/bank.
        """
        if not self.circuit_breaker.can_execute():
            raise NombaError("Circuit breaker open")

        client = await self._get_client()
        headers = await self._get_headers()

        body = {
            "bankCode": bank_code,
            "accountNumber": account_number,
        }

        try:
            response = await client.post(
                "/transfers/bank/lookup",
                headers=headers,
                json=body,
            )

            if response.status_code != 200:
                self.circuit_breaker.record_failure()
                raise NombaTransferError(
                    f"Bank lookup failed: {response.status_code}",
                )

            data = response.json()

            if "data" in data:
                lookup_data = data["data"]
            else:
                lookup_data = data

            self.circuit_breaker.record_success()

            return NombiTransferLookupResponse(**lookup_data)

        except httpx.HTTPError as e:
            self.circuit_breaker.record_failure()
            raise NombaTransferError(f"HTTP error: {e}") from e

    async def initiate_bank_transfer(
        self,
        amount_kobo: int,
        bank_code: str,
        account_number: str,
        account_name: str,
        narration: str,
        merchant_tx_ref: str,
        sender_name: str = "OffiMesh",
    ) -> NombaTransferResponse:
        """
        Initiate bank transfer for settlement.

        POST /transfers/bank
        Body: amount, bankCode, accountNumber, accountName, senderName, narration, merchantTxRef

        merchantTxRef is our unique idempotency key.
        """
        if not self.circuit_breaker.can_execute():
            raise NombaError("Circuit breaker open")

        client = await self._get_client()
        headers = await self._get_headers()

        body = {
            "amount": amount_kobo,
            "bankCode": bank_code,
            "accountNumber": account_number,
            "accountName": account_name,
            "senderName": sender_name,
            "narration": narration,
            "merchantTxRef": merchant_tx_ref,
        }

        try:
            response = await client.post(
                "/transfers/bank",
                headers=headers,
                json=body,
            )

            if response.status_code == 429:
                self.circuit_breaker.record_failure()
                raise NombaRateLimitError()

            if response.status_code not in (200, 201):
                self.circuit_breaker.record_failure()
                error_body = response.text[:500]
                logger.error(
                    "nomba_transfer_failed",
                    status=response.status_code,
                    body=error_body,
                )
                raise NombaTransferError(
                    f"Transfer failed: {response.status_code}",
                )

            data = response.json()

            if "data" in data:
                transfer_data = data["data"]
            else:
                transfer_data = data

            self.circuit_breaker.record_success()

            logger.info(
                "nomba_transfer_initiated",
                merchant_tx_ref=merchant_tx_ref,
                amount=amount_kobo,
            )

            return NombaTransferResponse(**transfer_data)

        except NombaRateLimitError:
            raise
        except NombaTransferError:
            raise
        except httpx.HTTPError as e:
            self.circuit_breaker.record_failure()
            raise NombaTransferError(f"HTTP error: {e}") from e

    async def get_transfer_status(self, merchant_tx_ref: str) -> NombaTransferResponse:
        """
        Check transfer status using our reference.

        GET /transfers/{merchantTxRef}
        """
        if not self.circuit_breaker.can_execute():
            raise NombaError("Circuit breaker open")

        client = await self._get_client()
        headers = await self._get_headers()

        try:
            response = await client.get(
                f"/transfers/{merchant_tx_ref}",
                headers=headers,
            )

            if response.status_code != 200:
                raise NombaError(
                    f"Failed to get transfer status: {response.status_code}"
                )

            data = response.json()

            if "data" in data:
                transfer_data = data["data"]
            else:
                transfer_data = data

            return NombaTransferResponse(**transfer_data)

        except httpx.HTTPError as e:
            raise NombaError(f"HTTP error: {e}") from e


# Singleton instance
_nomba_transfers_client: NombaTransfersClient | None = None


def get_nomba_transfers_client() -> NombaTransfersClient:
    """Get the transfers client singleton."""
    global _nomba_transfers_client
    if _nomba_transfers_client is None:
        _nomba_transfers_client = NombaTransfersClient()
    return _nomba_transfers_client
