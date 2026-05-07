"""Redis connection and utilities for real-time game features."""

from collections.abc import AsyncGenerator

import redis.asyncio as redis

from app.settings import ENV_SETTINGS


# Redis connection pool (reused across the app)
redis_pool: redis.ConnectionPool | None = None


async def init_redis() -> None:
    """Initialize Redis connection pool."""
    global redis_pool
    redis_pool = redis.ConnectionPool.from_url(
        ENV_SETTINGS.redis_url,
        decode_responses=True,
    )


async def close_redis() -> None:
    """Close Redis connection pool."""
    global redis_pool
    if redis_pool:
        await redis_pool.disconnect()
        redis_pool = None


async def get_redis() -> AsyncGenerator[redis.Redis, None]:
    """Get Redis client from pool. Use as FastAPI dependency."""
    if redis_pool is None:
        raise RuntimeError("Redis pool not initialized")
    client = redis.Redis(connection_pool=redis_pool)
    try:
        yield client
    finally:
        await client.aclose()


def get_redis_client() -> redis.Redis:
    """Get Redis client synchronously (for use outside request context)."""
    if redis_pool is None:
        raise RuntimeError("Redis pool not initialized")
    return redis.Redis(connection_pool=redis_pool)
