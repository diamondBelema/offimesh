"""Nomba sub-account API client for treasury/reconciliation reads.

Refactored to inherit from NombaResourceClient for production-grade reliability.
"""
from __future__ import annotations

import structlog

from app.core.config import settings
from app.integrations.nomba.base_client import NombaResourceClient
from app.integrations.nomba.types import NombaSubAccountBalanceResponse, NombaSubAccountDetailsResponse

logger = structlog.get_logger(__name__)


class NombaSubAccountsClient(NombaResourceClient):
    """
    Client for reading our team's sub-account balance and details.

    Used for internal bookkeeping and reconciliation ONLY -- there is no
    create/list operation because sub-accounts are dashboard-provisioned,
    not API-created. All requests use the PARENT accountId in the header
    (handled by BaseNombaClient); our sub-account id is passed as a path
    parameter, per the golden rule: header = parent, path/param = ours.
    """

    def __init__(self) -> None:
        super().__init__()
        self.sub_account_id = settings.nomba_subaccount_id
        if not self.sub_account_id:
            logger.warning(
                "nomba_subaccount_id_missing",
                message="settings.nomba_subaccount_id is not set; balance/details calls will fail.",
            )

    async def get_sub_account_balance(
        self,
        *,
        request_id: str | None = None,
    ) -> NombaSubAccountBalanceResponse:
        """
        Get our sub-account's balance.

        GET /v1/accounts/{subAccountId}/balance

        Note the real response shape: amount is a STRING in Naira
        (e.g. "281946.0"), not an int in kobo -- use .amount_kobo if
        you need it converted.
        """
        response = await self._get(
            f"/v1/accounts/{self.sub_account_id}/balance",
            request_id=request_id,
        )

        result = self._parse_response(response, NombaSubAccountBalanceResponse)

        logger.info(
            "nomba_sub_account_balance_retrieved",
            request_id=request_id,
            sub_account_id=self.sub_account_id,
            amount=result.amount,
        )

        return result

    async def get_sub_account_details(
        self,
        *,
        account_ref: str | None = None,
        request_id: str | None = None,
    ) -> NombaSubAccountDetailsResponse:
        """
        Get our sub-account's details.

        GET /v1/accounts/sub-account-details

        accountId (our sub-account) and accountRef are QUERY params on
        this endpoint, not path segments.

        Args:
            account_ref: Optional -- our own reference for the
                sub-account, if one was assigned when it was
                provisioned. Usually you only need the sub-account id
                (already set on this client).
            request_id: Optional request ID for tracing
        """
        params: dict[str, str] = {"accountId": self.sub_account_id}
        if account_ref:
            params["accountRef"] = account_ref

        response = await self._get(
            "/v1/accounts/sub-account-details",
            params=params,
            request_id=request_id,
        )

        return self._parse_response(response, NombaSubAccountDetailsResponse)


# Singleton instance
_nomba_sub_accounts_client: NombaSubAccountsClient | None = None


def get_nomba_sub_accounts_client() -> NombaSubAccountsClient:
    """Get the sub-accounts client singleton."""
    global _nomba_sub_accounts_client
    if _nomba_sub_accounts_client is None:
        _nomba_sub_accounts_client = NombaSubAccountsClient()
    return _nomba_sub_accounts_client
   
