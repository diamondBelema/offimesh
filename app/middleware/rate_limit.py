"""Rate limiting middleware using Redis."""
from __future__ import annotations

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.redis import increment_rate_limit


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple rate limiting middleware using Redis.

    Limits requests per IP address within a time window.
    More sophisticated rate limiting can be done with slowapi.
    """

    def __init__(self, app, requests_per_minute: int = None):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute or settings.rate_limit_requests
        self.window_seconds = settings.rate_limit_window_seconds

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/", "/v1/health"]:
            return await call_next(request)

        # Skip for webhook endpoints (Nomba might batch)
        if request.url.path.startswith("/v1/webhooks/"):
            return await call_next(request)

        # Get client IP
        client_ip = request.client.host if request.client else "unknown"
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()

        # Build rate limit key
        key = f"ratelimit:{client_ip}:{request.url.path}"

        # Check rate limit
        count = await increment_rate_limit(key, self.window_seconds)

        if count > self.requests_per_minute:
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": f"Rate limit exceeded. Max {self.requests_per_minute} requests per {self.window_seconds} seconds.",
                    },
                    "meta": {
                        "request_id": getattr(request.state, "correlation_id", ""),
                        "timestamp": time.time(),
                    },
                },
                headers={
                    "X-RateLimit-Limit": str(self.requests_per_minute),
                    "X-RateLimit-Remaining": str(max(0, self.requests_per_minute - count)),
                    "X-RateLimit-Reset": str(self.window_seconds),
                },
            )

        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(max(0, self.requests_per_minute - count))

        return response
