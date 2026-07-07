"""Nomba transfers API client for bank transfers and settlements.
"""
from __future__ import annotations

import structlog

from app.integrations.nomba.base_client import NombaResourceClient
from app.integrations.nomba.types import NombaBankLookupResponse, NombaTransferResponse

logger = structlog.get_logger(__name__)


class NombaTransfersClient(NombaResourceClient):
    """
    Client for Nomba transfers API.

    Used for settlements - transferring funds to merchant bank accounts.

    IMPORTANT: Always call lookup_bank_account() before initiate_bank_transfer()
    to verify the account details.

    Rate limit: 1 transfer per second per business.
    """

    async def lookup_bank_account(
        self,
        bank_code: str,
        account_number: str,
        *,
        request_id: str | None = None,
    ) -> NombaBankLookupResponse:
        """
        Resolve bank account to account name BEFORE transfer.

        POST /v1/transfers/bank/lookup
        Body: bankCode, accountNumber

        This is MANDATORY before initiating any transfer.

        Args:
            bank_code: Nigerian bank code (e.g., "044" for Access Bank)
            account_number: 10-digit NUBAN account number
            request_id: Optional request ID for tracing

        Returns:
            NombaBankLookupResponse with account_name and account_number

        Raises:
            NombaNotFoundError: If account cannot be resolved
            NombaValidationError: If bank_code or account_number invalid
        """
        body = {
            "bankCode": bank_code,
            "accountNumber": account_number,
        }

        response = await self._post(
            "/v1/transfers/bank/lookup",
            body,
            is_idempotent=True,
            request_id=request_id,
        )

        result = self._parse_response(response, NombaBankLookupResponse)

        logger.info(
            "nomba_bank_lookup_completed",
            request_id=request_id,
            bank_code=bank_code,
            account_name=result.account_name,
        )

        return result

    async def initiate_bank_transfer(
        self,
        amount_kobo: int,
        bank_code: str,
        account_number: str,
        account_name: str,
        narration: str,
        merchant_tx_ref: str,
        sender_name: str = "OffiMesh",
        *,
        request_id: str | None = None,
    ) -> NombaTransferResponse:
        """
        Initiate a bank transfer for settlement.

        POST /v2/transfers/bank
        Body: amount (Naira string), bankCode, accountNumber, accountName,
              senderName, narration, merchantTxRef

        The merchantTxRef is used as a unique idempotency key. If the same
        reference is used again, Nomba will return the original transfer.

        NOTE: Nomba amounts are in Naira (not kobo). The amount_kobo input
        is divided by 100 to convert from kobo to Naira.

        Args:
            amount_kobo: Amount in kobo (divided by 100 before sending)
            bank_code: Nigerian bank code
            account_number: 10-digit NUBAN
            account_name: Verified account name from lookup
            narration: Transfer description
            merchant_tx_ref: Unique reference (our tx_id)
            sender_name: Name shown to recipient (default "OffiMesh")
            request_id: Optional request ID for tracing

        Returns:
            NombaTransferResponse with transfer details

        Raises:
            NombaValidationError: If parameters invalid
            NombaConflictError: If duplicate reference
            NombaTransferError: If transfer fails
        """
        amount_naira = round(amount_kobo / 100, 2)

        body = {
            "amount": str(amount_naira),
            "bankCode": bank_code,
            "accountNumber": account_number,
            "accountName": account_name,
            "senderName": sender_name,
            "narration": narration,
            "merchantTxRef": merchant_tx_ref,
        }

        response = await self._post(
            "/v2/transfers/bank",
            body,
            is_idempotent=True,
            request_id=request_id,
        )

        result = self._parse_response(response, NombaTransferResponse)

        logger.info(
            "nomba_transfer_initiated",
            request_id=request_id,
            merchant_tx_ref=merchant_tx_ref,
            amount_naira=amount_naira,
            transfer_id=result.transfer_id,
            status=result.status,
        )

        return result

    async def get_transfer_status(
        self,
        merchant_tx_ref: str,
        *,
        request_id: str | None = None,
    ) -> NombaTransferResponse | None:
        """
        Check the status of a transfer using our merchant reference.

        Uses the transaction lookup endpoint since Nomba does not expose
        a dedicated transfer status endpoint.

        GET /v1/transactions/accounts/single?merchantTxRef={merchantTxRef}

        Args:
            merchant_tx_ref: Our unique reference used in initiate_bank_transfer
            request_id: Optional request ID for tracing

        Returns:
            NombaTransferResponse with current status, or None if not found
        """
        try:
            response = await self._get(
                "/v1/transactions/accounts/single",
                params={"merchantTxRef": merchant_tx_ref},
                request_id=request_id,
            )
            return self._parse_response(response, NombaTransferResponse)
        except Exception:
            return None

    async def get_transfer_by_id(
        self,
        transfer_id: str,
        *,
        request_id: str | None = None,
    ) -> NombaTransferResponse | None:
        """
        Get transfer by Nomba's transfer/transaction ID.

        Uses the transaction lookup endpoint.

        GET /v1/transactions/accounts/single?transactionRef={transferId}

        Args:
            transfer_id: Nomba's transfer ID from initiate_bank_transfer
            request_id: Optional request ID for tracing

        Returns:
            NombaTransferResponse with transfer details, or None if not found
        """
        try:
            response = await self._get(
                "/v1/transactions/accounts/single",
                params={"transactionRef": transfer_id},
                request_id=request_id,
            )
            return self._parse_response(response, NombaTransferResponse)
        except Exception:
            return None


# Singleton instance
_nomba_transfers_client: NombaTransfersClient | None = None


def get_nomba_transfers_client() -> NombaTransfersClient:
    """Get the transfers client singleton."""
    global _nomba_transfers_client
    if _nomba_transfers_client is None:
        _nomba_transfers_client = NombaTransfersClient()
    return _nomba_transfers_client
