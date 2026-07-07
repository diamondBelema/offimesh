"""Redis client configuration and helper functions."""
from __future__ import annotations

from datetime import timedelta

import redis.asyncio as redis
from redis.asyncio import Redis

from app.core.config import settings

_redis_client: Redis | None = None


async def get_redis() -> Redis:
    """Get or create Redis client instance."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def close_redis() -> None:
    """Close Redis connection on shutdown."""
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None


# --- Cache Operations ---


async def cache_get(key: str) -> str | None:
    """Get value from Redis cache."""
    client = await get_redis()
    return await client.get(key)


async def cache_set(key: str, value: str, ttl_seconds: int | None = None) -> None:
    """Set value in Redis cache with optional TTL."""
    client = await get_redis()
    if ttl_seconds:
        await client.setex(key, ttl_seconds, value)
    else:
        await client.set(key, value)


async def cache_delete(key: str) -> None:
    """Delete key from Redis cache."""
    client = await get_redis()
    await client.delete(key)


async def cache_exists(key: str) -> bool:
    """Check if key exists in Redis cache."""
    client = await get_redis()
    return bool(await client.exists(key))


# --- Nomba Token Caching ---


async def cache_nomba_token(access_token: str, expires_in: int) -> None:
    """Cache Nomba access token with 55-minute TTL (safe margin)."""
    # Store with 55-minute TTL to ensure refresh before expiry
    safe_ttl = min(expires_in - 300, 3300)  # 55 minutes max
    await cache_set("nomba:access_token", access_token, safe_ttl)


async def get_cached_nomba_token() -> str | None:
    """Get cached Nomba access token."""
    return await cache_get("nomba:access_token")


async def invalidate_nomba_token() -> None:
    """Invalidate cached Nomba token."""
    await cache_delete("nomba:access_token")


# --- Nonce Tracking (Replay Protection) ---


async def check_and_store_nonce(nonce: str, ttl_hours: int = 48) -> bool:
    """
    Check if nonce is unique and store it.
    Returns True if nonce is new (valid), False if already seen (replay).
    """
    client = await get_redis()
    key = f"nonce:{nonce}"
    # SETNX returns 1 if key was set (new), 0 if key exists (duplicate)
    result = await client.setnx(key, "1")
    if result:
        await client.expire(key, int(timedelta(hours=ttl_hours).total_seconds()))
    return bool(result)


# --- Sequence Number Tracking ---


async def get_last_sequence(device_id: str, token_id: str) -> int | None:
    """Get last processed sequence number for a device/token combination."""
    key = f"seq:{device_id}:{token_id}"
    val = await cache_get(key)
    return int(val) if val else None


async def set_last_sequence(device_id: str, token_id: str, seq: int, ttl_hours: int = 48) -> None:
    """Store last processed sequence number."""
    key = f"seq:{device_id}:{token_id}"
    await cache_set(key, str(seq), int(timedelta(hours=ttl_hours).total_seconds()))


# --- Token Spending Tracking ---


async def increment_token_spending(token_id: str, amount: int, limit: int) -> tuple[bool, int]:
    """
    Atomically increment token spending.
    Returns (success, new_total) - success is False if limit exceeded.
    """
    client = await get_redis()
    key = f"token_spending:{token_id}"
    # Use Redis transaction for atomicity
    async with client.pipeline() as pipe:
        while True:
            try:
                await pipe.watch(key)
                current = await client.get(key)
                current_val = int(current) if current else 0
                new_val = current_val + amount

                if new_val > limit:
                    await pipe.unwatch()
                    return False, current_val

                pipe.multi()
                pipe.set(key, new_val, ex=int(timedelta(hours=48).total_seconds()))
                await pipe.execute()
                return True, new_val
            except redis.WatchError:
                continue


# --- Rate Limiting ---


async def increment_rate_limit(key: str, window_seconds: int) -> int:
    """Increment rate limit counter and return current count."""
    client = await get_redis()
    current = await client.incr(key)
    if current == 1:
        await client.expire(key, window_seconds)
    return current
