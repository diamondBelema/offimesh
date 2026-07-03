"""Nomba authentication client with Redis caching."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import structlog

from app.core.config import settings
from app.core.exceptions import NombaAuthError
from app.core.redis import cache_nomba_token, get_cached_nomba_token, invalidate_nomba_token
from app.integrations.nomba.types import NombaAuthResponse

logger = structlog.get_logger(__name__)


class NombaAuthClient:
    """
    Nomba authentication client with token caching.

    Tokens are cached in Redis with 55-minute TTL to ensure
    refresh before expiry. All other Nomba clients depend on
    this for their Bearer token.
    """

    def __init__(self) -> None:
        self.base_url = settings.nomba_base_url
        self.account_id = settings.nomba_account_id
        self.client_id = settings.nomba_client_id
        self.client_secret = settings.nomba_client_secret
        self._http_client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=30.0,
            )
        return self._http_client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def get_access_token(self) -> str:
        """
        Get a valid access token, using cached token if available.

        The token is cached for 55 minutes (safe margin from 1-hour expiry).
        Returns the access token string.
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

        POST /auth/token/issue
        Headers: Content-Type, accountId
        Body: grant_type, client_id, client_secret
        """
        client = await self._get_client()

        headers = {
            "Content-Type": "application/json",
            "accountId": self.account_id,
        }

        body = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        try:
            response = await client.post(
                "/auth/token/issue",
                headers=headers,
                json=body,
            )

            if response.status_code != 200:
                logger.error(
                    "nomba_auth_failed",
                    status=response.status_code,
                    body=response.text[:500],
                )
                raise NombaAuthError(
                    f"Nomba auth failed: {response.status_code} - {response.text[:200]}"
                )

            data = response.json()

            # Nomba wraps response in "data" key
            if "data" in data:
                auth_data = data["data"]
            else:
                auth_data = data

            auth_response = NombaAuthResponse(**auth_data)

            # Cache the token with safe TTL (55 minutes)
            await cache_nomba_token(auth_response.access_token, auth_response.expires_in)

            logger.info(
                "nomba_auth_success",
                expires_in=auth_response.expires_in,
            )

            return auth_response.access_token

        except httpx.HTTPError as e:
            logger.error("nomba_auth_http_error", error=str(e))
            raise NombaAuthError(f"HTTP error during Nomba auth: {e}") from e

    async def refresh_token(self) -> str:
        """
        Force refresh the access token.

        POST /auth/token/refresh
        """
        # Invalidate cached token first
        await invalidate_nomba_token()

        # Fetch fresh token
        return await self._fetch_new_token()


# Singleton instance
_nomba_auth_client: NombaAuthClient | None = None


def get_nomba_auth_client() -> NombaAuthClient:
    """Get the Nomba auth client singleton."""
    global _nomba_auth_client
    if _nomba_auth_client is None:
        _nomba_auth_client = NombaAuthClient()
    return _nomba_auth_client
