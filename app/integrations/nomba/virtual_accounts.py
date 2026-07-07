"""Nomba virtual accounts API client for wallet funding.

Virtual accounts are dedicated NUBAN accounts that customers can
transfer funds into to top up their OffiMesh wallet.

IMPORTANT (per hackathon organizer guidance, July 2026):
Virtual accounts MUST be created under our team's sub-account using
POST /v1/accounts/virtual/{subAccountId}, NOT the bare
POST /v1/accounts/virtual. Creating at the parent level means funds
never land in our sub-account and webhook/settlement routing breaks.

The accountId HEADER sent by the base client is always the shared
PARENT hackathon account id (settings.nomba_account_id). Our team's
sub-account id (settings.nomba_subaccount_id) is passed as a PATH
parameter on endpoints that support it. These are two different
values used in two different places -- do not conflate them.
"""
from __future__ import annotations

import structlog

from app.core.config import settings
from app.integrations.nomba.base_client import NombaResourceClient
from app.integrations.nomba.types import NombaVirtualAccountResponse

logger = structlog.get_logger(__name__)

# Nomba enforces these bounds server-side (CreateVirtualAccountRequest
# schema). Failing fast locally avoids a round trip for a guaranteed 400.
_ACCOUNT_REF_MIN_LEN = 16
_ACCOUNT_REF_MAX_LEN = 64
_ACCOUNT_NAME_MIN_LEN = 8
_ACCOUNT_NAME_MAX_LEN = 64


