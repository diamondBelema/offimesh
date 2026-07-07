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

    Rate limit: 5 bank transfers to the same recipient per minute (per docs'
    rate limit notice on this endpoint) -- not "1/sec/business" as previously
    stated here; that number wasn't found in the docs I've verified.

    NOTE ON BASE URL: real Nomba endpoints are called as
    https://api.nomba.com/v1/... or https://api.nomba.com/v2/... -- the
    version lives in the PATH, not the base URL. These paths already
    include their version prefix, which only works correctly if
    settings.nomba_base_url is bare (e.g. "https://api.nomba.com", no
    "/v1" suffix). If other Nomba clients in this codebase assume the
    base URL already contains "/v1" and use bare paths, that's the
    inconsistency to fix -- not this file.
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

        Real response only contains accountNumber/accountName -- bank_code
        is attached here from the input since Nomba doesn't echo it back.

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
        # Nomba doesn't echo the bank_code back -- attach what we queried with.
        result.bank_code = bank_code

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
        Body: amount (Naira, NUMBER not string), bankCode, accountNumber,
              accountName, senderName, narration, merchantTxRef

        The merchantTxRef is used as a unique idempotency key. If the same
        reference is used again, Nomba will return the original transfer.

        NOTE: Nomba amounts are in Naira (not kobo), sent as a JSON
        number -- the docs' own examples send "amount": 3500, not "3500".

        The response only contains { id, status } -- NOT amount, fee,
        reference, or created_at. Those fields are attached here from
        what we already know (we sent them), rather than expected from
        Nomba. transfer_id (the returned "id") is what you must persist
        to requery status later -- there is no documented way to requery
        purely by merchant_tx_ref.

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
            NombaTransferResponse with transfer_id and status

        Raises:
            NombaValidationError: If parameters invalid
            NombaConflictError: If duplicate reference
        """
        amount_naira = round(amount_kobo / 100, 2)

        body = {
            "amount": amount_naira,  # JSON number, not a string
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
        # Attach what Nomba doesn't echo back.
        result.reference = merchant_tx_ref
        result.amount = amount_kobo

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
        transaction_ref: str,
        *,
        request_id: str | None = None,
    ) -> NombaTransferResponse | None:
        """
        Check the status of a transfer using NOMBA'S OWN transfer id.

        GET /v1/transactions/accounts/single?transactionRef={transactionRef}

        IMPORTANT: per the docs, transactionRef must be the "id" value
        Nomba returned from initiate_bank_transfer (e.g.
        "API-TRANSFER-XXX-XXX"), NOT your own merchant_tx_ref. There is
        no documented endpoint to requery purely by merchant_tx_ref --
        persist the returned transfer_id immediately after initiating
        a transfer so you have it available for requery.

        If you initiated the transfer from a SUB-ACCOUNT (via
        /v2/transfers/bank/{subAccountId}), use
        GET /v1/transactions/accounts/{subAccountId}/single instead --
        this method assumes a parent-account-initiated transfer.

        Args:
            transaction_ref: Nomba's transfer id, from a prior
                initiate_bank_transfer() response's transfer_id.
            request_id: Optional request ID for tracing

        Returns:
            NombaTransferResponse with current status, or None if
            genuinely not found (404) -- other errors are NOT swallowed
            here; they propagate so a transient failure isn't mistaken
            for "transfer doesn't exist."
        """
        from app.core.exceptions import NombaNotFoundError

        try:
            response = await self._get(
                "/v1/transactions/accounts/single",
                params={"transactionRef": transaction_ref},
                request_id=request_id,
            )
            return self._parse_response(response, NombaTransferResponse)
        except NombaNotFoundError:
            return None
        
