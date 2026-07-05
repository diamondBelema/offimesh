"""Nomba API integration.

This package provides production-grade clients for the Nomba payment API:

- NombaAuthClient: OAuth token management with Redis caching
- NombaVirtualAccountsClient: Wallet funding NUBAN creation
- NombaTransfersClient: Bank transfers for settlements
- NombaTransactionsClient: Transaction queries for reconciliation
- NombaSubAccountsClient: Treasury sub-account management

All feature clients inherit from BaseNombaClient which provides:
- Singleton HTTP client with connection pooling
- Exponential backoff with jitter for retries
- Circuit breaker pattern
- Structured logging with timing
- Granular error handling
- Type-safe response parsing
"""
from app.integrations.nomba.auth import (
    NombaAuthClient,
    get_nomba_auth_client,
)
from app.integrations.nomba.virtual_accounts import (
    NombaVirtualAccountsClient,
    get_nomba_virtual_accounts_client,
)
from app.integrations.nomba.transfers import (
    NombaTransfersClient,
    get_nomba_transfers_client,
)
from app.integrations.nomba.transactions import (
    NombaTransactionsClient,
    get_nomba_transactions_client,
)
from app.integrations.nomba.sub_accounts import (
    NombaSubAccountsClient,
    get_nomba_sub_accounts_client,
)
from app.integrations.nomba.base_client import (
    BaseNombaClient,
    NombaResourceClient,
    CircuitBreaker,
    RetryConfig,
    get_nomba_http_client,
)
from app.integrations.nomba.types import (
    NombaAuthResponse,
    NombaVirtualAccountResponse,
    NombaBankLookupResponse,
    NombiTransferLookupResponse,
    NombaTransferResponse,
    NombaTransactionResponse,
    NombaTransactionListResponse,
    NombaWebhookEvent,
    NombaSubAccountResponse,
    NombaBalanceResponse,
)

__all__ = [
    # Clients
    "NombaAuthClient",
    "get_nomba_auth_client",
    "NombaVirtualAccountsClient",
    "get_nomba_virtual_accounts_client",
    "NombaTransfersClient",
    "get_nomba_transfers_client",
    "NombaTransactionsClient",
    "get_nomba_transactions_client",
    "NombaSubAccountsClient",
    "get_nomba_sub_accounts_client",
    # Base client
    "BaseNombaClient",
    "NombaResourceClient",
    "CircuitBreaker",
    "RetryConfig",
    "get_nomba_http_client",
    # Types
    "NombaAuthResponse",
    "NombaVirtualAccountResponse",
    "NombaBankLookupResponse",
    "NombiTransferLookupResponse",
    "NombaTransferResponse",
    "NombaTransactionResponse",
    "NombaTransactionListResponse",
    "NombaWebhookEvent",
    "NombaSubAccountResponse",
    "NombaBalanceResponse",
]
