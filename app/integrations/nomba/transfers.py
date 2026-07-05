"""Nomba transfers API client for bank transfers and settlements.

Refactored to inherit from NombaResourceClient, providing:
- Bank account lookup (required before transfer)
- Bank transfer initiation
- Transfer status queries
- Production-grade error handling and retries
"""
from __future__ import annotations

import structlog

from app.integrations.nomba.base_client import NombaResourceClient
from app.integrations.nomba.types import NombaTransferResponse, NombaBankLookupResponse

logger = structlog.get_logger(__name__)


class NombaTransfersClient(NombaResourceClient):
    """
    Client for Nomba transfers API.

    Used for settlements - transferring funds to merchant bank accounts.

    IMPORTANT: Always call lookup_bank_account() before initiate_bank_transfer()
    to verify the account details. This is mandatory per Nomba's documentation.
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

        POST /transfers/bank/lookup
        Body: bankCode, accountNumber

        This is MANDATORY before initiating any transfer.

        Args:
            bank_code: Nigerian bank code (e.g., "044" for Access Bank)
            account_number: 10-digit NUBAN account number
            request_id: Optional request ID for tracing

        Returns:
            NombaBankLookupResponse with account_name, bank_name, etc.

        Raises:
            NombaNotFoundError: If account cannot be resolved
            NombaValidationError: If bank_code or account_number invalid
        """
        body = {
            "bankCode": bank_code,
            "accountNumber": account_number,
        }

        response = await self._post(
            "/transfers/bank/lookup",
            body,
            is_idempotent=True,  # Lookup is safe to retry
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

        POST /transfers/bank
        Body: amount, bankCode, accountNumber, accountName, senderName, narration, merchantTxRef

        The merchantTxRef is used as a unique idempotency key. If the same
        reference is used again, Nomba will return the original transfer.

        Args:
            amount_kobo: Amount in kobo (1/100 of Naira)
            bank_code: Nigerian bank code
            account_number: 10-digit NUBAN
            account_name: Verified account name from lookup
            narration: Transfer description
            merchant_tx_ref: Unique reference (our tx_id)
            sender_name: Name shown to recipient
            request_id: Optional request ID for tracing

        Returns:
            NombaTransferResponse with transfer details

        Raises:
            NombaValidationError: If parameters invalid
            NombaConflictError: If duplicate reference
            NombaTransferError: If transfer fails
        """
        body = {
            "amount": amount_kobo,
            "bankCode": bank_code,
            "accountNumber": account_number,
            "accountName": account_name,
            "senderName": sender_name,
            "narration": narration,
            "merchantTxRef": merchant_tx_ref,
        }

        response = await self._post(
            "/transfers/bank",
            body,
            is_idempotent=True,  # merchantTxRef provides idempotency
            request_id=request_id,
        )

        result = self._parse_response(response, NombaTransferResponse)

        logger.info(
            "nomba_transfer_initiated",
            request_id=request_id,
            merchant_tx_ref=merchant_tx_ref,
            amount_kobo=amount_kobo,
            transfer_id=result.transfer_id,
        )

        return result

    async def get_transfer_status(
        self,
        merchant_tx_ref: str,
        *,
        request_id: str | None = None,
    ) -> NombaTransferResponse:
        """
        Check the status of a transfer using our reference.

        GET /transfers/{merchantTxRef}

        Args:
            merchant_tx_ref: Our unique reference used in initiate
            request_id: Optional request ID for tracing

        Returns:
            NombaTransferResponse with current status
        """
        response = await self._get(
            f"/transfers/{merchant_tx_ref}",
            request_id=request_id,
        )

        return self._parse_response(response, NombaTransferResponse)

    async def get_transfer_by_id(
        self,
        transfer_id: str,
        *,
        request_id: str | None = None,
    ) -> NombaTransferResponse:
        """
        Get transfer by Nomba's transfer ID.

        GET /transfers/id/{transferId}

        Args:
            transfer_id: Nomba's transfer ID from initiate_bank_transfer
            request_id: Optional request ID for tracing

        Returns:
            NombaTransferResponse with transfer details
        """
        response = await self._get(
            f"/transfers/id/{transfer_id}",
            request_id=request_id,
        )

        return self._parse_response(response, NombaTransferResponse)


# Singleton instance
_nomba_transfers_client: NombaTransfersClient | None = None


def get_nomba_transfers_client() -> NombaTransfersClient:
    """Get the transfers client singleton."""
    global _nomba_transfers_client
    if _nomba_transfers_client is None:
        _nomba_transfers_client = NombaTransfersClient()
    return _nomba_transfers_client
