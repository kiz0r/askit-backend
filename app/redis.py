from collections.abc import AsyncGenerator
import redis.asyncio as redis
from app.settings import ENV_SETTINGS

# Redis connection pool (reused across the app)
redis_pool: redis.ConnectionPool | None = None


async def init_redis() -> None:
    global redis_pool
    redis_pool = redis.ConnectionPool.from_url(
        ENV_SETTINGS.redis_url,
        decode_responses=True,
    )


async def close_redis() -> None:
    global redis_pool
    if redis_pool:
        await redis_pool.aclose()
        redis_pool = None


async def get_redis() -> AsyncGenerator[redis.Redis, None]:
    if redis_pool is None:
        raise RuntimeError("Redis pool not initialized")
    client = redis.Redis(connection_pool=redis_pool)
    try:
        yield client
    finally:
        await client.aclose()


def get_redis_client() -> redis.Redis:
    if redis_pool is None:
        raise RuntimeError("Redis pool not initialized")
    return redis.Redis(connection_pool=redis_pool)
