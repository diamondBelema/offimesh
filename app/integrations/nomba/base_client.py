"""Base Nomba API client with shared functionality.

This module provides the foundation for all Nomba API clients, implementing:
- Lazy singleton HTTP client with connection pooling
- Standardized request/response handling
- Exponential backoff with jitter for retries
- Circuit breaker pattern
- Comprehensive observability (structured logging, timing, correlation IDs)
- Granular error handling
- Type-safe response parsing
"""
from __future__ import annotations

import random
import time
import uuid
from abc import ABC
from contextlib import asynccontextmanager
from typing import Any, TypeVar

import httpx
import structlog

from app.core.config import settings
from app.core.exceptions import (
    NombaAuthError,
    NombaConflictError,
    NombaError,
    NombaNotFoundError,
    NombaRateLimitError,
    NombaServerError,
    NombaServiceUnavailableError,
    NombaTimeoutError,
    NombaValidationError,
)
from app.integrations.nomba.auth import get_nomba_auth_client

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class CircuitBreaker:
    """
    Circuit breaker for Nomba API calls.

    Opens after threshold failures within a time window, allowing
    the system to fail fast and prevent cascading failures.

    States:
    - closed: Normal operation, requests flow through
    - open: Circuit is tripped, requests fail immediately
    - half-open: Testing if service has recovered
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout_seconds: float = 30.0,
        window_seconds: float = 60.0,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.reset_timeout_seconds = reset_timeout_seconds
        self.window_seconds = window_seconds
        self.failures: list[float] = []
        self.last_failure_time: float | None = None
        self.state: str = "closed"
        self._half_open_attempts: int = 0

    def record_failure(self) -> None:
        """Record a failure and potentially open circuit."""
        now = time.time()
        # Remove failures outside the window
        self.failures = [f for f in self.failures if now - f < self.window_seconds]
        self.failures.append(now)
        self.last_failure_time = now

        if len(self.failures) >= self.failure_threshold:
            if self.state != "open":
                logger.warning(
                    "nomba_circuit_opened",
                    failure_count=len(self.failures),
                    threshold=self.failure_threshold,
                )
            self.state = "open"

    def record_success(self) -> None:
        """Record success and close circuit."""
        self.failures.clear()
        self.state = "closed"
        self._half_open_attempts = 0

    def can_execute(self) -> bool:
        """Check if a request can proceed."""
        now = time.time()

        if self.state == "closed":
            return True

        if self.state == "open":
            # Check if we should transition to half-open
            if self.last_failure_time is not None:
                elapsed = now - self.last_failure_time
                if elapsed >= self.reset_timeout_seconds:
                    self.state = "half-open"
                    self._half_open_attempts = 0
                    logger.info("nomba_circuit_transitioned", new_state="half-open")
                    return True
            return False

        # half-open: allow limited test requests
        if self._half_open_attempts < 3:
            self._half_open_attempts += 1
            return True
        return False


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay_seconds: float = 0.5,
        max_delay_seconds: float = 8.0,
        jitter_factor: float = 0.5,
        retryable_status_codes: frozenset[int] | None = None,
    ) -> None:
        self.max_retries = max_retries
        self.base_delay_seconds = base_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self.jitter_factor = jitter_factor
        self.retryable_status_codes = retryable_status_codes or frozenset({408, 429, 500, 502, 503, 504})

    def compute_delay(self, attempt: int) -> float:
        """Compute delay with exponential backoff and jitter."""
        # Exponential backoff: base * 2^attempt
        exponential_delay = self.base_delay_seconds * (2 ** attempt)
        # Cap at max delay
        capped_delay = min(exponential_delay, self.max_delay_seconds)
        # Add jitter: random factor between (1 - jitter) and (1 + jitter)
        jitter = 1 + random.uniform(-self.jitter_factor, self.jitter_factor)
        return capped_delay * jitter


class NombaHTTPClient:
    """
    Singleton HTTP client for all Nomba API calls.

    Manages a shared httpx.AsyncClient with:
    - Connection pooling
    - Configurable timeouts
    - Lazy initialization
    """

    _instance: NombaHTTPClient | None = None
    _client: httpx.AsyncClient | None = None

    def __new__(cls) -> NombaHTTPClient:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def get_client(self) -> httpx.AsyncClient:
        """Get or lazily create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=settings.nomba_base_url,
                timeout=httpx.Timeout(
                    connect=5.0,
                    read=30.0,
                    write=30.0,
                    pool=5.0,
                ),
                limits=httpx.Limits(
                    max_connections=100,
                    max_keepalive_connections=20,
                    keepalive_expiry=30.0,
                ),
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def get_nomba_http_client() -> NombaHTTPClient:
    """Get the singleton HTTP client instance."""
    return NombaHTTPClient()


