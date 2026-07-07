"""Nomba authentication client with Redis caching.

Handles OAuth client_credentials flow for obtaining and refreshing
access tokens. Tokens are cached in Redis with a 25-minute TTL
(30-min Nomba expiry minus 5-min safety margin).

Note: This client does NOT inherit from BaseNombaClient because
authentication requests use different headers (no Bearer token yet).
"""
from __future__ import annotations

import structlog

import httpx

from app.core.config import settings
from app.core.exceptions import NombaAuthError
from app.core.redis import cache_nomba_token, get_cached_nomba_token, invalidate_nomba_token
from app.integrations.nomba.types import NombaAuthResponse

logger = structlog.get_logger(__name__)


class NombaAuthClient:
    """
    Nomba authentication client with token caching.

    Tokens are cached in Redis with 25-minute TTL to ensure
    refresh well before the 30-minute Nomba expiry. All other
    Nomba clients depend on this for their Bearer token.

    This client maintains its own HTTP client because auth requests
    don't include Bearer tokens and have different requirements.
    """

    _instance: NombaAuthClient | None = None
    _client: httpx.AsyncClient | None = None

    def __new__(cls) -> NombaAuthClient:
        """Singleton pattern for auth client."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        # Only initialize once
        if not hasattr(self, "_initialized"):
            self.base_url = settings.nomba_base_url
            self.account_id = settings.nomba_account_id
            self.client_id = settings.nomba_client_id
            self.client_secret = settings.nomba_client_secret
            self._initialized = True

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or lazily create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(
                    connect=5.0,
                    read=10.0,
                    write=10.0,
                    pool=5.0,
                ),
                limits=httpx.Limits(
                    max_connections=10,
                    max_keepalive_connections=5,
                ),
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get_access_token(self) -> str:
        """
        Get a valid access token, using cached token if available.

        The token is cached for 25 minutes (safe margin from 30-minute expiry).
        Returns the access token string.

        Returns:
            str: The Bearer access token

        Raises:
            NombaAuthError: If authentication fails
        """
        # Try to get cached token first
        cached_token = await get_cached_nomba_token()
        if cached_token:
            return cached_token

        # Need to fetch new token
        logger.info("nomba_auth_fetching_token")
        return await self._fetch_new_token()

    async def _fetch_new_token(self) -> str:
        """
        Fetch a new access token from Nomba and cache it.

        POST /v1/auth/token/issue
        Headers: Content-Type, accountId
        Body: grant_type, client_id, client_secret

        Confirmed against Nomba's own reference example:
        POST https://api.nomba.com/v1/auth/token/issue

        Returns:
            str: The access token

        Raises:
            NombaAuthError: If request fails or token is invalid
        """
        client = await self._get_client()

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "accountId": self.account_id,
        }

        body = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        try:
            logger.debug(
                "nomba_auth_request_started",
                # Never log client_id or client_secret
            )

            response = await client.post(
                "/v1/auth/token/issue",
                headers=headers,
                json=body,
            )

            if response.status_code != 200:
                logger.error(
                    "nomba_auth_failed",
                    status=response.status_code,
                    # Don't log response body which may contain errors
                )
                raise NombaAuthError(
                    f"Nomba authentication failed (HTTP {response.status_code})"
                )

            data = response.json()

            # Nomba wraps response in "data" key
            if "data" in data:
                auth_data = data["data"]
            else:
                auth_data = data

            auth_response = NombaAuthResponse.model_validate(auth_data)

            remaining = auth_response.expires_in
            await cache_nomba_token(auth_response.access_token, remaining)

            logger.info(
                "nomba_auth_success",
                expires_in=remaining,
            )

            return auth_response.access_token

        except httpx.TimeoutException as e:
            logger.error("nomba_auth_timeout", error=str(e))
            raise NombaAuthError("Nomba auth request timed out") from e

        except httpx.ConnectError as e:
            logger.error("nomba_auth_connection_error", error=str(e))
            raise NombaAuthError("Failed to connect to Nomba API") from e

        except httpx.HTTPError as e:
            logger.error("nomba_auth_http_error", error=str(e))
            raise NombaAuthError(f"HTTP error during Nomba auth: {e}") from e

    async def refresh_token(self) -> str:
        """
        Force refresh the access token.

        Invalidates the cached token and fetches a fresh one.

        Returns:
            str: The new access token
        """
        # Invalidate cached token first
        await invalidate_nomba_token()

        # Fetch fresh token
        logger.info("nomba_auth_forcing_refresh")
        return await self._fetch_new_token()


# Singleton accessor
def get_nomba_auth_client() -> NombaAuthClient:
    """Get the Nomba auth client singleton."""
    return NombaAuthClient()
        
