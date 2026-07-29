from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.settings import ENV_SETTINGS


class Base(DeclarativeBase):
    pass


# A WebSocket connection holds its dependency-injected session for as long as it
# stays open, so the pool has to accommodate a full game room (up to
# max_participants players plus the host) on top of the ordinary HTTP traffic.
# The SQLAlchemy defaults of 5 + 10 are well below that, and once they are
# exhausted every HTTP request blocks waiting for a connection.
engine = create_async_engine(
    ENV_SETTINGS.database_url,
    echo=ENV_SETTINGS.LOG_LEVEL == "DEBUG",
    future=True,
    pool_size=ENV_SETTINGS.DB_POOL_SIZE,
    max_overflow=ENV_SETTINGS.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=1800,
)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