class BaseNombaClient(ABC):
    """
    Base client for Nomba API operations.

    Provides shared functionality for all feature-specific clients:
    - Authentication header management
    - Request execution with retries and circuit breaker
    - Response parsing with type safety
    - Structured logging with timing
    - Granular error handling

    Subclasses implement only business-specific logic.
    """

    def __init__(
        self,
        circuit_breaker: CircuitBreaker | None = None,
        retry_config: RetryConfig | None = None,
    ) -> None:
        self.account_id = settings.nomba_account_id
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.retry_config = retry_config or RetryConfig()
        self._http_client = get_nomba_http_client()

    async def _get_headers(self, include_auth: bool = True) -> dict[str, str]:
        """
        Get headers for API requests.

        Args:
            include_auth: Whether to include Bearer token (default True)

        Returns:
            Headers dictionary
        """
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "accountId": self.account_id,
        }

        if include_auth:
            auth_client = get_nomba_auth_client()
            token = await auth_client.get_access_token()
            headers["Authorization"] = f"Bearer {token}"

        return headers

    def _generate_request_id(self) -> str:
        """Generate a unique request ID for tracing."""
        return f"req_{uuid.uuid4().hex[:12]}"

    @asynccontextmanager
    async def _request_context(self, method: str, path: str, request_id: str):
        """Context manager for request logging and timing."""
        start_time = time.time()
        logger.info(
            "nomba_request_started",
            request_id=request_id,
            method=method,
            path=path,
            # Never log credentials or tokens
        )
        try:
            yield
        finally:
            duration_ms = (time.time() - start_time) * 1000
            logger.info(
                "nomba_request_completed",
                request_id=request_id,
                method=method,
                path=path,
                duration_ms=round(duration_ms, 2),
            )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        include_auth: bool = True,
        is_idempotent: bool = False,
        request_id: str | None = None,
    ) -> httpx.Response:
        """
        Execute an HTTP request with retries and circuit breaker.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            path: API endpoint path
            body: Request body for POST/PUT
            params: Query parameters
            include_auth: Whether to include auth header
            is_idempotent: Whether the operation is safe to retry
            request_id: Optional request ID for tracing

        Returns:
            httpx.Response

        Raises:
            NombaError or subclasses based on response
        """
        request_id = request_id or self._generate_request_id()
        headers = await self._get_headers(include_auth=include_auth)

        last_error: Exception | None = None
        attempt = 0

        while attempt <= self.retry_config.max_retries:
            # Check circuit breaker
            if not self.circuit_breaker.can_execute():
                raise NombaServiceUnavailableError(
                    "Nomba service unavailable (circuit breaker open)",
                    request_id=request_id,
                )

            client = await self._http_client.get_client()

            try:
                async with self._request_context(method, path, request_id):
                    response = await client.request(
                        method=method,
                        url=path,
                        headers=headers,
                        json=body,
                        params=params,
                    )

                # Handle response status codes
                return self._handle_response(response, request_id)

            except httpx.TimeoutException as e:
                last_error = NombaTimeoutError(
                    timeout_seconds=30.0,
                    request_id=request_id,
                )
                self.circuit_breaker.record_failure()
                logger.warning(
                    "nomba_request_timeout",
                    request_id=request_id,
                    attempt=attempt,
                    error=str(e),
                )

            except httpx.ConnectError as e:
                last_error = NombaServiceUnavailableError(
                    "Failed to connect to Nomba API",
                    request_id=request_id,
                )
                self.circuit_breaker.record_failure()
                logger.warning(
                    "nomba_connection_error",
                    request_id=request_id,
                    attempt=attempt,
                    error=str(e),
                )

            except httpx.HTTPError as e:
                last_error = NombaError(
                    f"HTTP error: {e}",
                    request_id=request_id,
                )
                self.circuit_breaker.record_failure()
                logger.error(
                    "nomba_http_error",
                    request_id=request_id,
                    attempt=attempt,
                    error=str(e),
                )

            # Check if we should retry
            if not is_idempotent and attempt > 0:
                # Don't retry non-idempotent operations on failure
                break

            # Check if this was a retryable error
            if isinstance(last_error, (NombaTimeoutError, NombaServiceUnavailableError)):
                attempt += 1
                if attempt <= self.retry_config.max_retries:
                    delay = self.retry_config.compute_delay(attempt - 1)
                    logger.info(
                        "nomba_request_retry",
                        request_id=request_id,
                        attempt=attempt,
                        delay_seconds=round(delay, 3),
                    )
                    await self._sleep(delay)
                    continue

            # Non-retryable error
            break

        # All retries exhausted
        if last_error:
            raise last_error

        # Should never reach here
        raise NombaError("Unexpected error in request handling", request_id=request_id)

    async def _sleep(self, seconds: float) -> None:
        """Sleep for the given duration."""
        import asyncio
        await asyncio.sleep(seconds)

    def _handle_response(self, response: httpx.Response, request_id: str) -> httpx.Response:
        """
        Handle the HTTP response and raise appropriate errors.

        Args:
            response: The HTTP response
            request_id: Request ID for tracing

        Returns:
            The response if successful

        Raises:
            NombaError or subclasses based on status code
        """
        status_code = response.status_code

        # Rate limit
        if status_code == 429:
            retry_after = response.headers.get("Retry-After")
            retry_seconds = int(retry_after) if retry_after else None
            raise NombaRateLimitError(retry_seconds, request_id=request_id)

        # Server errors (5xx)
        if 500 <= status_code < 600:
            self.circuit_breaker.record_failure()
            raise NombaServerError(status_code, request_id=request_id)

        # Client errors
        if status_code == 400:
            error_body = self._extract_error_message(response)
            raise NombaValidationError(error_body, request_id=request_id)

        if status_code == 401:
            raise NombaAuthError("Nomba authentication failed", request_id=request_id)

        if status_code == 404:
            raise NombaNotFoundError(request_id=request_id)

        if status_code == 409:
            error_body = self._extract_error_message(response)
            raise NombaConflictError(error_body, request_id=request_id)

        # Success (2xx)
        if 200 <= status_code < 300:
            self.circuit_breaker.record_success()
            return response

        # Unexpected status code
        raise NombaError(
            f"Unexpected status code: {status_code}",
            status_code=502,
            request_id=request_id,
        )

    def _extract_error_message(self, response: httpx.Response) -> str:
        """Extract error message from response body."""
        try:
            data = response.json()
            if isinstance(data, dict):
                if "message" in data:
                    return str(data["message"])
                if "error" in data:
                    return str(data["error"])
                if "data" in data:
                    inner = data["data"]
                    if isinstance(inner, dict) and "message" in inner:
                        return str(inner["message"])
        except Exception:
            pass
        return f"HTTP {response.status_code}: {response.text[:200]}"

    def _parse_response(self, response: httpx.Response, model_class: type[T]) -> T:
        """
        Parse response body into a typed model.

        Args:
            response: The HTTP response
            model_class: Pydantic model class to parse into

        Returns:
            Parsed model instance
        """
        data = response.json()

        # Nomba wraps responses in "data" key
        if isinstance(data, dict) and "data" in data:
            inner_data = data["data"]
        else:
            inner_data = data

        return model_class.model_validate(inner_data)

    def _parse_response_optional(self, response: httpx.Response, model_class: type[T]) -> T | None:
        """Parse response into model, returning None if empty."""
        try:
            return self._parse_response(response, model_class)
        except Exception:
            return None

    async def close(self) -> None:
        """Close the HTTP client."""
        # The shared client handles cleanup
        pass


# Convenience methods for subclasses
class NombaResourceClient(BaseNombaClient):
    """
    Base client for specific Nomba resources (transfers, accounts, etc.).

    Provides GET, POST, PUT, DELETE helpers.
    """

    async def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        request_id: str | None = None,
    ) -> httpx.Response:
        """Execute a GET request."""
        return await self._request("GET", path, params=params, is_idempotent=True, request_id=request_id)

    async def _post(
        self,
        path: str,
        body: dict[str, Any],
        *,
        is_idempotent: bool = False,
        request_id: str | None = None,
    ) -> httpx.Response:
        """Execute a POST request."""
        return await self._request("POST", path, body=body, is_idempotent=is_idempotent, request_id=request_id)

    async def _put(
        self,
        path: str,
        body: dict[str, Any],
        *,
        is_idempotent: bool = True,
        request_id: str | None = None,
    ) -> httpx.Response:
        """Execute a PUT request."""
        return await self._request("PUT", path, body=body, is_idempotent=is_idempotent, request_id=request_id)

    async def _delete(
        self,
        path: str,
        *,
        request_id: str | None = None,
    ) -> httpx.Response:
        """Execute a DELETE request."""
        return await self._request("DELETE", path, is_idempotent=True, request_id=request_id)
