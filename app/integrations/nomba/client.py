"""Unified Nomba API client combining all sub-clients."""
from __future__ import annotations

from app.integrations.nomba.auth import (
    NombaAuthClient,
    get_nomba_auth_client,
)
from app.integrations.nomba.transfers import (
    NombaTransfersClient,
    get_nomba_transfers_client,
)
from app.integrations.nomba.virtual_accounts import (
    NombaVirtualAccountsClient,
    get_nomba_virtual_accounts_client,
)
from app.integrations.nomba.transactions import (
    NombaTransactionsClient,
    get_nomba_transactions_client,
)


class NombaClient:
    """
    Unified client for all Nomba API operations.

    Provides convenient access to all Nomba sub-clients:
    - auth: Token management (automatic via other clients)
    - virtual_accounts: Wallet funding accounts
    - transfers: Settlement transfers to merchants
    - transactions: Reconciliation queries
    """

    @property
    def auth(self) -> NombaAuthClient:
        """Get auth client."""
        return get_nomba_auth_client()

    @property
    def virtual_accounts(self) -> NombaVirtualAccountsClient:
        """Get virtual accounts client."""
        return get_nomba_virtual_accounts_client()

    @property
    def transfers(self) -> NombaTransfersClient:
        """Get transfers client."""
        return get_nomba_transfers_client()

    @property
    def transactions(self) -> NombaTransactionsClient:
        """Get transactions client."""
        return get_nomba_transactions_client()

    async def close_all(self) -> None:
        """Close all underlying HTTP clients."""
        await self.auth.close()
        await self.virtual_accounts.close()
        await self.transfers.close()
        await self.transactions.close()


# Singleton
_nomba_client: NombaClient | None = None


def get_nomba_client() -> NombaClient:
    """Get the unified Nomba client."""
    global _nomba_client
    if _nomba_client is None:
        _nomba_client = NombaClient()
    return _nomba_client