class NombaVirtualAccountsClient(NombaResourceClient):
    """
    Client for Nomba virtual accounts API.

    Used for wallet funding - creates a dedicated NUBAN for customers
    to transfer funds into their OffiMesh wallet.

    All virtual accounts are created under our team's sub-account
    (settings.nomba_subaccount_id) so that inbound payments settle
    into that sub-account and webhooks resolve correctly. See module
    docstring for the accountId header vs sub-account path distinction.
    """

    def __init__(self) -> None:
        super().__init__()
        self.sub_account_id = settings.nomba_subaccount_id
        if not self.sub_account_id:
            logger.warning(
                "nomba_subaccount_id_missing",
                message=(
                    "nomba_subaccount_id is not set. Virtual account creation "
                    "will fail or silently route to the wrong place."
                ),
            )

    @staticmethod
    def _validate_account_ref(account_ref: str) -> None:
        if not (_ACCOUNT_REF_MIN_LEN <= len(account_ref) <= _ACCOUNT_REF_MAX_LEN):
            raise ValueError(
                f"account_ref must be {_ACCOUNT_REF_MIN_LEN}-{_ACCOUNT_REF_MAX_LEN} "
                f"chars (got {len(account_ref)}): {account_ref!r}"
            )

    @staticmethod
    def _validate_account_name(account_name: str) -> None:
        if not (_ACCOUNT_NAME_MIN_LEN <= len(account_name) <= _ACCOUNT_NAME_MAX_LEN):
            raise ValueError(
                f"account_name must be {_ACCOUNT_NAME_MIN_LEN}-{_ACCOUNT_NAME_MAX_LEN} "
                f"chars (got {len(account_name)}): {account_name!r}"
            )

    async def create_virtual_account(
        self,
        account_ref: str,
        account_name: str,
        amount: int | None = None,
        *,
        request_id: str | None = None,
    ) -> NombaVirtualAccountResponse:
        """
        Create a virtual account for wallet funding, scoped to our sub-account.

        POST /accounts/virtual/{subAccountId}
        Body: accountRef, accountName, expectedAmount (optional)

        Returns a dedicated NUBAN that the customer can transfer to.
        Funds sent to it settle into our team sub-account.

        Args:
            account_ref: Our stable reference, 16-64 chars.
            account_name: Name to show on the NUBAN, 8-64 chars.
            amount: Optional expected amount in kobo.
            request_id: Optional request ID for tracing

        Returns:
            NombaVirtualAccountResponse with NUBAN and bank details
        """
        self._validate_account_ref(account_ref)
        self._validate_account_name(account_name)

        body: dict[str, object] = {
            "accountRef": account_ref,
            "accountName": account_name,
        }
        if amount is not None:
            body["expectedAmount"] = round(amount / 100, 2)

        response = await self._post(
            f"/accounts/virtual/{self.sub_account_id}",
            body,
            is_idempotent=True,
            request_id=request_id,
        )

        result = self._parse_response(response, NombaVirtualAccountResponse)

        logger.info(
            "nomba_virtual_account_created",
            request_id=request_id,
            account_ref=account_ref,
            sub_account_id=self.sub_account_id,
            nuban=result.account_number,
        )

        return result

    async def get_virtual_account(
        self,
        identifier: str,
        *,
        request_id: str | None = None,
    ) -> NombaVirtualAccountResponse:
        """
        Fetch a virtual account by its accountRef or NUBAN.

        GET /accounts/virtual/{identifier}

        Args:
            identifier: The accountRef used at creation, or the
                10-digit bank account number (NUBAN).
            request_id: Optional request ID for tracing

        Returns:
            NombaVirtualAccountResponse with account details
        """
        response = await self._get(
            f"/accounts/virtual/{identifier}",
            request_id=request_id,
        )

        return self._parse_response(response, NombaVirtualAccountResponse)

    async def update_virtual_account(
        self,
        identifier: str,
        *,
        new_account_ref: str | None = None,
        account_name: str | None = None,
        callback_url: str | None = None,
        expected_amount: int | None = None,
        request_id: str | None = None,
    ) -> bool:
        """
        Update a virtual account's reference, name, callback URL, or
        expected amount.

        PUT /accounts/virtual/{identifier}

        Args:
            identifier: The accountRef or NUBAN of the account to update.
            new_account_ref: New accountRef to assign.
            account_name: New display name.
            callback_url: New callback URL.
            expected_amount: New expected amount in kobo.
            request_id: Optional request ID for tracing

        Returns:
            True if Nomba confirmed the update.
        """
        body: dict[str, object] = {}
        if new_account_ref is not None:
            body["newAccountRef"] = new_account_ref
        if account_name is not None:
            body["accountName"] = account_name
        if callback_url is not None:
            body["callbackUrl"] = callback_url
        if expected_amount is not None:
            body["expectedAmount"] = str(round(expected_amount / 100, 2))

        response = await self._put(
            f"/accounts/virtual/{identifier}",
            body,
            request_id=request_id,
        )

        data = response.json().get("data", {})
        updated = bool(data.get("updated", False))

        logger.info(
            "nomba_virtual_account_updated",
            request_id=request_id,
            identifier=identifier,
            updated=updated,
        )

        return updated

    async def expire_virtual_account(
        self,
        identifier: str,
        *,
        request_id: str | None = None,
    ) -> bool:
        """
        Expire (deactivate) a virtual account.

        DELETE /accounts/virtual/{identifier}

        Args:
            identifier: The accountRef of the account to expire.
            request_id: Optional request ID for tracing

        Returns:
            True if Nomba confirmed the account is now expired.
        """
        response = await self._delete(
            f"/accounts/virtual/{identifier}",
            request_id=request_id,
        )

        data = response.json().get("data", {})
        expired = bool(data.get("expired", False))

        logger.info(
            "nomba_virtual_account_expired",
            request_id=request_id,
            identifier=identifier,
            expired=expired,
        )

        return expired

    async def filter_virtual_accounts(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        account_name: str | None = None,
        account_ref: str | None = None,
        bank_account_number: str | None = None,
        expired: bool | None = None,
        resource_acquired: bool | None = None,
        request_id: str | None = None,
    ) -> tuple[list[NombaVirtualAccountResponse], str | None]:
        """
        Filter/list virtual accounts under our sub-account.

        POST /accounts/virtual/list

        Args:
            limit: Page size.
            cursor: Pagination cursor from a previous call.
            account_name: Filter by account holder name.
            account_ref: Filter by our reference.
            bank_account_number: Filter by NUBAN.
            expired: Filter by expiry state.
            resource_acquired: Filter by whether the account is in use.
            request_id: Optional request ID for tracing

        Returns:
            Tuple of (results, next_cursor).
        """
        params = {k: v for k, v in {"limit": limit, "cursor": cursor}.items() if v is not None}
        body = {
            k: v
            for k, v in {
                "accountName": account_name,
                "accountRef": account_ref,
                "bankAccountNumber": bank_account_number,
                "expired": expired,
                "resourceAcquired": resource_acquired,
            }.items()
            if v is not None
        }

        response = await self._post(
            "/accounts/virtual/list",
            body,
            params=params,
            request_id=request_id,
        )

        data = response.json().get("data", {})
        results = [
            NombaVirtualAccountResponse.model_validate(item)
            for item in data.get("results", [])
        ]
        next_cursor = data.get("cursor") or None

        return results, next_cursor


_nomba_virtual_accounts_client: NombaVirtualAccountsClient | None = None


def get_nomba_virtual_accounts_client() -> NombaVirtualAccountsClient:
    """Get the virtual accounts client singleton."""
    global _nomba_virtual_accounts_client
    if _nomba_virtual_accounts_client is None:
        _nomba_virtual_accounts_client = NombaVirtualAccountsClient()
    return _nomba_virtual_accounts_client
