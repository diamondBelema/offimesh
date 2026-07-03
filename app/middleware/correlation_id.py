"""Correlation ID middleware for request tracing."""
from __future__ import annotations

import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import bind_context, clear_context


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds a correlation ID to every request.

    The correlation ID is:
    1. Taken from X-Correlation-ID header if provided
    2. Generated as new UUID if not provided
    3. Stored in request.state for access in handlers
    4. Added to response headers
    5. Bound to logging context
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Get or generate correlation ID
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        # Store in request state
        request.state.correlation_id = correlation_id

        # Bind to logging context
        bind_context(correlation_id=correlation_id)

        try:
            response = await call_next(request)

            # Add to response headers
            response.headers["X-Correlation-ID"] = correlation_id

            return response

        finally:
            # Clear logging context
            clear_context()


def get_correlation_id(request: Request) -> str:
    """Get correlation ID from request state."""
    return getattr(request.state, "correlation_id", "")
