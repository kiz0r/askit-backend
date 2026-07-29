from dotenv import load_dotenv

load_dotenv(".env.test", override=True)

from collections.abc import AsyncGenerator

import pytest
import redis.asyncio as redis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.redis as app_redis
from app.database import Base, get_async_db
from app.main import app
from app.settings import ENV_SETTINGS

_TEST_DB_URL = (
    ENV_SETTINGS.database_url.rsplit(f"/{ENV_SETTINGS.POSTGRES_DB}", 1)[0]
    + "/askit_test"
)
_TEST_REDIS_URL = ENV_SETTINGS.redis_url  # REDIS_DB=1 comes from .env.test

# NullPool avoids asyncpg connection sharing across task boundaries (BaseHTTPMiddleware compat)
_engine = create_async_engine(_TEST_DB_URL, echo=False, poolclass=NullPool)
_SessionFactory = async_sessionmaker(
    bind=_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest.fixture(scope="session", autouse=True)
async def _setup_test_env() -> AsyncGenerator[None, None]:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    app_redis.redis_pool = redis.ConnectionPool.from_url(
        _TEST_REDIS_URL, decode_responses=True
    )

    yield

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    if app_redis.redis_pool:
        await app_redis.redis_pool.aclose()
    await _engine.dispose()


@pytest.fixture(autouse=True)
async def _clean_tables() -> AsyncGenerator[None, None]:
    yield
    table_names = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    async with _engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))
    r = redis.Redis(connection_pool=app_redis.redis_pool)
    await r.flushdb()
    await r.aclose()
    from app.core.limiter import limiter

    limiter._storage.reset()


@pytest.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    # Each HTTP request in tests gets its own fresh session (NullPool guarantees no reuse).
    # The test body also gets a direct session for DB setup/assertions.
    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with _SessionFactory() as session:
            yield session

    app.dependency_overrides[get_async_db] = _override_get_db

    # The WebSocket handlers and the question-timeout task run outside the
    # request/response cycle and open their own short sessions, so they never
    # see the dependency override above. Point the factory they call at the
    # test database too, otherwise they would reach the development one.
    import app.database as app_database

    original_factory = app_database.AsyncSessionLocal
    app_database.AsyncSessionLocal = _SessionFactory

    async with _SessionFactory() as session:
        try:
            yield session
        finally:
            app_database.AsyncSessionLocal = original_factory
            app.dependency_overrides.pop(get_async_db, None)


@pytest.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


@pytest.fixture
async def auth_client(client: AsyncClient) -> AsyncClient:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "TestPass123!",
        },
    )
    assert resp.status_code == 200
    return client
